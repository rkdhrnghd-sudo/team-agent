from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app import mail, store
from app.main import REMIND_LIMIT, app

client = TestClient(app)

DEADLINE = (date.today() + timedelta(days=14)).isoformat()
MEMBERS = [{"name": f"팀원{i}", "email": f"m{i}@example.com"} for i in range(3)]
GOOD = "1. 자료 http://a.example\n요약 1\n요약 2\n2. 자료 http://b.example\n요약\n3. 자료 http://c.example\n요약"


def token_of(url):
    return parse_qs(urlparse(url).query)["t"][0]


def setup_team(lead_email="lead@example.com"):
    plan = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": MEMBERS}).json()
    body = client.post("/api/approve", json={
        "deadline": DEADLINE, "members": MEMBERS, "goals": plan["goals"], "lead_email": lead_email,
    }).json()
    return plan["goals"], token_of(body["lead_url"]), {l["name"]: token_of(l["url"]) for l in body["links"]}, body


def outbox(lead):
    return client.get("/api/review", params={"lead": lead}).json()["outbox"]


def count_sends(monkeypatch):
    sent = []
    real = mail.send

    def spy(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
        return real(to, subject, body)

    monkeypatch.setattr(mail, "send", spy)
    return sent


def test_no_mail_before_approve(monkeypatch):
    sent = count_sends(monkeypatch)
    client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": MEMBERS})
    assert sent == []


def test_plan_mail_per_member_on_approve():
    goals, lead, links, body = setup_team()
    assert body["mails"] == 3 and body["fake_mail"] is True
    box = outbox(lead)
    assert sorted(m["email"] for m in box) == sorted(m["email"] for m in MEMBERS)
    for m in box:
        assert m["kind"] == "계획" and m["mode"] == "연습용" and m["sent"] is False
        assert links[m["to"]] in m["body"]  # 자기 개인 링크가 들어 있음
        others = [n for n in links if n != m["to"]]
        assert all(links[o] not in m["body"] for o in others)


def test_approve_rejects_bad_email():
    plan = client.post("/api/plan", json={"notice": "보고서 10쪽, 평가", "deadline": DEADLINE, "members": MEMBERS}).json()
    bad = [{**MEMBERS[0], "email": "nope"}] + MEMBERS[1:]
    assert client.post("/api/approve", json={"deadline": DEADLINE, "members": bad, "goals": plan["goals"]}).status_code == 422
    assert client.post("/api/approve", json={"deadline": DEADLINE, "members": MEMBERS, "goals": plan["goals"], "lead_email": "x"}).status_code == 422


def test_daily_once_per_day():
    goals, lead, links, _ = setup_team()
    first_due = min(date.fromisoformat(g["due"]) for g in goals)
    days = (first_due - date.today()).days - 1  # 첫 마감 하루 전으로
    if days > 0:
        client.post("/api/clock", json={"lead": lead, "days": days})
    before = len(outbox(lead))
    r1 = client.post("/api/daily", json={"lead": lead}).json()
    r2 = client.post("/api/daily", json={"lead": lead}).json()
    assert r2["mails"] == 0
    assert len(outbox(lead)) == before + r1["mails"]


def test_daily_mail_has_at_most_two_goals():
    goals, lead, links, _ = setup_team()
    client.post("/api/clock", json={"lead": lead, "days": 30})
    for m in outbox(lead):
        if m["kind"] == "매일":
            assert m["body"].count("완료 기준:") <= 2


def test_no_reply_after_limit():
    goals, lead, links, body = setup_team()
    client.post("/api/clock", json={"lead": lead, "days": 20})
    review = client.get("/api/review", params={"lead": lead}).json()
    flagged = [g for g in review["goals"] if g["no_reply"]]
    assert flagged and all(g["reminders"] > REMIND_LIMIT for g in flagged)
    full = store.load(body["team_id"])["outbox"]  # 화면은 최근 50통만 보여 줘서 저장된 전체로 셈
    lead_mails = [m for m in full if m["kind"] == "응답 없음"]
    assert len(lead_mails) == len(flagged)  # 할 일마다 한 번만
    assert all(m["email"] == "lead@example.com" for m in lead_mails)
    board = client.get("/api/status", params={"t": lead}).json()
    assert sum(r["no_reply"] for r in board["contribution"]) == len(flagged)


def test_no_lead_mail_without_lead_email():
    goals, lead, links, _ = setup_team(lead_email="")
    client.post("/api/clock", json={"lead": lead, "days": 20})
    assert not [m for m in outbox(lead) if m["kind"] == "응답 없음"]


def test_submitted_goal_not_reminded():
    goals, lead, links, _ = setup_team()
    g = next(x for x in goals if x["title"] == "자료 조사 1")
    client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": GOOD})
    client.post("/api/clock", json={"lead": lead, "days": 20})
    full = store.load(_["team_id"])["outbox"]
    assert all(g["title"] not in m["body"] for m in full if m["kind"] == "매일")


def test_fix_mail_only_after_lead():
    goals, lead, links, _ = setup_team()
    g = next(x for x in goals if x["title"] == "자료 조사 1")
    client.post("/api/submit", json={"member": links[g["owner"]], "goal_id": g["id"], "content": "짧음"})
    assert not [m for m in outbox(lead) if m["kind"] == "보완 요청"]
    client.post("/api/review", json={"lead": lead, "goal_id": g["id"], "decision": "보완 요청", "note": "링크 넣기"})
    fix = [m for m in outbox(lead) if m["kind"] == "보완 요청"]
    assert len(fix) == 1 and fix[0]["to"] == g["owner"]
    assert "팀장: 링크 넣기" in fix[0]["body"] and links[g["owner"]] in fix[0]["body"]


def test_cron(monkeypatch):
    goals, lead, links, _ = setup_team()
    assert client.post("/api/cron/daily").status_code == 404
    monkeypatch.setenv("CRON_SECRET", "s3cret")
    assert client.post("/api/cron/daily", headers={"X-Cron-Secret": "wrong"}).status_code == 403
    assert client.post("/api/cron/daily", headers={"X-Cron-Secret": "s3cret"}).status_code == 200


class FakeSMTP:
    sent = []
    fail = False

    def __init__(self, host, port, timeout):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        pass

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise OSError("down")
        FakeSMTP.sent.append(msg)


def test_smtp_mode(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    out = mail.send("a@example.com", "제목\n줄바꿈", "본문")
    assert out == {"sent": True, "mode": "SMTP", "error": None}
    assert FakeSMTP.sent[0]["Subject"] == "제목 줄바꿈"
    FakeSMTP.fail = True
    out = mail.send("a@example.com", "제목", "본문")
    assert out["sent"] is False and out["error"] == "OSError"
