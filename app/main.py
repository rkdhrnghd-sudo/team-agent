import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import zlib
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from app import ai, store

app = FastAPI()

TEMPLATES = Path(__file__).parent / "templates"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# 개인 링크 서명 키. 환경변수가 없으면 켤 때마다 새로 만든다(앱을 다시 켜면 옛 링크는 안 열림).
LINK_SECRET = os.environ.get("LINK_SECRET", "").encode() or secrets.token_bytes(32)
MAX_TOKEN = 6000


class Member(BaseModel):
    name: str
    email: str
    hours_per_week: Optional[float] = Field(default=None, ge=0)
    good_at: str = ""

    @field_validator("name", "email", "good_at")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("name")
    @classmethod
    def name_needed(cls, v: str) -> str:
        if not v:
            raise ValueError("이름을 넣어 주세요.")
        return v

    @field_validator("email")
    @classmethod
    def email_ok(cls, v: str) -> str:
        if not EMAIL.match(v):
            raise ValueError("메일이 올바르지 않습니다.")
        return v


class PlanRequest(BaseModel):
    notice: str = Field(min_length=1)
    deadline: date
    members: list[Member] = Field(min_length=2, max_length=5)


class Goal(BaseModel):
    id: int
    title: str
    hours: float
    owner: str
    due: date
    done_rule: str


class ApproveRequest(BaseModel):
    deadline: date
    members: list[str] = Field(min_length=2, max_length=5)
    goals: list[Goal] = Field(min_length=1, max_length=50)
    share_board: bool = False  # 팀원에게도 기여도 판을 보여 줄지(팀이 처음에 동의해서 정함)


class SubmitRequest(BaseModel):
    member: str
    goal_id: int
    content: str = Field(min_length=1, max_length=5000)


class ReviewRequest(BaseModel):
    lead: str
    goal_id: int
    decision: Literal["통과", "보완 요청"]
    note: str = Field(default="", max_length=500)


class ClockRequest(BaseModel):
    lead: str
    days: int = Field(default=1, ge=1, le=30)
    reset: bool = False


# 할 일 상태
TODO, WAIT, FIX, PASS = "할 일", "팀장 확인 중", "보완 필요", "통과"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    return (TEMPLATES / "index.html").read_text(encoding="utf-8")


@app.get("/me", response_class=HTMLResponse)
def me_page():
    return (TEMPLATES / "me.html").read_text(encoding="utf-8")


@app.get("/lead", response_class=HTMLResponse)
def lead_page():
    return (TEMPLATES / "lead.html").read_text(encoding="utf-8")


@app.get("/board.js")
def board_js():
    return Response((TEMPLATES / "board.js").read_text(encoding="utf-8"), media_type="text/javascript")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body: bytes) -> bytes:
    return hmac.new(LINK_SECRET, body, hashlib.sha256).digest()[:16]


def make_token(data: dict) -> str:
    body = zlib.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())
    return _b64(body) + "." + _b64(_sign(body))


def read_token(token: str) -> dict:
    try:
        if len(token) > MAX_TOKEN:
            raise ValueError
        a, b = token.split(".")
        body, sig = _unb64(a), _unb64(b)
    except ValueError:
        raise HTTPException(400, "링크가 올바르지 않습니다.")
    if not hmac.compare_digest(sig, _sign(body)):
        raise HTTPException(403, "링크가 올바르지 않거나 바뀌었습니다. 팀장에게 새 링크를 받으세요.")
    return json.loads(zlib.decompress(body))


def today() -> date:
    """진짜 오늘 날짜."""
    return date.today()


MAX_DEMO_DAYS = 60


def team_today(team: dict) -> date:
    """그 팀의 오늘. 시연용 날짜 넘기기로 앞당긴 날수(day_offset)를 더한다."""
    return today() + timedelta(days=team.get("day_offset", 0))


def _role(token: str, role: str) -> dict:
    data = read_token(token)
    if data.get("v") != 2 or data.get("r") != role:
        raise HTTPException(403, "이 화면에 쓰는 링크가 아닙니다.")
    return data


