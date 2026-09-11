"""App logo and window icon."""
from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap

from app.utils.common import get_resource_path

_ICON: QIcon | None = None

LOGO_PNG = "assets/clash_autoloot_logo.png"
LOGO_ICO = "assets/clash_autoloot_logo.ico"


def app_icon() -> QIcon:
    global _ICON
    if _ICON is not None:
        return _ICON
    ico = get_resource_path(LOGO_ICO)
    png = get_resource_path(LOGO_PNG)
    if ico.is_file():
        _ICON = QIcon(str(ico))
    elif png.is_file():
        _ICON = QIcon(str(png))
    else:
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
