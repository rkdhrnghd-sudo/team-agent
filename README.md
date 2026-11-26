# 팀플 관리 에이전트

과제 공지를 넣으면 AI가 작은 목표로 쪼개 예상 시간을 매기고, 역할과 일정을 나누고, 제출물을 검수하며 사람별 기여도를 기록하는 앱.

## 실행 방법 (Windows)

```
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 연다. 테스트는 `.venv\Scripts\python.exe -m pytest`.

개인 링크는 서버에 저장하지 않고, 그 사람의 할 일을 링크 안에 넣어 서명한다. 서명 키는 환경변수 `LINK_SECRET`(이름만 `.env.example`에 있음). 없으면 켤 때마다 새 키를 만들어서, 앱을 다시 켜면 옛 링크가 안 열린다.

## 약속 초안

| 주소 | 보내는 값 | 받는 값 |
|---|---|---|
| `GET /health` | 없음 | `{"status": "ok"}` |
| `GET /` | 없음 | 첫 화면(HTML) |
| `POST /api/plan` | `{"notice": 공지 글, "deadline": "YYYY-MM-DD", "members": [{"name", "email", "hours_per_week", "good_at"}]}` | `{"goals": [{"id", "title", "hours", "owner", "due", "done_rule"}], "loads": [{"name", "hours"}], "gap": 0–1, "warnings": [글], "fake": 가짜 답이면 true}` |
| `POST /api/approve` | `{"deadline", "members": [이름], "goals": plan에서 받은 goals}` | `{"links": [{"name", "goals": 개수, "url"}]}` |
| `GET /me` | `?t=개인 링크 값` | 팀원 개인 화면(HTML) |
| `GET /api/today` | `?member=개인 링크 값` | `{"name", "deadline", "goals": [{"id", "title", "hours", "due", "done_rule"}]}` |
| `POST /api/submit` | `{"member", "goal_id", "content"}` | `{"result": "통과" 또는 "보완 필요", "reasons": [글]}` |
| `GET /api/status` | `?team_id=` | `{"goals": [...], "contribution": [{"name", "hours", "share", "on_time", "no_reply"}]}` |

| 파일 | 담당 |
|---|---|
| `app/main.py` | 백엔드 |
| `app/ai.py` | AI (함수: `make_plan`, `check_submission`). 지금은 연습용 가짜 답 |
| `app/templates/` | 프론트엔드 |
| `README.md` | 기획 |
