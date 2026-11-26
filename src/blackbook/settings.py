"""Local settings of this installation, stored in <repo>/.blackbook/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_DIR / ".blackbook" / "settings.json"


def load() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get(key: str, default=None):
    return load().get(key, default)


def set_value(key: str, value) -> None:
    settings = load()
    settings[key] = value
    save(settings)
