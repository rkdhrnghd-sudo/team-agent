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
