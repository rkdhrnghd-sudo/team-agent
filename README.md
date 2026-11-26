# 팀플 관리 에이전트

과제 공지를 넣으면 AI가 작은 목표로 쪼개 예상 시간을 매기고, 역할과 일정을 나누고, 제출물을 검수하며 사람별 기여도를 기록하는 앱.

## 실행 방법 (Windows)

```
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --env-file .env
```

`.env`에 `GEMINI_API_KEY`를 넣으면 진짜 AI(Gemini)를 쓴다. 키가 없거나 AI가 실패하면 연습용 가짜 답으로 돌아가고 화면에 "연습용 가짜 답"이 보인다. 모델은 `GEMINI_MODEL`(기본 `gemini-3.8-flash`. `gemini-2.5-flash`는 새 사용자에게 막혀 있음). `.env`는 git에 올라가지 않는다.

브라우저에서 http://127.0.0.1:8000 을 연다. 테스트는 `.venv\Scripts\python.exe -m pytest`.

개인 링크와 팀장 링크에는 팀 번호와 이름만 넣어 서명한다. 서명 키는 환경변수 `LINK_SECRET`(이름만 `.env.example`에 있음). 없으면 켤 때마다 새 키를 만들어서, 앱을 다시 켜면 옛 링크가 안 열린다.

**지금 저장은 연습용이다.** 팀, 제출물, 검수 결과를 내 PC의 `.data/store.json`에 둔다(git에 안 올라감). 서버 안 저장이라 배포 전에 서버 밖 저장소로 바꿔야 한다.

## 약속 초안

| 주소 | 보내는 값 | 받는 값 |
|---|---|---|
| `GET /health` | 없음 | `{"status": "ok"}` |
| `GET /` | 없음 | 첫 화면(HTML) |
| `POST /api/plan` | `{"notice": 공지 글, "deadline": "YYYY-MM-DD", "members": [{"name", "email", "hours_per_week", "good_at"}]}` | `{"goals": [{"id", "title", "hours", "owner", "due", "done_rule"}], "loads": [{"name", "hours"}], "gap": 0–1, "warnings": [글], "fake": 가짜 답이면 true}` |
| `POST /api/approve` | `{"deadline", "members": [{"name", "email"}], "goals": plan에서 받은 goals, "share_board": false, "lead_email": ""}` | `{"team_id", "lead_url", "links": [{"name", "goals": 개수, "url"}], "fake_store", "mails", "fake_mail"}` |
| `GET /me` | `?t=개인 링크 값` | 팀원 개인 화면(HTML) |
| `GET /api/today` | `?member=개인 링크 값` | `{"name", "deadline", "goals": [{"id", "title", "hours", "due", "done_rule", "status", "reasons", "fix_count"}]}` |
| `POST /api/submit` | `{"member": 개인 링크 값, "goal_id", "content": 5000자 이하}` | `{"result": "통과" / "보완 필요" / "팀장 확인", "items": [{"rule", "ok", "why"}], "status", "fake"}` |
| `GET /lead` | `?t=팀장 링크 값` | 팀장 화면(HTML) |
| `GET /api/review` | `?lead=팀장 링크 값` | `{"deadline", "members", "goals": [... + "owner", "last": 마지막 제출], "fake_store"}` |
| `POST /api/review` | `{"lead", "goal_id", "decision": "통과" / "보완 요청", "note"}` | 바뀐 할 일 하나 |

할 일 상태: `할 일` → 제출 → AI가 통과면 `통과`, 아니면 `팀장 확인 중` → 팀장이 `통과` 또는 `보완 필요`(이유 필수, 보완 횟수 +1) → 다시 제출.
| `GET /api/status` | `?t=팀장 링크 값` (팀원 링크는 `share_board`일 때만) | `{"today", "team_planned", "team_passed", "contribution": [{"name", "planned", "passed", "share", "progress", "on_time", "late", "fix_count", "overdue"}], "share_board"}` |
| `GET /board.js` | 없음 | 기여도 판 그리는 스크립트(팀장, 팀원 화면이 같이 씀) |
| `POST /api/clock` | `{"lead", "days": 1–30}` 또는 `{"lead", "reset": true}` | `{"today", "day_offset", "max": 60, "mails"}` |
| `POST /api/daily` | `{"lead"}` | `{"today", "mails"}` (그 팀의 오늘 매일 알림) |
| `POST /api/cron/daily` | 머리글 `X-Cron-Secret` | `{"mails"}` (모든 팀. `CRON_SECRET`이 없으면 404) |

**메일:** 승인할 때 팀원마다 개인 링크가 담긴 계획 메일, 매일 마감 지났거나 내일까지인 할 일 1–2개(같은 날 한 번만), 팀장이 보완 요청을 확인했을 때 보완 메일, 같은 할 일 알림이 3번을 넘으면 '응답 없음' 표시와 팀장 메일. 승인 전에는 한 통도 안 나간다. `SMTP_HOST`가 없으면 연습용이라 실제로 보내지 않고 팀장 화면 '보낸 메일'에만 남긴다(`app/mail.py`). 날짜 넘기기를 하면 넘긴 날마다 매일 알림이 돈다. 진짜 '매일 정해진 시각'은 배포 때 예약 실행이 `/api/cron/daily`를 부르게 한다.

**시연용 날짜 넘기기:** 팀장 화면에서 그 팀의 날짜만 앞으로 옮긴다(최대 60일, 뒤로는 '오늘로 돌아가기'만). 마감 지남, 늦게 냄, 기여도 판이 옮긴 날짜로 계산된다. `/api/today`, `/api/review`에 `today`, `day_offset`이 같이 온다.

기여도 = 그 사람이 통과한 예상 시간 ÷ 팀 전체가 통과한 예상 시간. 진행률 = 통과한 시간 ÷ 맡은 시간. 팀원에게도 보여 줄지는 승인할 때 정한다(`share_board`, 기본은 팀장만). 응답 없음(같은 알림 3번)은 알림 기능이 생기면 더한다.

| 파일 | 담당 |
|---|---|
| `app/main.py` | 백엔드 |
| `app/ai.py` | AI (함수: `make_plan`, `check_submission`). Gemini, 키가 없으면 연습용 가짜 답 |
| `app/mail.py` | 백엔드 (`send`, `is_fake`). SMTP 설정이 없으면 연습용 |
| `app/store.py` | 백엔드 (저장: `load`, `save`, `locked`). 지금은 연습용 파일 저장 `.data/store.json`, 배포 전에 서버 밖 저장소로 바꿈 |
| `app/templates/` | 프론트엔드 |
| `README.md` | 기획 |
