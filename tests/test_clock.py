from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import MAX_DEMO_DAYS, app

client = TestClient(app)

DEADLINE = (date.today() + timedelta(days=14)).isoformat()
GOOD = "1. 자료 http://a.example\n요약 1\n요약 2\n2. 자료 http://b.example\n요약\n3. 자료 http://c.example\n요약"


def token_of(url):
    return parse_qs(urlparse(url).query)["t"][0]


def setup_team():
    members = [{"name": f"팀원{i}", "email": f"m{i}@example.com"} for i in range(3)]
    plan = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": members}).json()
    body = client.post("/api/approve", json={"deadline": DEADLINE, "members": [m["name"] for m in members], "goals": plan["goals"]}).json()
    return plan["goals"], token_of(body["lead_url"]), {l["name"]: token_of(l["url"]) for l in body["links"]}


def move(lead, **kw):
    res = client.post("/api/clock", json={"lead": lead, **kw})
    assert res.status_code == 200
    return res.json()


def test_starts_today():
    goals, lead, links = setup_team()
    body = client.get("/api/review", params={"lead": lead}).json()
    assert body["today"] == date.today().isoformat() and body["day_offset"] == 0


def test_move_and_reset():
    goals, lead, links = setup_team()
    assert move(lead, days=1)["day_offset"] == 1
    out = move(lead, days=7)
    assert out["day_offset"] == 8
    assert out["today"] == (date.today() + timedelta(days=8)).isoformat()
    member = next(iter(links.values()))
    assert client.get("/api/today", params={"member": member}).json()["today"] == out["today"]
    assert client.get("/api/status", params={"t": lead}).json()["today"] == out["today"]
    assert move(lead, reset=True)["day_offset"] == 0


def test_max_days():
    goals, lead, links = setup_team()
    for _ in range(5):
        move(lead, days=30)
    assert move(lead, days=1)["day_offset"] == MAX_DEMO_DAYS


def test_bad_days_rejected():
    goals, lead, links = setup_team()
    for d in (0, -1, 31):
        assert client.post("/api/clock", json={"lead": lead, "days": d}).status_code == 422


def test_only_lead_moves_clock():
    goals, lead, links = setup_team()
    member = next(iter(links.values()))
    assert client.post("/api/clock", json={"lead": member, "days": 1}).status_code == 403


def test_other_team_not_moved():
    goals, lead, links = setup_team()
    goals2, lead2, links2 = setup_team()
    move(lead, days=7)
    assert client.get("/api/review", params={"lead": lead2}).json()["day_offset"] == 0


def test_overdue_and_late_after_moving():
    goals, lead, links = setup_team()
    g = next(x for x in goals if x["title"] == "자료 조사 1")
    days = (date.fromisoformat(g["due"]) - date.today()).days + 1
    move(lead, days=days)
    mine = client.get("/api/today", params={"member": links[g["owner"]]}).json()["goals"]
    assert next(x for x in mine if x["id"] == g["id"])["overdue"] is True
    status = client.get("/api/status", params={"t": lead}).json()
    assert next(r for r in status["contribution"] if r["name"] == g["owner"])["overdue"] >= 1

    res = client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": GOOD})
    assert res.json()["status"] == "통과"
    status = client.get("/api/status", params={"t": lead}).json()
    assert next(r for r in status["contribution"] if r["name"] == g["owner"])["late"] == 1
