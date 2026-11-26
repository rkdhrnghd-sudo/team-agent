"""진짜 AI 쪽 코드 검사. 실제 Gemini는 부르지 않고 _ask를 가짜로 바꿔 끼운다."""

import pytest

from app import ai

NOTICE = "공정 개선 보고서 A4 10쪽과 발표 10분. 평가: 내용 60, 발표 40."


def goals(n=5, hours=3, skill="자료조사"):
    return [{"stage": i + 1, "title": f"목표{i}", "hours": hours, "skill": skill, "done_rule": "자료 3개, 자료마다 3줄"} for i in range(n)]


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


def use(monkeypatch, answer=None, error=None):
    calls = []

    def fake_ask(system, prompt, schema):
        calls.append({"system": system, "prompt": prompt, "schema": schema})
        if error:
            raise error
        return answer

    monkeypatch.setattr(ai, "_ask", fake_ask)
    return calls


def test_no_key_uses_fake(monkeypatch):
    calls = use(monkeypatch, {"goals": goals(), "warnings": []})
    out = ai.make_plan(NOTICE)
    assert out["fake"] is True and calls == []


def test_plan_from_ai(monkeypatch, key):
    calls = use(monkeypatch, {"goals": goals(), "warnings": ["발표 날짜가 없음"]})
    out = ai.make_plan(NOTICE)
    assert out["fake"] is False
    assert [g["title"] for g in out["goals"]] == [f"목표{i}" for i in range(5)]
    assert "발표 날짜가 없음" in out["warnings"]
    assert "<<<\n" + NOTICE + "\n>>>" in calls[0]["prompt"]


def test_plan_prompt_has_team_size_and_deadline(monkeypatch, key):
    calls = use(monkeypatch, {"goals": goals(), "warnings": []})
    ai.make_plan(NOTICE, 3, "2026-12-10")
    assert "팀원 수: 3명" in calls[0]["prompt"] and "6개 또는 9개" in calls[0]["prompt"]
    assert "2026-12-10" in calls[0]["prompt"]


def test_plan_keeps_notice_check(monkeypatch, key):
    use(monkeypatch, {"goals": goals(), "warnings": []})
    out = ai.make_plan("팀 보고서 내기")
    assert any("평가 기준" in w for w in out["warnings"])
    assert any("분량" in w for w in out["warnings"])


@pytest.mark.parametrize("bad", [
    {"goals": goals(hours=6), "warnings": []},
    {"goals": goals(skill="노래"), "warnings": []},
    {"goals": goals(n=2), "warnings": []},
    {"goals": [{"stage": 1, "title": "", "hours": 3, "skill": "정리", "done_rule": "표 1개"}] * 3, "warnings": []},
    {"nothing": 1},
])
def test_bad_ai_answer_falls_back(monkeypatch, key, bad):
    use(monkeypatch, bad)
    out = ai.make_plan(NOTICE)
    assert out["fake"] is True
    assert any("규칙에 맞지 않아" in w for w in out["warnings"])


def test_ai_error_falls_back(monkeypatch, key):
    use(monkeypatch, error=TimeoutError())
    out = ai.make_plan(NOTICE)
    assert out["fake"] is True
    assert any("연결하지 못해" in w for w in out["warnings"])


def test_check_from_ai(monkeypatch, key):
    calls = use(monkeypatch, {"items": [
        {"verdict": "채움", "why": "자료 3개"},
        {"verdict": "판단 어려움", "why": "요약 질은 모름"},
    ]})
    out = ai.check_submission("자료 3개, 자료마다 3줄 요약", "내용")
    assert out["fake"] is False
    assert [i["ok"] for i in out["items"]] == [True, None]
    assert out["result"] == "팀장 확인"
    assert "1. 자료 3개\n2. 자료마다 3줄 요약" in calls[0]["prompt"]
    assert calls[0]["schema"]["properties"]["items"]["minItems"] == 2


def test_check_fail_item(monkeypatch, key):
    use(monkeypatch, {"items": [{"verdict": "못 채움", "why": "1개뿐"}]})
    out = ai.check_submission("자료 3개", "내용")
    assert out["result"] == "보완 필요" and out["items"][0]["why"] == "1개뿐"


@pytest.mark.parametrize("bad", [
    {"items": [{"verdict": "채움", "why": "x"}]},  # 항목 2개인데 판정 1개
    {"items": [{"verdict": "통과", "why": "x"}, {"verdict": "채움", "why": "x"}]},  # 모르는 판정
    {"nope": []},
])
def test_bad_check_falls_back(monkeypatch, key, bad):
    use(monkeypatch, bad)
    out = ai.check_submission("자료 3개, 자료마다 3줄 요약", "내용")
    assert out["fake"] is True


def test_empty_content_does_not_call_ai(monkeypatch, key):
    calls = use(monkeypatch, {"items": []})
    out = ai.check_submission("자료 3개", "   ")
    assert calls == [] and out["result"] == "보완 필요"
