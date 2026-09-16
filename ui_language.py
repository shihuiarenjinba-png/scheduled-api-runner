from __future__ import annotations

import json
import locale
import os
import tempfile
from pathlib import Path

SUPPORTED_LANGUAGES = {"ja", "en"}


def _default_language() -> str:
    try:
        current = locale.getlocale()[0] or ""
    except Exception:
        current = ""
    return "ja" if current.lower().startswith("ja") else "en"


def _settings_path(app_id: str) -> Path:
    local = os.getenv("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "PrivateAutomation" / "ui" / f"{app_id}.json"


def load_language(app_id: str) -> str:
    override = os.getenv("PRIVATE_AUTOMATION_UI_LANGUAGE", "").strip().lower()
    if override in SUPPORTED_LANGUAGES:
        return override
    path = _settings_path(app_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        value = str(raw.get("language", "")).lower() if isinstance(raw, dict) else ""
        return value if value in SUPPORTED_LANGUAGES else _default_language()
    except (OSError, json.JSONDecodeError):
        return _default_language()


def save_language(app_id: str, language: str) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("language must be 'ja' or 'en'")
    path = _settings_path(app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"language": language}, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
