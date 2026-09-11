"""Manual game-window selection (JSON) under LOCALAPPDATA\\ClashAutoLoot.

Stores a stable identity (window title + top-level class + game-surface child class) so the
correct Google Play Games window can be re-resolved across restarts, even when the HWND changes
or auto-detection picks the wrong window.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.utils.common import ensure_dir, get_user_app_data_dir

WINDOW_SELECTION_FILENAME = "window.json"


@dataclass
class WindowSelection:
    """A user-pinned window identity. Empty fields mean "auto-detect"."""

    title: str = ""
    top_class: str = ""
    child_class: str = ""

    def is_set(self) -> bool:
        return bool(self.title.strip() or self.child_class.strip())


def get_window_selection_path() -> Path:
    dest = get_user_app_data_dir() / WINDOW_SELECTION_FILENAME
    ensure_dir(dest.parent)
    return dest


def load_window_selection() -> WindowSelection:
    path = get_window_selection_path()
    if not path.is_file():
        return WindowSelection()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return WindowSelection()
    if not isinstance(raw, dict):
        return WindowSelection()
    return WindowSelection(
        title=str(raw.get("title", "") or ""),
        top_class=str(raw.get("top_class", "") or ""),
        child_class=str(raw.get("child_class", "") or ""),
    )


def save_window_selection(selection: WindowSelection) -> None:
    path = get_window_selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(selection)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_window_selection() -> None:
    path = get_window_selection_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        save_window_selection(WindowSelection())