def _team(team_id: str) -> dict:
    team = store.load(team_id)
    if team is None:
        raise HTTPException(404, "팀을 찾을 수 없습니다. 연습용 저장이 지워졌을 수 있습니다.")
    return team


def _goal(team: dict, goal_id: int) -> dict:
    for g in team["goals"]:
        if g["id"] == goal_id:
            return g
    raise HTTPException(404, "그 할 일을 찾을 수 없습니다.")


@app.post("/api/approve")
def approve(req: ApproveRequest, request: Request):
    """팀장이 계획을 승인하면 팀을 저장하고, 팀장 링크와 팀원별 개인 링크를 만든다. 메일은 아직 보내지 않는다."""
    if len(set(req.members)) != len(req.members):
        raise HTTPException(422, "같은 이름이 두 번 들어갔습니다.")
    unknown = {g.owner for g in req.goals} - set(req.members)
    if unknown:
        raise HTTPException(422, f"팀원 명단에 없는 담당자가 있습니다: {', '.join(sorted(unknown))}")
    team_id = secrets.token_urlsafe(9)
    team = {
        "deadline": req.deadline.isoformat(),
        "members": req.members,
        "goals": [{**g.model_dump(), "due": g.due.isoformat()} for g in req.goals],
        "state": {str(g.id): {"status": TODO, "fix_count": 0, "reasons": [], "history": []} for g in req.goals},
        "approved": today().isoformat(),
        "share_board": req.share_board,
    }
    with store.locked():
        store.save(team_id, team)
    base = str(request.base_url)
    links = []
    for name in req.members:
        token = make_token({"v": 2, "r": "member", "t": team_id, "n": name})
        count = sum(1 for g in req.goals if g.owner == name)
        links.append({"name": name, "goals": count, "url": f"{base}me?t={token}"})
    lead = make_token({"v": 2, "r": "lead", "t": team_id})
    return {"team_id": team_id, "lead_url": f"{base}lead?t={lead}", "links": links, "fake_store": store.FAKE}


def _goal_view(g: dict, st: dict, now: date) -> dict:
    return {
        "id": g["id"],
        "title": g["title"],
        "hours": g["hours"],
        "due": g["due"],
        "done_rule": g["done_rule"],
        "status": st["status"],
        "reasons": st["reasons"],
        "fix_count": st["fix_count"],
        "overdue": st["status"] in (TODO, FIX) and date.fromisoformat(g["due"]) < now,
    }


def _clock(team: dict) -> dict:
    return {"today": team_today(team).isoformat(), "day_offset": team.get("day_offset", 0)}


@app.get("/api/today")
def today_goals(member: str):
    """개인 링크 값으로 그 사람의 할 일과 검수 상태만 돌려준다."""
    data = _role(member, "member")
    team = _team(data["t"])
    mine = sorted((g for g in team["goals"] if g["owner"] == data["n"]), key=lambda g: (g["due"], g["id"]))
    now = team_today(team)
    goals = [_goal_view(g, team["state"][str(g["id"])], now) for g in mine]
    return {
        "name": data["n"],
        "deadline": team["deadline"],
        "goals": goals,
        "share_board": team.get("share_board", False),
        **_clock(team),
    }


@app.post("/api/submit")
def submit(req: SubmitRequest):
    """팀원이 결과물을 내면 AI가 완료 기준과 비교한다.
    통과면 바로 통과. 보완 필요나 애매하면 팀장 확인 뒤에 팀원에게 알린다."""
    data = _role(req.member, "member")
    with store.locked():
        team = _team(data["t"])
        g = _goal(team, req.goal_id)
        if g["owner"] != data["n"]:
            raise HTTPException(403, "내 할 일만 낼 수 있습니다.")
        st = team["state"][str(g["id"])]
        if st["status"] in (WAIT, PASS):
            raise HTTPException(409, f"지금은 낼 수 없습니다(상태: {st['status']}).")
        check = ai.check_submission(g["done_rule"], req.content)
        now = team_today(team)
        st["history"].append({
            "at": now.isoformat(),
            "content": req.content,
            "result": check["result"],
            "items": check["items"],
            "fake": check["fake"],
        })
        st["status"] = PASS if check["result"] == "통과" else WAIT
        st["reasons"] = []
        st["on_time"] = now <= date.fromisoformat(g["due"])
        store.save(data["t"], team)
    return {"result": check["result"], "items": check["items"], "status": st["status"], "fake": check["fake"]}


