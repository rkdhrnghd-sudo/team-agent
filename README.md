# 팀플 관리 에이전트

과제 공지를 넣으면 AI가 작은 목표로 쪼개 예상 시간을 매기고, 역할과 일정을 나누고, 제출물을 검수하며 사람별 기여도를 기록하는 앱.

## 실행 방법 (Windows)

```
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 연다. 테스트는 `.venv\Scripts\python.exe -m pytest`.

개인 링크와 팀장 링크에는 팀 번호와 이름만 넣어 서명한다. 서명 키는 환경변수 `LINK_SECRET`(이름만 `.env.example`에 있음). 없으면 켤 때마다 새 키를 만들어서, 앱을 다시 켜면 옛 링크가 안 열린다.

**지금 저장은 연습용이다.** 팀, 제출물, 검수 결과를 내 PC의 `.data/store.json`에 둔다(git에 안 올라감). 서버 안 저장이라 배포 전에 서버 밖 저장소로 바꿔야 한다.

## 약속 초안

| 주소 | 보내는 값 | 받는 값 |
|---|---|---|
| `GET /health` | 없음 | `{"status": "ok"}` |
| `GET /` | 없음 | 첫 화면(HTML) |
| `POST /api/plan` | `{"notice": 공지 글, "deadline": "YYYY-MM-DD", "members": [{"name", "email", "hours_per_week", "good_at"}]}` | `{"goals": [{"id", "title", "hours", "owner", "due", "done_rule"}], "loads": [{"name", "hours"}], "gap": 0–1, "warnings": [글], "fake": 가짜 답이면 true}` |
| `POST /api/approve` | `{"deadline", "members": [이름], "goals": plan에서 받은 goals, "share_board": false}` | `{"team_id", "lead_url", "links": [{"name", "goals": 개수, "url"}], "fake_store"}` |
| `GET /me` | `?t=개인 링크 값` | 팀원 개인 화면(HTML) |
| `GET /api/today` | `?member=개인 링크 값` | `{"name", "deadline", "goals": [{"id", "title", "hours", "due", "done_rule", "status", "reasons", "fix_count"}]}` |
| `POST /api/submit` | `{"member": 개인 링크 값, "goal_id", "content": 5000자 이하}` | `{"result": "통과" / "보완 필요" / "팀장 확인", "items": [{"rule", "ok", "why"}], "status", "fake"}` |
| `GET /lead` | `?t=팀장 링크 값` | 팀장 화면(HTML) |
| `GET /api/review` | `?lead=팀장 링크 값` | `{"deadline", "members", "goals": [... + "owner", "last": 마지막 제출], "fake_store"}` |
| `POST /api/review` | `{"lead", "goal_id", "decision": "통과" / "보완 요청", "note"}` | 바뀐 할 일 하나 |

할 일 상태: `할 일` → 제출 → AI가 통과면 `통과`, 아니면 `팀장 확인 중` → 팀장이 `통과` 또는 `보완 필요`(이유 필수, 보완 횟수 +1) → 다시 제출.
| `GET /api/status` | `?t=팀장 링크 값` (팀원 링크는 `share_board`일 때만) | `{"today", "team_planned", "team_passed", "contribution": [{"name", "planned", "passed", "share", "progress", "on_time", "late", "fix_count", "overdue"}], "share_board"}` |
| `GET /board.js` | 없음 | 기여도 판 그리는 스크립트(팀장, 팀원 화면이 같이 씀) |
| `POST /api/clock` | `{"lead", "days": 1–30}` 또는 `{"lead", "reset": true}` | `{"today", "day_offset", "max": 60}` |

**시연용 날짜 넘기기:** 팀장 화면에서 그 팀의 날짜만 앞으로 옮긴다(최대 60일, 뒤로는 '오늘로 돌아가기'만). 마감 지남, 늦게 냄, 기여도 판이 옮긴 날짜로 계산된다. `/api/today`, `/api/review`에 `today`, `day_offset`이 같이 온다.

기여도 = 그 사람이 통과한 예상 시간 ÷ 팀 전체가 통과한 예상 시간. 진행률 = 통과한 시간 ÷ 맡은 시간. 팀원에게도 보여 줄지는 승인할 때 정한다(`share_board`, 기본은 팀장만). 응답 없음(같은 알림 3번)은 알림 기능이 생기면 더한다.

| 파일 | 담당 |
|---|---|
| `app/main.py` | 백엔드 |
| `app/ai.py` | AI (함수: `make_plan`, `check_submission`). 지금은 연습용 가짜 답 |
| `app/store.py` | 백엔드 (저장: `load`, `save`, `locked`). 지금은 연습용 파일 저장 `.data/store.json`, 배포 전에 서버 밖 저장소로 바꿈 |
| `app/templates/` | 프론트엔드 |
| `README.md` | 기획 |
