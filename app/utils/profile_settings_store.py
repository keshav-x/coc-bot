"""Profile preferences (JSON) under LOCALAPPDATA\\ClashAutoLoot, next to ``player_list.json``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.utils.common import ensure_dir, get_user_app_data_dir

EARTHQUAKE_METHOD_CURVE = "Curve Placement"
EARTHQUAKE_METHOD_RANDOM = "Random Placement"
EARTHQUAKE_METHOD_OPTIONS = (EARTHQUAKE_METHOD_CURVE, EARTHQUAKE_METHOD_RANDOM)
SETTINGS_FILENAME = "settings.json"


@dataclass
class ProfileSettings:
    earthquake_method: str = EARTHQUAKE_METHOD_CURVE


def get_settings_path() -> Path:
    dest = get_user_app_data_dir() / SETTINGS_FILENAME
    ensure_dir(dest.parent)
    return dest


def _normalize_earthquake_method(raw: Any) -> str:
    if raw == EARTHQUAKE_METHOD_RANDOM or raw == EARTHQUAKE_METHOD_CURVE:
        return str(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == "random placement":
            return EARTHQUAKE_METHOD_RANDOM
        if s == "curve placement":
            return EARTHQUAKE_METHOD_CURVE
    return EARTHQUAKE_METHOD_CURVE


def load_profile_settings() -> ProfileSettings:
    path = get_settings_path()
    if not path.is_file():
        return ProfileSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ProfileSettings()
    if not isinstance(raw, dict):
        return ProfileSettings()
    return ProfileSettings(
        earthquake_method=_normalize_earthquake_method(raw.get("earthquake_method"))
    )


def save_profile_settings(settings: ProfileSettings) -> None:
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = ProfileSettings(
        earthquake_method=_normalize_earthquake_method(settings.earthquake_method)
    )
    payload = asdict(normalized)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
