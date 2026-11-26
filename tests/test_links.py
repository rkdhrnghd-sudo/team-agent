from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DEADLINE = (date.today() + timedelta(days=14)).isoformat()


def make_plan(n=3):
    members = [{"name": f"팀원{i}", "email": f"m{i}@example.com"} for i in range(n)]
    res = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": members})
    assert res.status_code == 200
    return {"deadline": DEADLINE, "members": [m["name"] for m in members], "goals": res.json()["goals"]}


def token_of(url):
    return parse_qs(urlparse(url).query)["t"][0]


def test_approve_gives_one_link_per_member():
    plan = make_plan()
    res = client.post("/api/approve", json=plan)
    assert res.status_code == 200
    links = res.json()["links"]
    assert [l["name"] for l in links] == plan["members"]
    assert sum(l["goals"] for l in links) == len(plan["goals"])
    assert all("/me?t=" in l["url"] for l in links)


def test_link_shows_only_own_goals():
    plan = make_plan()
    links = client.post("/api/approve", json=plan).json()["links"]
    for l in links:
        body = client.get("/api/today", params={"member": token_of(l["url"])}).json()
        assert body["name"] == l["name"]
        mine = {g["id"] for g in plan["goals"] if g["owner"] == l["name"]}
        assert {g["id"] for g in body["goals"]} == mine
        assert all(g["done_rule"] and g["due"] for g in body["goals"])


def test_link_has_no_email():
    plan = make_plan()
    url = client.post("/api/approve", json=plan).json()["links"][0]["url"]
    body = client.get("/api/today", params={"member": token_of(url)}).text
    assert "@example.com" not in body


def test_changed_link_is_rejected():
    plan = make_plan()
    token = token_of(client.post("/api/approve", json=plan).json()["links"][0]["url"])
    a, b = token.split(".")
    other = client.post("/api/approve", json={**plan, "deadline": "2030-01-01"}).json()["links"][0]["url"]
    forged = token_of(other).split(".")[0] + "." + b
    assert client.get("/api/today", params={"member": forged}).status_code == 403


def test_broken_link_is_rejected():
    assert client.get("/api/today", params={"member": "abc"}).status_code == 400
    assert client.get("/api/today", params={"member": "x" * 7000 + ".y"}).status_code == 400


def test_approve_rejects_unknown_owner():
    plan = make_plan()
    plan["goals"][0]["owner"] = "모르는사람"
    assert client.post("/api/approve", json=plan).status_code == 422


def test_plan_rejects_same_name():
    members = [{"name": "민수", "email": "a@example.com"}, {"name": "민수", "email": "b@example.com"}]
    res = client.post("/api/plan", json={"notice": "보고서", "deadline": DEADLINE, "members": members})
    assert res.status_code == 422


def test_me_page():
    res = client.get("/me")
    assert res.status_code == 200
    assert "내 할 일" in res.text
    assert "innerHTML" not in res.text