@app.get("/api/review")
def review_list(lead: str):
    """팀장 화면: 모든 할 일의 상태와 마지막 제출, AI 검수 결과."""
    data = _role(lead, "lead")
    team = _team(data["t"])
    now = team_today(team)
    goals = []
    for g in team["goals"]:
        st = team["state"][str(g["id"])]
        view = {**_goal_view(g, st, now), "owner": g["owner"], "last": st["history"][-1] if st["history"] else None}
        goals.append(view)
    return {
        "deadline": team["deadline"],
        "members": team["members"],
        "goals": goals,
        "fake_store": store.FAKE,
        **_clock(team),
    }


@app.post("/api/review")
def review(req: ReviewRequest):
    """팀장이 AI 검수 결과를 확인한다. 보완 요청이면 이유가 꼭 있어야 한다."""
    data = _role(req.lead, "lead")
    with store.locked():
        team = _team(data["t"])
        g = _goal(team, req.goal_id)
        st = team["state"][str(g["id"])]
        if st["status"] != WAIT:
            raise HTTPException(409, f"팀장 확인 중인 할 일이 아닙니다(상태: {st['status']}).")
        last = st["history"][-1]
        if req.decision == "통과":
            st["status"] = PASS
            st["reasons"] = []
            last["lead"] = "통과"
        else:
            reasons = [f"{i['rule']}: {i['why']}" for i in last["items"] if i["ok"] is not True]
            if req.note.strip():
                reasons.append(f"팀장: {req.note.strip()}")
            if not reasons:
                raise HTTPException(422, "보완 이유를 적어 주세요.")
            st["status"] = FIX
            st["reasons"] = reasons
            st["fix_count"] += 1
            last["lead"] = "보완 요청"
        store.save(data["t"], team)
    return _goal_view(g, st, team_today(team))


def contribution(team: dict, now: date) -> dict:
    """기여도 판. 기여도 = 사람별 통과한 예상 시간 합 ÷ 팀 전체 통과 시간 합.
    진행률 = 사람별 통과한 예상 시간 ÷ 맡은 예상 시간."""
    rows = {
        n: {"name": n, "planned": 0.0, "passed": 0.0, "on_time": 0, "late": 0, "fix_count": 0, "overdue": 0}
        for n in team["members"]
    }
    for g in team["goals"]:
        st = team["state"][str(g["id"])]
        r = rows[g["owner"]]
        r["planned"] += g["hours"]
        r["fix_count"] += st["fix_count"]
        if st["status"] == PASS:
            r["passed"] += g["hours"]
            r["on_time" if st.get("on_time", True) else "late"] += 1
        elif st["status"] in (TODO, FIX) and date.fromisoformat(g["due"]) < now:
            r["overdue"] += 1
    team_planned = sum(r["planned"] for r in rows.values())
    team_passed = sum(r["passed"] for r in rows.values())
    out = []
    for r in rows.values():
        r["share"] = round(r["passed"] / team_passed, 3) if team_passed else 0.0
        r["progress"] = round(r["passed"] / r["planned"], 3) if r["planned"] else 0.0
        out.append(r)
    return {
        "today": now.isoformat(),
        "team_planned": team_planned,
        "team_passed": team_passed,
        "contribution": out,
    }


