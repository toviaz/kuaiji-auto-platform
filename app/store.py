from __future__ import annotations

import json
import threading
from pathlib import Path

from .config import ROOT

LOCK = threading.Lock()
STATE = ROOT / "data" / "platform" / "state.json"

DEFAULT = {
    "terminals": [
        {
            "id": "local",
            "name": "本机",
            "kind": "local",
            "host": "127.0.0.1",
            "enabled": True,
            "note": "当前这台 Mac，能直接 adb",
        }
    ],
    "devices": [],
    "jobs": [],
}


def _load() -> dict:
    if not STATE.exists():
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(json.dumps(DEFAULT))
    return json.loads(STATE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_state() -> dict:
    with LOCK:
        data = _load()
        data.setdefault("terminals", list(DEFAULT["terminals"]))
        data.setdefault("devices", [])
        data.setdefault("jobs", [])
        return data


def write_state(data: dict) -> dict:
    with LOCK:
        _save(data)
        return data


def update_state(mutator):
    with LOCK:
        data = _load()
        data.setdefault("terminals", list(DEFAULT["terminals"]))
        data.setdefault("devices", [])
        data.setdefault("jobs", [])
        mutator(data)
        _save(data)
        return data
