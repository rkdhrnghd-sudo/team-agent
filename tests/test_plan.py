from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.main import PlanRequest, app, make_schedule

client = TestClient(app)

TODAY = date(2026, 11, 26)
NOTICE = "공정 개선 보고서 A4 10쪽과 발표 10분. 평가: 내용 60, 발표 40."


def members(n, hours=10):
    return [
        {"name": f"팀원{i}", "email": f"m{i}@example.com", "hours_per_week": hours, "good_at": ""}
        for i in range(n)
    ]


def req(n=4, deadline=TODAY + timedelta(days=14), notice=NOTICE, hours=10):
    return PlanRequest(notice=notice, deadline=deadline, members=members(n, hours))


def test_ai_fake_plan_not_empty():
    out = ai.make_plan(NOTICE)
    assert out["goals"]
    assert all(g["title"] and g["done_rule"] and 2 <= g["hours"] <= 4 for g in out["goals"])


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_every_goal_filled_and_balanced(n):
    out = make_schedule(req(n), TODAY)
    for g in out["goals"]:
        assert g["owner"] and g["hours"] and g["due"] and g["done_rule"]
    assert out["gap"] <= 0.2
    assert sum(l["hours"] for l in out["loads"]) == sum(g["hours"] for g in out["goals"])


def test_good_at_gets_matching_goal():
    r = req()
    for m, skill in zip(r.members, ["자료조사", "PPT, 발표", "글쓰기", ""]):
        m.good_at = skill
    out = make_schedule(r, TODAY)
    owner = {g["title"]: g["owner"] for g in out["goals"]}
    assert r.members[0].name in {owner["자료 조사 1"], owner["자료 조사 2"], owner["주제 후보 조사"]}
    assert owner["발표 자료 초안"] == r.members[1].name
    assert r.members[2].name in {owner["본문 초안 앞부분"], owner["본문 초안 뒷부분"], owner["목차 짜기"]}
    assert out["gap"] <= 0.2


def test_all_due_two_days_before_deadline():
    r = req()
    out = make_schedule(r, TODAY)
    last = r.deadline - timedelta(days=2)
    assert all(TODAY < date.fromisoformat(g["due"]) <= last for g in out["goals"])


def test_notice_without_rules_warns():
    out = make_schedule(req(notice="팀 보고서 내기"), TODAY)
    assert any("평가 기준" in w for w in out["warnings"])
    assert any("분량" in w for w in out["warnings"])


def test_missing_hours_warns():
    r = req()
    r.members[0].hours_per_week = None
    out = make_schedule(r, TODAY)
    assert any(r.members[0].name in w and "팀장 확인" in w for w in out["warnings"])


def test_over_capacity_warns():
    out = make_schedule(req(hours=1), TODAY)
    assert any("가능 시간" in w and "넘습니다" in w for w in out["warnings"])


def test_api_plan_ok():
    body = {"notice": NOTICE, "deadline": (date.today() + timedelta(days=14)).isoformat(), "members": members(4)}
    res = client.post("/api/plan", json=body)
    assert res.status_code == 200
    assert res.json()["fake"] is True
    assert len(res.json()["goals"]) > 0


def test_api_plan_rejects_one_member():
    body = {"notice": NOTICE, "deadline": (date.today() + timedelta(days=14)).isoformat(), "members": members(1)}
    assert client.post("/api/plan", json=body).status_code == 422


def test_api_plan_rejects_six_members():
    body = {"notice": NOTICE, "deadline": (date.today() + timedelta(days=14)).isoformat(), "members": members(6)}
    assert client.post("/api/plan", json=body).status_code == 422


def test_api_plan_rejects_past_deadline():
    body = {"notice": NOTICE, "deadline": date.today().isoformat(), "members": members(4)}
    assert client.post("/api/plan", json=body).status_code == 422


def test_api_plan_rejects_same_email():
    m = members(3)
    m[1]["email"] = m[0]["email"]
    body = {"notice": NOTICE, "deadline": (date.today() + timedelta(days=14)).isoformat(), "members": m}
    assert client.post("/api/plan", json=body).status_code == 422
