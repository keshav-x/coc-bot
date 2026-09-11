"""App logo and window icon."""
from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap

from app.utils.common import get_resource_path

_ICON: QIcon | None = None

APP_NAME = "ApexClash Pro"
APP_SUBTITLE = "AUTONOMOUS COMBAT SUITE"
APP_FULL_TITLE = "ApexClash Pro — Autonomous Combat & Farming Suite"

LOGO_PNG = "assets/apex_clash_logo.png"
LOGO_ICO = "assets/apex_clash_logo.ico"
LEGACY_LOGO_PNG = "assets/clash_autoloot_logo.png"
LEGACY_LOGO_ICO = "assets/clash_autoloot_logo.ico"


def app_icon() -> QIcon:
    global _ICON
    if _ICON is not None:
        return _ICON
    for path in (LOGO_ICO, LOGO_PNG, LEGACY_LOGO_ICO, LEGACY_LOGO_PNG):
        f = get_resource_path(path)
        if f.is_file():
            _ICON = QIcon(str(f))
            return _ICON
    _ICON = QIcon()
    return _ICON


def logo_pixmap(size: int = 48) -> QPixmap:
    icon = app_icon()
    if icon.isNull():
        return QPixmap()
    return icon.pixmap(size, size)


def apply_app_icon(widget) -> None:
    icon = app_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)
