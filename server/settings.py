from __future__ import annotations

import json
from threading import RLock
from typing import Any

from .config import DATA_DIR


SETTINGS_PATH = DATA_DIR / "settings.json"
DEFAULT_CAPTURE_SETTINGS = {
    "enabled": True,
    "hotkey": "ctrl+shift+x",
    "dayMode": "today",
    "lastDay": None,
}
_lock = RLock()


def get_capture_settings() -> dict[str, Any]:
    with _lock:
        stored: dict[str, Any] = {}
        if SETTINGS_PATH.exists():
            try:
                stored = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                stored = {}
        return {**DEFAULT_CAPTURE_SETTINGS, **stored.get("capture", {})}


def update_capture_settings(changes: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        document: dict[str, Any] = {}
        if SETTINGS_PATH.exists():
            try:
                document = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                document = {}
        current = {**DEFAULT_CAPTURE_SETTINGS, **document.get("capture", {})}
        current.update(changes)
        document["capture"] = current
        temporary = SETTINGS_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_PATH)
        return current
