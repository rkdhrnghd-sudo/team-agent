"""메일 담당 파일.

SMTP_HOST가 없으면 연습용이다: 실제로 보내지 않고, 보낸 것처럼 기록만 남긴다(팀장 화면 '보낸 메일').
진짜로 보내려면 .env에 SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, MAIL_FROM을 넣는다.
예: Gmail은 SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, 비밀번호는 Google '앱 비밀번호'.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)
TIMEOUT = 10


def is_fake() -> bool:
    return not os.environ.get("SMTP_HOST", "").strip()


def _one_line(s: str) -> str:
    return " ".join(s.split())[:150]


def send(to: str, subject: str, body: str) -> dict:
    """-> {"sent": 실제로 보냈는지, "mode": "연습용" 또는 "SMTP", "error": 실패 이유 또는 None}"""
    if is_fake():
        return {"sent": False, "mode": "연습용", "error": None}
    msg = EmailMessage()
    msg["From"] = os.environ.get("MAIL_FROM", "").strip() or os.environ.get("SMTP_USER", "").strip()
    msg["To"] = to
    msg["Subject"] = _one_line(subject)
    msg.set_content(body)
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(os.environ["SMTP_HOST"].strip(), port, timeout=TIMEOUT) as s:
            s.starttls()
            user = os.environ.get("SMTP_USER", "").strip()
            if user:
                s.login(user, os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return {"sent": True, "mode": "SMTP", "error": None}
    except Exception as e:
        log.warning("메일 보내기 실패: %s", type(e).__name__)
        return {"sent": False, "mode": "SMTP", "error": type(e).__name__}
