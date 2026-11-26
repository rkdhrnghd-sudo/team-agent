"""AI 담당 파일. 지금은 연습용 가짜 답이다. 키가 준비되면 진짜 AI로 바꾼다.

make_plan(notice) -> {"goals": [...], "warnings": [...], "fake": bool}
  goals 하나: {"stage": 순서, "title": 글, "hours": 예상 시간, "skill": 맞는 능력, "done_rule": 완료 기준}
  과제 내용은 쓰지 않고, 할 일과 완료 기준만 만든다.
"""

import re

# (순서, 제목, 예상 시간, 맞는 능력, 완료 기준). 합 30시간.
_FAKE_GOALS = [
    (1, "공지 읽고 산출물과 평가 기준 정리", 2, "정리", "산출물, 분량, 평가 항목을 각각 1줄씩 적은 표 1개"),
    (2, "주제 후보 조사", 3, "자료조사", "출처 있는 주제 후보 3개, 각 3줄 요약"),
    (3, "자료 조사 1", 3, "자료조사", "출처 있는 자료 3개, 각 3줄 요약"),
    (3, "자료 조사 2", 3, "자료조사", "출처 있는 자료 3개, 각 3줄 요약"),
    (4, "목차 짜기", 2, "글쓰기", "목차 5개 이상, 목차마다 쓸 자료 표시"),
    (5, "본문 초안 앞부분", 4, "글쓰기", "목차 앞 절반, 목차마다 1쪽 이상"),
    (5, "본문 초안 뒷부분", 4, "글쓰기", "목차 뒤 절반, 목차마다 1쪽 이상"),
    (6, "발표 자료 초안", 3, "PPT", "슬라이드 8장 이상, 장마다 제목 1개"),
    (6, "검토와 형식 맞추기", 3, "정리", "맞춤법, 쪽 번호, 출처 표기를 확인한 표 1개"),
    (7, "발표 대본과 연습", 3, "발표", "슬라이드마다 대본 3줄 이상, 연습 1회 걸린 시간 기록"),
]


def make_plan(notice: str) -> dict:
    goals = [
        {"stage": s, "title": t, "hours": h, "skill": k, "done_rule": r}
        for s, t, h, k, r in _FAKE_GOALS
    ]
    warnings = []
    if "평가" not in notice:
        warnings.append("공지에 평가 기준이 보이지 않습니다. 공지 확인 필요")
    if not re.search(r"\d+\s*(쪽|장|분|페이지|매|자|단어)", notice):
        warnings.append("공지에 분량이 보이지 않습니다. 공지 확인 필요")
    return {"goals": goals, "warnings": warnings, "fake": True}


def check_submission(done_rule: str, content: str) -> dict:
    """완료 기준을 쉼표로 나눠 항목마다 채웠는지 본다. 지금은 연습용 가짜 검수(줄 수와 출처 표시만 봄).

    -> {"result": "통과" | "보완 필요" | "팀장 확인", "items": [{"rule", "ok": True/False/None, "why"}], "fake": bool}
    ok가 None이면 글자만으로 판단하기 어려운 항목이라 팀장에게 넘긴다.
    """
    text = content.strip()
    lines = [l for l in text.splitlines() if l.strip()]
    items = []
    for part in [p.strip() for p in done_rule.split(",") if p.strip()]:
        m = re.search(r"(\d+)\s*(개|장|줄|쪽|회|표)", part)
        if not text:
            items.append({"rule": part, "ok": False, "why": "제출한 내용이 없습니다."})
        elif "출처" in part and "http" not in text and "출처" not in text:
            items.append({"rule": part, "ok": False, "why": "출처(링크나 '출처:')가 보이지 않습니다."})
        elif m:
            need = int(m.group(1))
            items.append({
                "rule": part,
                "ok": len(lines) >= need,
                "why": f"내용 {len(lines)}줄, 기준 {need}{m.group(2)}",
            })
        else:
            items.append({"rule": part, "ok": None, "why": "글자만으로 판단하기 어렵습니다. 팀장 확인 필요"})
    if any(i["ok"] is False for i in items):
        result = "보완 필요"
    elif any(i["ok"] is None for i in items):
        result = "팀장 확인"
    else:
        result = "통과"
    return {"result": result, "items": items, "fake": True}