@app.get("/api/status")
def status(t: str):
    """기여도 판. 팀장 링크는 항상, 팀원 링크는 팀이 보여 주기로 정했을 때만 볼 수 있다."""
    data = read_token(t)
    if data.get("v") != 2 or data.get("r") not in ("lead", "member"):
        raise HTTPException(403, "이 화면에 쓰는 링크가 아닙니다.")
    team = _team(data["t"])
    if data["r"] == "member" and not team.get("share_board"):
        raise HTTPException(403, "이 팀은 기여도 판을 팀장만 봅니다.")
    return {**contribution(team, team_today(team)), "share_board": team.get("share_board", False)}


@app.post("/api/clock")
def clock(req: ClockRequest):
    """시연용 날짜 넘기기. 팀장만, 그 팀만 바뀐다. 앞으로만 가고, reset이면 진짜 오늘로 돌아온다."""
    data = _role(req.lead, "lead")
    with store.locked():
        team = _team(data["t"])
        if req.reset:
            team["day_offset"] = 0
        else:
            team["day_offset"] = min(MAX_DEMO_DAYS, team.get("day_offset", 0) + req.days)
        store.save(data["t"], team)
    return {"today": team_today(team).isoformat(), "day_offset": team["day_offset"], "max": MAX_DEMO_DAYS}


@app.post("/api/plan")
def plan(req: PlanRequest):
    return make_schedule(req, today())


def _same(a: str, b: str) -> bool:
    a, b = a.replace(" ", "").lower(), b.replace(" ", "").lower()
    return bool(a) and a in b


def _gap(loads: list[float]) -> float:
    return (max(loads) - min(loads)) / max(loads) if max(loads) else 0.0


def _assign(goals: list[dict], members: list[Member], caps: list) -> list[int]:
    """여러 순서로 나눠 보고, 사람별 합 차이가 20% 안인 것 중 잘하는 일과 가장 많이 맞는 것을 고른다.
    20% 안인 게 없으면 차이가 가장 작은 것을 고른다."""

    def matches(k, i):
        return _same(goals[k]["skill"], members[i].good_at)

    def has_match(k):
        return any(matches(k, i) for i in range(len(members)))

    big_first = sorted(range(len(goals)), key=lambda k: -goals[k]["hours"])
    match_first = sorted(range(len(goals)), key=lambda k: (not has_match(k), -goals[k]["hours"]))

    tries = []
    for order in (match_first, big_first):
        for slack in (2, 1, 0):
            loads = [0.0] * len(members)
            owners = [0] * len(goals)
            for k in order:
                h = goals[k]["hours"]
                fits = [i for i in range(len(members)) if caps[i] is None or loads[i] + h <= caps[i]]
                pool = fits or list(range(len(members)))
                low = min(loads[i] for i in pool)
                near = [i for i in pool if loads[i] <= low + slack]
                match = [i for i in near if matches(k, i)]
                pick = min(match or near, key=lambda i: (loads[i], i))
                owners[k] = pick
                loads[pick] += h
            hit = sum(matches(k, i) for k, i in enumerate(owners))
            tries.append((_gap(loads), hit, owners))

    ok = [t for t in tries if t[0] <= 0.2]
    owners = max(ok, key=lambda t: (t[1], -t[0]))[2] if ok else min(tries, key=lambda t: t[0])[2]
    return _improve(goals, members, caps, owners, matches)


def _improve(goals, members, caps, owners, matches):
    """두 목표의 담당을 바꾸거나 하나를 옮겨서, 차이 20%와 가능 시간을 지키면서
    잘하는 일을 하나라도 받은 사람 수(다음으로 맞은 개수)를 늘린다."""
    n = len(members)

    def loads_of(o):
        loads = [0.0] * n
        for k, i in enumerate(o):
            loads[i] += goals[k]["hours"]
        return loads

    def over(loads):
        return sum(1 for i in range(n) if caps[i] is not None and loads[i] > caps[i])

    def value(o):
        covered = sum(1 for i in range(n) if any(o[k] == i and matches(k, i) for k in range(len(o))))
        return (covered, sum(matches(k, i) for k, i in enumerate(o)))

    limit = max(0.2, _gap(loads_of(owners)))
    base_over = over(loads_of(owners))
    current = value(owners)
    changed = True
    while changed:
        changed = False
        moves = [(a, b) for a in range(len(goals)) for b in range(a + 1, len(goals))]
        moves += [(a, -1 - i) for a in range(len(goals)) for i in range(n)]
        for a, b in moves:
            trial = list(owners)
            if b >= 0:
                trial[a], trial[b] = trial[b], trial[a]
            else:
                trial[a] = -1 - b
            if trial == owners:
                continue
            loads = loads_of(trial)
            if _gap(loads) > limit or over(loads) > base_over:
                continue
            v = value(trial)
            if v > current:
                owners, current, changed = trial, v, True
    return owners


