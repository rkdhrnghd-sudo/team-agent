import pytest


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    """테스트마다 빈 연습용 저장 파일을 쓴다."""
    monkeypatch.setenv("STORE_FILE", str(tmp_path / "store.json"))
