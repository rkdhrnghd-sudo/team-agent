from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app

client = TestClient(app)

DEADLINE = (date.today() + timedelta(days=14)).isoformat()
GOOD = "1. 자료 http://a.example\n요약 1\n요약 2\n2. 자료 http://b.example\n요약\n3. 자료 http://c.example\n요약"


def token_of(url):
    return parse_qs(urlparse(url).query)["t"][0]


def setup_team(share=False):
    members = [{"name": f"팀원{i}", "email": f"m{i}@example.com"} for i in range(3)]
    plan = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": members}).json()
    body = client.post("/api/approve", json={
        "deadline": DEADLINE, "members": [m["name"] for m in members], "goals": plan["goals"], "share_board": share,
    }).json()
    return plan["goals"], token_of(body["lead_url"]), {l["name"]: token_of(l["url"]) for l in body["links"]}


def board(lead):
    res = client.get("/api/status", params={"t": lead})
    assert res.status_code == 200
    return res.json()


def row(b, name):
    return next(r for r in b["contribution"] if r["name"] == name)


def pass_goal(links, g):
    res = client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": GOOD})
    assert res.json()["status"] == "통과"


def research(goals):
    return [g for g in goals if g["title"].startswith("자료 조사")]


def test_empty_board():
    goals, lead, links = setup_team()
    b = board(lead)
    assert b["team_passed"] == 0
    assert b["team_planned"] == sum(g["hours"] for g in goals)
    assert all(r["share"] == 0 and r["passed"] == 0 for r in b["contribution"])
    for name in links:
        assert row(b, name)["planned"] == sum(g["hours"] for g in goals if g["owner"] == name)


def test_passed_hours_and_share():
    goals, lead, links = setup_team()
    done = research(goals)
    for g in done:
        pass_goal(links, g)
    b = board(lead)
    passed_sum = sum(g["hours"] for g in done)
    # 기여도 판의 합 = 통과한 목표의 예상 시간 합 (완료 조건)
    assert b["team_passed"] == passed_sum
    assert sum(r["passed"] for r in b["contribution"]) == passed_sum
    assert sum(r["share"] for r in b["contribution"]) == pytest.approx(1.0, abs=0.01)
    for name in links:
        mine = sum(g["hours"] for g in done if g["owner"] == name)
        assert row(b, name)["passed"] == mine
        assert row(b, name)["share"] == pytest.approx(mine / passed_sum, abs=0.001)
        assert row(b, name)["on_time"] == sum(1 for g in done if g["owner"] == name)


def test_fix_count_counted():
    goals, lead, links = setup_team()
    g = research(goals)[0]
    client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": "짧음"})
    client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "보완 요청"})
    assert row(board(lead), g["owner"])["fix_count"] == 1
    assert row(board(lead), g["owner"])["passed"] == 0


def test_late_submission(monkeypatch):
    goals, lead, links = setup_team()
    g = research(goals)[0]
    monkeypatch.setattr(main, "today", lambda: date.fromisoformat(g["due"]) + timedelta(days=1))
    pass_goal(links, g)
    r = row(board(lead), g["owner"])
    assert r["late"] == 1 and r["on_time"] == 0


def test_overdue_after_due(monkeypatch):
    goals, lead, links = setup_team()
    monkeypatch.setattr(main, "today", lambda: date.fromisoformat(DEADLINE) + timedelta(days=1))
    b = board(lead)
    assert sum(r["overdue"] for r in b["contribution"]) == len(goals)


def test_member_sees_board_only_if_shared():
    goals, lead, links = setup_team(share=False)
    m = next(iter(links.values()))
    assert client.get("/api/status", params={"t": m}).status_code == 403
    assert client.get("/api/today", params={"member": m}).json()["share_board"] is False

    goals, lead, links = setup_team(share=True)
    m = next(iter(links.values()))
    assert client.get("/api/status", params={"t": m}).status_code == 200
    assert client.get("/api/today", params={"member": m}).json()["share_board"] is True


def test_board_script():
    res = client.get("/board.js")
    assert res.status_code == 200
    assert "javascript" in res.headers["content-type"]
    assert "renderBoard" in res.text and "innerHTML" not in res.text