def make_schedule(req: PlanRequest, today: date) -> dict:
    """AI가 쪼갠 목표에 담당자와 마감을 붙인다(판단 규칙: 역할 나누기, 거꾸로 일정)."""
    if req.deadline <= today:
        raise HTTPException(422, "최종 마감일은 내일 이후여야 합니다.")
    emails = [m.email.lower() for m in req.members]
    if len(set(emails)) != len(emails):
        raise HTTPException(422, "같은 메일이 두 번 들어갔습니다.")
    names = [m.name for m in req.members]
    if len(set(names)) != len(names):
        raise HTTPException(422, "같은 이름이 두 번 들어갔습니다. 구분되게 바꿔 주세요(예: 민수A).")

    draft = ai.make_plan(req.notice)
    goals = draft["goals"]
    warnings = list(draft["warnings"])

    # 거꾸로 일정: 모든 목표가 최종 마감 2일 전에 끝나게
    end = req.deadline - timedelta(days=2)
    if end <= today:
        end = req.deadline
        warnings.append("마감까지 3일이 안 돼서 2일 여유를 두지 못했습니다.")
    span = (end - today).days
    stages = sorted({g["stage"] for g in goals})
    if span < len(stages):
        warnings.append("기간이 짧아 같은 날 마감인 단계가 있습니다.")
    stage_due = {
        s: today + timedelta(days=max(1, round(span * (i + 1) / len(stages))))
        for i, s in enumerate(stages)
    }

    # 역할 나누기: 가능 시간 안에서, 잘하는 사람에게 먼저, 사람별 합은 20% 안으로
    members = req.members
    weeks = max(1.0, span / 7)
    caps = [None if m.hours_per_week is None else m.hours_per_week * weeks for m in members]
    owners = _assign(goals, members, caps)
    loads = [0.0] * len(members)
    for k, i in enumerate(owners):
        loads[i] += goals[k]["hours"]

    for i, m in enumerate(members):
        if caps[i] is None:
            warnings.append(f"{m.name}: 가능 시간이 없어 다른 사람과 똑같이 나눴습니다. 팀장 확인 필요")
        elif loads[i] > caps[i]:
            warnings.append(f"{m.name}: 예상 {loads[i]:g}시간이 가능 시간 {caps[i]:g}시간을 넘습니다. 팀장 확인 필요")

    gap = _gap(loads)
    if gap > 0.2:
        avg = sum(loads) / len(loads)
        reason = (
            "가능 시간이 적은 팀원이 있어서"
            if any(c is not None and c < avg for c in caps)
            else "목표 크기가 2–4시간 단위라서"
        )
        warnings.append(f"사람별 예상 시간 차이가 {gap:.0%}로 20%를 넘습니다. 이유: {reason}")

    out_goals = [
        {
            "id": n + 1,
            "title": g["title"],
            "hours": g["hours"],
            "owner": members[owners[n]].name,
            "due": stage_due[g["stage"]].isoformat(),
            "done_rule": g["done_rule"],
        }
        for n, g in enumerate(goals)
    ]
    return {
        "goals": out_goals,
        "loads": [{"name": m.name, "hours": loads[i]} for i, m in enumerate(members)],
        "gap": round(gap, 3),
        "warnings": warnings,
        "fake": draft["fake"],
    }
