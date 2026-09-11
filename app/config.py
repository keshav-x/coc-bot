import json
import sys
from typing import Any, Dict, List, Optional, Tuple

from app.utils.common import get_resource_path
from app.utils.logger import setup_logger

logger = setup_logger("Config")

ASPECT_16_10 = "16_10"
ASPECT_16_9 = "16_9"

_ASPECT_TOLERANCE = 0.03

ASPECT_BASELINE: Dict[str, tuple[int, int]] = {
    ASPECT_16_10: (2560, 1600),
    ASPECT_16_9: (2560, 1440),
}


def resolve_aspect_key(width: int, height: int) -> Optional[str]:
    if width <= 0 or height <= 0:
        return None
    r = width / height
    r16_9 = 16.0 / 9.0
    r16_10 = 1.6
    d9 = abs(r - r16_9)
    d10 = abs(r - r16_10)
    if min(d9, d10) > _ASPECT_TOLERANCE:
        return None
    if d9 < d10:
        return ASPECT_16_9
    return ASPECT_16_10


def _show_window_not_found_dialog(parent, on_configure):
    try:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("ApexClash Pro")
        box.setText("Clash of Clans window not found.\nOpen the game, then press Start.")
        box.setInformativeText(
            "If the game is already open, choose the correct window manually in Settings → Game window."
        )
        config_btn = None
        if on_configure is not None:
            config_btn = box.addButton("Open configuration", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if config_btn is not None and box.clickedButton() is config_btn:
            on_configure()
    except Exception as e:
        logger.error(f"Could not show window-not-found dialog: {e}")


def check_game_window_aspect_for_start(parent=None, on_configure=None) -> bool:
    try:
        from app.services.window import WindowService

        ws = WindowService()
        size = ws.get_outer_pixel_size()
    except Exception as e:
        logger.warning(f"Could not probe game window for aspect ({e}); allowing start.")
        return True

    if size is None:
        _show_window_not_found_dialog(parent, on_configure)
        return False

    w, h = size
    if resolve_aspect_key(w, h) is not None:
        return True

    try:
        from PySide6.QtWidgets import QMessageBox

        msg = "Aspect ratio not supported (resize the game window to ~16:9 or ~16:10)."
        QMessageBox.critical(parent, "ApexClash Pro", msg)
    except Exception as e:
        logger.error(f"Game window aspect not supported (~{w}x{h}). Could not show dialog: {e}")
        print("Aspect ratio not supported", file=sys.stderr)
    return False


def _default_aspect_key():
    try:
        from app.services.window import WindowService

        ws = WindowService()
        if ws.hwnd:
            oz = ws.get_outer_pixel_size()
            if oz:
                w, h = oz
                key = resolve_aspect_key(w, h)
                if key is not None:
                    return key
        return ASPECT_16_10
    except Exception:
        return ASPECT_16_10


class Config:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.data = {}
        self.aspect_key = _default_aspect_key()
        self.ref_width, self.ref_height = ASPECT_BASELINE[self.aspect_key]
        self.width = self.ref_width
        self.height = self.ref_height
        self.load_config()
        self._initialized = True

    def _apply_aspect(self, key):
        if key not in ASPECT_BASELINE:
            key = ASPECT_16_10
        self.aspect_key = key
        rw, rh = ASPECT_BASELINE[key]
        self.ref_width = int(rw)
        self.ref_height = int(rh)

    def set_aspect_for_screen_size(self, width, height):
        if width <= 0 or height <= 0:
            return False
        new_key = resolve_aspect_key(width, height)
        if new_key is None:
            logger.error(f"Unsupported capture aspect (~{width}x{height}); need ~16:9 or ~16:10.")
            return False
        if new_key == self.aspect_key:
            return False
        self._apply_aspect(new_key)
        self.load_config()
        logger.info(
            f"Switched to {self.aspect_key} profile ({self.ref_width}x{self.ref_height} ref)"
        )
        return True

    def load_config(self):
        try:
            config_path = get_resource_path(f"templates/{self.aspect_key}/data.json")
            with open(config_path, "r") as f:
                temp_data = json.load(f)
            self.data = temp_data[0] if isinstance(temp_data, list) else temp_data
            logger.info(
                f"Loaded config profile {self.aspect_key} (ref {self.ref_width}x{self.ref_height}): {config_path.name}"
            )
        except FileNotFoundError:
            logger.error(f"data.json not found for aspect {self.aspect_key}!")
            raise
        except json.JSONDecodeError:
            logger.error("data.json is invalid JSON!")
            raise
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    def set_target_size(self, width, height):
        if width <= 0 or height <= 0:
            return
        self.set_aspect_for_screen_size(width, height)
        self.width = int(width)
        self.height = int(height)

    def set_target_size_from_frame(self, frame):
        if frame is None or getattr(frame, "size", 0) == 0:
            return
        h, w = frame.shape[:2]
        self.set_target_size(int(w), int(h))

    def scale_factors(self, size=None):
        tw, th = size if size is not None else (self.width, self.height)
        return (tw / self.ref_width, th / self.ref_height)

    def template_scale(self, height=None):
        target_h = height if height is not None else self.height
        return target_h / self.ref_height

    def scale_point(self, point, size=None):
        sx, sy = self.scale_factors(size)
        return [int(round(point[0] * sx)), int(round(point[1] * sy))]

    def scale_scalar(self, value, height=None):
        return int(round(value * self.template_scale(height)))

    def get_point(self, key, size=None):
        val = self.data.get(key)
        if not val or not isinstance(val, (list, tuple)) or len(val) < 2:
            raise KeyError(f"Key '{key}' missing or not a two-element point.")
        return self.scale_point([int(val[0]), int(val[1])], size)

    def get_scaled(self, key, default=None, height=None):
        val = self.data.get(key, default)
        if isinstance(val, (int, float)):
            return self.scale_scalar(int(val), height)
        return val
