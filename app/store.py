"""저장 담당 파일. 지금은 연습용 임시 저장이다(내 PC의 파일 하나).

배포 전에 서버 밖 저장소(예: DynamoDB)로 바꾼다. 바꿀 때는 아래 load, save, locked 세 개만 바꾸면 된다.
팀 하나 = 문서 하나(dict).
"""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

FAKE = True
_lock = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("STORE_FILE", ".data/store.json"))


def _read_all() -> dict:
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


@contextmanager
def locked():
    """읽고 고쳐서 저장하는 동안 다른 요청이 끼어들지 않게 한다."""
    with _lock:
        yield


def load(team_id: str):
    return _read_all().get(team_id)


def save(team_id: str, team: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _read_all()
    data[team_id] = team
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
