import pytest


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    """테스트마다 빈 연습용 저장 파일을 쓰고, 진짜 AI는 부르지 않는다(키를 지움)."""
    monkeypatch.setenv("STORE_FILE", str(tmp_path / "store.json"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
