from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_home():
    res = client.get("/")
    assert res.status_code == 200
    assert "팀플 관리 에이전트" in res.text


def test_team_form():
    res = client.get("/")
    for part in ['id="team-form"', 'id="notice"', 'id="deadline"', 'id="members"', 'id="plan"', "연습용 가짜 답"]:
        assert part in res.text
    assert "innerHTML" not in res.text
