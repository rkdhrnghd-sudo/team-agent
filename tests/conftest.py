import pytest


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    """테스트마다 빈 연습용 저장 파일을 쓰고, 진짜 AI와 진짜 메일은 부르지 않는다(키와 설정을 지움)."""
    monkeypatch.setenv("STORE_FILE", str(tmp_path / "store.json"))
    for name in ("GEMINI_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM", "CRON_SECRET"):
        monkeypatch.delenv(name, raising=False)
