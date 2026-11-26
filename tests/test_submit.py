from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app import ai
from app.main import app

client = TestClient(app)

DEADLINE = (date.today() + timedelta(days=14)).isoformat()
GOOD = "1. 자료 http://a.example\n요약 1\n요약 2\n2. 자료 http://b.example\n요약\n3. 자료 http://c.example\n요약"


def token_of(url):
    return parse_qs(urlparse(url).query)["t"][0]


def setup_team():
    members = [{"name": f"팀원{i}", "email": f"m{i}@example.com"} for i in range(3)]
    plan = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": members}).json()
    body = client.post("/api/approve", json={"deadline": DEADLINE, "members": [m["name"] for m in members], "goals": plan["goals"]}).json()
    lead = token_of(body["lead_url"])
    links = {l["name"]: token_of(l["url"]) for l in body["links"]}
    return plan["goals"], lead, links


def goal_titled(goals, title):
    return next(g for g in goals if g["title"] == title)


def submit(links, g, content):
    return client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": content})


def status_of(lead, goal_id):
    goals = client.get("/api/review", params={"lead": lead}).json()["goals"]
    return next(g for g in goals if g["id"] == goal_id)


# --- AI 가짜 검수 ---

def test_check_pass():
    out = ai.check_submission("출처 있는 자료 3개, 각 3줄 요약", GOOD)
    assert out["result"] == "통과"
    assert all(i["ok"] is True for i in out["items"])


def test_check_missing_source():
    out = ai.check_submission("출처 있는 자료 3개", "자료1\n자료2\n자료3")
    assert out["result"] == "보완 필요"
    assert "출처" in out["items"][0]["why"]


def test_check_too_short():
    out = ai.check_submission("슬라이드 8장 이상", "한 줄")
    assert out["result"] == "보완 필요"


def test_check_unclear_goes_to_lead():
    out = ai.check_submission("목차마다 쓸 자료 표시", "아무 내용")
    assert out["result"] == "팀장 확인"
    assert out["items"][0]["ok"] is None


# --- 제출과 검수 흐름 ---

def test_pass_right_away():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "자료 조사 1")
    res = submit(links, g, GOOD).json()
    assert res["result"] == "통과" and res["status"] == "통과"
    assert status_of(lead, g["id"])["status"] == "통과"


def test_fix_needs_lead_before_member_sees_it():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "자료 조사 1")
    res = submit(links, g, "자료 하나").json()
    assert res["status"] == "팀장 확인 중"
    me = client.get("/api/today", params={"member": links[g["owner"]]}).json()
    mine = next(x for x in me["goals"] if x["id"] == g["id"])
    assert mine["status"] == "팀장 확인 중" and mine["reasons"] == []

    r = client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "보완 요청"})
    assert r.status_code == 200
    me = client.get("/api/today", params={"member": links[g["owner"]]}).json()
    mine = next(x for x in me["goals"] if x["id"] == g["id"])
    assert mine["status"] == "보완 필요" and mine["fix_count"] == 1
    assert mine["reasons"]  # 근거 없는 보완 필요는 없다


def test_resubmit_after_fix():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "자료 조사 1")
    submit(links, g, "자료 하나")
    client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "보완 요청"})
    assert submit(links, g, GOOD).json()["status"] == "통과"


def test_lead_can_pass_unclear():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "목차 짜기")
    assert submit(links, g, "\n".join(f"{i}. 목차 - 자료" for i in range(6))).json()["status"] == "팀장 확인 중"
    r = client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "통과"})
    assert r.json()["status"] == "통과"


def test_fix_from_unclear_still_has_reason():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "목차 짜기")
    submit(links, g, "\n".join(f"{i}. 목차 - 자료" for i in range(6)))
    r = client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "보완 요청", "note": "자료 표시 빠짐"})
    assert r.status_code == 200
    assert any("판단하기 어렵" in x for x in r.json()["reasons"])
    assert any(x == "팀장: 자료 표시 빠짐" for x in r.json()["reasons"])


def test_review_only_when_waiting():
    goals, lead, links = setup_team()
    r = client.post("/api/review", json={"lead": lead, "goal_id": goals[0]["id"], "decision": "통과"})
    assert r.status_code == 409


def test_cannot_submit_others_goal():
    goals, lead, links = setup_team()
    g = goals[0]
    other = next(n for n in links if n != g["owner"])
    r = client.post("/api/submit", json={"member": links[other], "goal_id": g["id"], "content": GOOD})
    assert r.status_code == 403


def test_cannot_submit_twice_while_waiting():
    goals, lead, links = setup_team()
    g = goal_titled(goals, "자료 조사 1")
    submit(links, g, "자료 하나")
    assert submit(links, g, GOOD).status_code == 409


def test_member_link_cannot_open_lead():
    goals, lead, links = setup_team()
    any_member = next(iter(links.values()))
    assert client.get("/api/review", params={"lead": any_member}).status_code == 403
    assert client.get("/api/today", params={"member": lead}).status_code == 403


def test_empty_or_huge_content_rejected():
    goals, lead, links = setup_team()
    g = goals[0]
    assert submit(links, g, "").status_code == 422
    assert submit(links, g, "가" * 5001).status_code == 422


def test_pages():
    for path, text in [("/me", "내 할 일"), ("/lead", "팀장 화면")]:
        res = client.get(path)
        assert res.status_code == 200 and text in res.text
        assert "innerHTML" not in res.text
