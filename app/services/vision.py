"""Vision service: template matching and OCR for Clash of Clans bot automation."""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    import pytesseract
    from app.utils.tesseract_env import configure_tesseract
    configure_tesseract()
except ImportError:
    pytesseract = None

from app.config import (
    ASPECT_16_9,
    ASPECT_16_10,
    ASPECT_BASELINE,
    Config,
    resolve_aspect_key,
)
from app.utils.common import (
    ensure_dir,
    get_resource_path,
    get_template_path,
)
from app.utils.logger import setup_logger

logger = setup_logger("VisionService")


@dataclass(frozen=True)
class OcrWordBox:
    """A single word bounding box in **screen** coordinates (matches `screen_img`)."""

    left: int
    top: int
    width: int
    height: int
    text: str
    confidence: float

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


_NUMBERS_HUD_ROI_AT_BASELINE: Dict[str, Tuple[int, int]] = {
    ASPECT_16_10: (600, 400),
    ASPECT_16_9: (550, 350),
}
_MULTIUPGRADE_COST_REDNESS_ABOVE_AT_BASELINE: Dict[str, Tuple[int, int, int]] = {
    ASPECT_16_9: (43, 80, 18),
    ASPECT_16_10: (49, 80, 24),
}
_NUMBERS_REF_LINE_HEIGHT_PX = 30
HUD_TOP_RIGHT_NUMBERS_ROI_UPSCALE = 3.0


@dataclass(frozen=True)
class GroupedNumber:
    """Merged numeric string on one text line (see :meth:`VisionService.extract_grouped_numbers_in_region`)."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


@dataclass(frozen=True)
class UpgradeCostIconRedness:
    """Gold or elixir slot from ``multiupgrade.png`` + redness in the cost box above it."""

    template: str
    found: bool
    match_confidence: float
    redness: float
    cost_roi_xywh: Optional[Tuple[int, int, int, int]]
    center: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class UpgradeCostRednessPair:
    """See :meth:`VisionService.upgrade_cost_redness_by_resource_icons`."""

    gold: UpgradeCostIconRedness
    elixir: UpgradeCostIconRedness


@dataclass(frozen=True)
class GemPromptDetection:
    """Detection result for modal prompts attempting to charge gems."""

    detected: bool
    reason: str = ""
    cancel_point: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class WallUpgradeActionInfo:
    """Action bar buttons and affordability when a wall (or row of walls) is selected on the village map."""

    is_selected: bool = False
    select_row: Optional[Tuple[int, int]] = None
    upgrade_more: Optional[Tuple[int, int]] = None
    elixir_upgrade: Optional[Tuple[int, int]] = None
    gold_upgrade: Optional[Tuple[int, int]] = None
    elixir_affordable: bool = False
    gold_affordable: bool = False


BOTTOM_HALF_BOT_TEMPLATES = frozenset({
    "nightwitch.png",
    "bstar.png",
    "removewall.png",
    "bbstar.png",
    "farmbattle.png",
    "attack.png",
    "removewallfake.png",
    "settings.png",
    "upgrademore.png",
    "upgrademore_card.png",
    "wall_hammer.png",
    "selectrow.png",
    "addwall.png",
    "rankedbattle.png",
    "addwallfake.png",
    "rankedattackconfirm.png",
    "attack2.png",
    "battlemachine.png",
    "findnow.png",
    "babydragon.png",
    "surrender.png",
    "flyingmachine.png",
    "endbattle.png",
})

TOP_HALF_BOT_TEMPLATES = frozenset({
    "gbuilder.png",
    "builder.png",
    "fullecart.png",
    "mbuilder.png",
    "fullecart2.png",
    "fullecart3.png",
})

_WHITE_TEXT_BRIGHTNESS_FLOOR = 190

_CC_INK_AREA_AT_BASELINE: Dict[str, Tuple[int, int]] = {
    ASPECT_16_10: (100, 600),
    ASPECT_16_9: (80, 500),
}

_TOP_CENTER_MENU_SQUARE_SIDE_AT_BASELINE: Dict[str, int] = {
    ASPECT_16_10: 1400,
    ASPECT_16_9: 1260,
}

_WALL_MENU_LETTER_CC_AT_BASELINE: Dict[str, Tuple[int, int]] = {
    ASPECT_16_10: (40, 400),
    ASPECT_16_9: (30, 350),
}


class VisionService:
    """Handles image recognition and processing."""

    _tesseract_missing_logged: bool = False

    @staticmethod
    def _log_tesseract_missing() -> None:
        """Log the Tesseract-not-found error once (subsequent calls are silent)."""
        if VisionService._tesseract_missing_logged:
            return
        VisionService._tesseract_missing_logged = True
        logger.error(
            "Tesseract executable not found; OCR is disabled and all word/number reads "
            "will return empty. Install Tesseract and ensure it is on PATH or bundled "
            "(e.g. Windows installer from UB Mannheim). This is logged once per run."
        )

    @staticmethod
    def _template_scale_xy(screen_img: np.ndarray) -> Tuple[float, float]:
        """Scale from authored ref (:attr:`Config.ref_width` / :attr:`Config.ref_height`) to ``screen_img``."""
        h, w = screen_img.shape[:2]
        cfg = Config()
        return (w / cfg.ref_width, h / cfg.ref_height)

    @staticmethod
    def _resize_template_for_screen(template: np.ndarray, screen_img: np.ndarray) -> np.ndarray:
        """Resize reference PNG templates to match the current capture resolution.

        Uses :meth:`_template_scale_xy`. When scale is ~1.0, returns ``template`` unchanged.
        """
        sx, sy = VisionService._template_scale_xy(screen_img)
        if abs(sx - 1.0) < 0.001 and abs(sy - 1.0) < 0.001:
            return template
        t_h, t_w = template.shape[:2]
        new_w = max(1, int(round(t_w * sx)))
        new_h = max(1, int(round(t_h * sy)))
        interp = cv2.INTER_AREA if min(sx, sy) < 1.0 else cv2.INTER_CUBIC
        return cv2.resize(template, (new_w, new_h), interpolation=interp)

    @staticmethod
    def bottom_half_region(screen_img: np.ndarray) -> Tuple[int, int, int, int]:
        """ROI (x, y, w, h) covering the bottom half of the screen."""
        h, w = screen_img.shape[:2]
        y0 = h // 2
        return (0, y0, w, h - y0)

    @staticmethod
    def top_half_region(screen_img: np.ndarray) -> Tuple[int, int, int, int]:
        """ROI (x, y, w, h) covering the top half of the screen."""
        h, w = screen_img.shape[:2]
        y1 = h // 2
        return (0, 0, w, y1)

    @staticmethod
    def right_half_region(screen_img: np.ndarray) -> Tuple[int, int, int, int]:
        """ROI (x, y, w, h) covering the right half of the screen."""
        h, w = screen_img.shape[:2]
        x0 = w // 2
        return (x0, 0, w - x0, h)

    @staticmethod
    def top_right_quadrant_region(screen_img: np.ndarray) -> Tuple[int, int, int, int]:
        """ROI (x, y, w, h) covering the top-right quarter of the screen."""
        h, w = screen_img.shape[:2]
        x0 = w // 2
        y1 = h // 2
        return (x0, 0, w - x0, y1)

    @staticmethod
    def find_image_in_frame(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
    ) -> Optional[Tuple[int, int]]:
        """Finds center (x, y) of template in frame, or None if not found."""
        if not template_name.endswith(".png"):
            template_name = f"{template_name}.png"
        x, y = VisionService.find_template(screen_img, template_name, threshold=threshold)
        if x is not None and y is not None:
            return (x, y)
        return None

    @staticmethod
    def find_template(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        scale_template: bool = True,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Finds a single occurrence of a template in the screen image.

        Args:
            screen_img: The full screenshot to search within.
            template_name: The filename of the template to search for.
            threshold: The match confidence threshold (0.0 to 1.0).
            region: Optional (x, y, w, h) region to search within.
            scale_template: Whether to scale the template for current capture resolution.

        Returns:
            Tuple of (center_x, center_y) if found, else (None, None).
        """
        try:
            template_path = get_template_path(template_name)
            if not template_path.exists():
                logger.error(f"Template not found: {template_path}")
                return (None, None)

            template = cv2.imread(str(template_path))
            if template is None:
                logger.error(f"Failed to load template image: {template_path}")
                return (None, None)

            if scale_template:
                template = VisionService._resize_template_for_screen(template, screen_img)

            if region:
                x, y, w, h = region
                h_screen, w_screen = screen_img.shape[:2]
                if x + w > w_screen or y + h > h_screen:
                    logger.warning(f"Region {region} out of bounds for image size {w_screen}x{h_screen}")
                    return (None, None)
                search_img = screen_img[y : y + h, x : x + w]
                offset_x, offset_y = x, y
            else:
                search_img = screen_img
                offset_x, offset_y = 0, 0

            t_h, t_w = template.shape[:2]
            s_h, s_w = search_img.shape[:2]
            if t_w > s_w or t_h > s_h:
                return (None, None)

            result = cv2.matchTemplate(search_img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < threshold:
                return (None, None)

            center_x = offset_x + max_loc[0] + t_w // 2
            center_y = offset_y + max_loc[1] + t_h // 2
            return (center_x, center_y)

        except Exception as e:
            logger.error(f"Error in find_template: {e}")
            return (None, None)

    @staticmethod
    def find_template_with_confidence(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        scale_template: bool = True,
    ) -> Tuple[Optional[int], Optional[int], float]:
        """Finds a template and returns (center_x, center_y, confidence).

        If confidence is below threshold, returns (None, None, max_val).
        """
        try:
            template_path = get_template_path(template_name)
            if not template_path.exists():
                logger.error(f"Template not found: {template_path}")
                return (None, None, 0.0)

            template = cv2.imread(str(template_path))
            if template is None:
                logger.error(f"Failed to load template image: {template_path}")
                return (None, None, 0.0)

            if scale_template:
                template = VisionService._resize_template_for_screen(template, screen_img)

            if region:
                x, y, w, h = region
                h_screen, w_screen = screen_img.shape[:2]
                if x + w > w_screen or y + h > h_screen:
                    logger.warning(f"Region {region} out of bounds for image size {w_screen}x{h_screen}")
                    return (None, None, 0.0)
                search_img = screen_img[y : y + h, x : x + w]
                offset_x, offset_y = x, y
            else:
                search_img = screen_img
                offset_x, offset_y = 0, 0

            t_h, t_w = template.shape[:2]
            s_h, s_w = search_img.shape[:2]
            if t_w > s_w or t_h > s_h:
                return (None, None, 0.0)

            result = cv2.matchTemplate(search_img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < threshold:
                return (None, None, float(max_val))

            center_x = offset_x + max_loc[0] + t_w // 2
            center_y = offset_y + max_loc[1] + t_h // 2
            return (center_x, center_y, float(max_val))

        except Exception as e:
            logger.error(f"Error in find_template_with_confidence: {e}")
            return (None, None, 0.0)

    @staticmethod
    def find_all_template_centers(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        max_matches: int = 12,
        suppress_pad_frac: float = 0.5,
    ) -> List[Tuple[int, int]]:
        """All non-overlapping template hits as ``(center_x, center_y)`` in screen coords."""
        matches = VisionService._find_template_matches(
            screen_img,
            template_name,
            threshold,
            region,
            max_matches=max_matches,
            suppress_pad_frac=suppress_pad_frac,
        )
        return [
            (int(left) + int(tw) // 2, int(top) + int(th) // 2)
            for left, top, tw, th, _score in matches
        ]

    @staticmethod
    def _template_best_match(
        screen_img: np.ndarray,
        template_name: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        scale_template: bool = True,
    ) -> Tuple[float, Optional[int], Optional[int]]:
        """Best ``TM_CCOEFF_NORMED`` score and match center ``(score, cx, cy)``."""
        try:
            template_path = get_template_path(template_name)
            if not template_path.exists():
                return (0.0, None, None)

            template = cv2.imread(str(template_path))
            if template is None:
                return (0.0, None, None)

            if scale_template:
                template = VisionService._resize_template_for_screen(template, screen_img)

            if region:
                x, y, w, h = region
                h_screen, w_screen = screen_img.shape[:2]
                if x + w > w_screen or y + h > h_screen:
                    return (0.0, None, None)
                search_img = screen_img[y : y + h, x : x + w]
                offset_x, offset_y = x, y
            else:
                search_img = screen_img
                offset_x, offset_y = 0, 0

            t_h, t_w = template.shape[:2]
            s_h, s_w = search_img.shape[:2]
            if t_w > s_w or t_h > s_h:
                return (0.0, None, None)

            result = cv2.matchTemplate(search_img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            center_x = offset_x + max_loc[0] + t_w // 2
            center_y = offset_y + max_loc[1] + t_h // 2
            return (float(max_val), center_x, center_y)

        except Exception as e:
            logger.error(f"Error in _template_best_match ({template_name}): {e}")
            return (0.0, None, None)

    @staticmethod
    def find_active_over_disabled_template(
        screen_img: np.ndarray,
        active_template: str,
        disabled_template: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        threshold: float = 0.8,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Match active vs disabled (grayed/red) UI variants and pick the winner."""
        disabled_path = get_template_path(disabled_template)
        if not disabled_path.exists():
            return VisionService.find_template(
                screen_img, active_template, threshold=threshold, region=region
            )

        active_score, ax, ay = VisionService._template_best_match(
            screen_img, active_template, region=region
        )
        disabled_score, dx, dy = VisionService._template_best_match(
            screen_img, disabled_template, region=region
        )

        best_score = -1.0
        best_is_active = False
        best_x = None
        best_y = None

        for score, x, y, is_active in (
            (active_score, ax, ay, True),
            (disabled_score, dx, dy, False),
        ):
            if score >= threshold and x is not None and y is not None:
                if score > best_score:
                    best_score = score
                    best_is_active = is_active
                    best_x = x
                    best_y = y

        if not best_is_active or best_x is None or best_y is None:
            return (None, None)

        return (best_x, best_y)

    @staticmethod
    def lime_fraction(
        bgr: np.ndarray,
        hue_lo: int = 35,
        hue_hi: int = 90,
        sat_floor: int = 80,
        val_floor: int = 80,
    ) -> float:
        """Fraction of pixels in lime/chartreuse hue (OpenCV H 0–179)."""
        if bgr is None or bgr.size == 0:
            return 0.0
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        mask = (h >= hue_lo) & (h <= hue_hi) & (s >= sat_floor) & (v >= val_floor)
        return float(np.count_nonzero(mask) / mask.size)

    @staticmethod
    def find_active_addwall(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        template_threshold: float = 0.75,
        lime_threshold: float = 0.3,
        max_matches: int = 32,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Locate an active (lime green) add-wall control via ``addwall.png``."""
        matches = VisionService._find_template_matches(
            screen_img,
            "addwall.png",
            template_threshold,
            region,
            max_matches=max_matches,
        )
        if not matches:
            return (None, None)

        frame_h, frame_w = screen_img.shape[:2]
        passing = []
        for left, top, tw, th, _score in matches:
            x0 = max(0, min(int(left), frame_w))
            y0 = max(0, min(int(top), frame_h))
            x1 = max(0, min(int(left) + int(tw), frame_w))
            y1 = max(0, min(int(top) + int(th), frame_h))
            crop = screen_img[y0:y1, x0:x1]
            if VisionService.lime_fraction(crop) < lime_threshold:
                continue
            passing.append((int(left) + int(tw) // 2, int(top) + int(th) // 2))

        if not passing:
            return (None, None)
        return min(passing, key=lambda pt: pt[0])

    @staticmethod
    def yellow_fraction(
        bgr: np.ndarray,
        hue_lo: int = 18,
        hue_hi: int = 40,
        sat_floor: int = 80,
        val_floor: int = 80,
    ) -> float:
        """Fraction of pixels in yellow hue (OpenCV H 0–179)."""
        if bgr is None or bgr.size == 0:
            return 0.0
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        mask = (h >= hue_lo) & (h <= hue_hi) & (s >= sat_floor) & (v >= val_floor)
        return float(np.count_nonzero(mask) / mask.size)

    @staticmethod
    def pink_fraction(
        bgr: np.ndarray,
        hue_lo: int = 130,
        hue_hi: int = 175,
        sat_floor: int = 80,
        val_floor: int = 80,
    ) -> float:
        """Fraction of pixels in pink/magenta hue (OpenCV H 0–179)."""
        if bgr is None or bgr.size == 0:
            return 0.0
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        mask = (h >= hue_lo) & (h <= hue_hi) & (s >= sat_floor) & (v >= val_floor)
        return float(np.count_nonzero(mask) / mask.size)

    @staticmethod
    def find_active_hgoldfull(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        template_threshold: float = 0.85,
        yellow_threshold: float = 0.3,
        max_matches: int = 8,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Locate a full gold storage hero-bar icon via ``hgoldfull.png``."""
        matches = VisionService._find_template_matches(
            screen_img,
            "hgoldfull.png",
            template_threshold,
            region,
            max_matches=max_matches,
        )
        if not matches:
            return (None, None)

        frame_h, frame_w = screen_img.shape[:2]
        passing = []
        for left, top, tw, th, _score in matches:
            x0 = max(0, min(int(left), frame_w))
            y0 = max(0, min(int(top), frame_h))
            x1 = max(0, min(int(left) + int(tw), frame_w))
            y1 = max(0, min(int(top) + int(th), frame_h))
            crop = screen_img[y0:y1, x0:x1]
            if VisionService.yellow_fraction(crop) < yellow_threshold:
                continue
            passing.append((int(left) + int(tw) // 2, int(top) + int(th) // 2))

        if not passing:
            return (None, None)
        return min(passing, key=lambda pt: pt[0])

    @staticmethod
    def find_active_helixirfull(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        template_threshold: float = 0.85,
        pink_threshold: float = 0.3,
        max_matches: int = 8,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Locate a full elixir storage hero-bar icon via ``helixirfull.png``."""
        matches = VisionService._find_template_matches(
            screen_img,
            "helixirfull.png",
            template_threshold,
            region,
            max_matches=max_matches,
        )
        if not matches:
            return (None, None)

        frame_h, frame_w = screen_img.shape[:2]
        passing = []
        for left, top, tw, th, _score in matches:
            x0 = max(0, min(int(left), frame_w))
            y0 = max(0, min(int(top), frame_h))
            x1 = max(0, min(int(left) + int(tw), frame_w))
            y1 = max(0, min(int(top) + int(th), frame_h))
            crop = screen_img[y0:y1, x0:x1]
            if VisionService.pink_fraction(crop) < pink_threshold:
                continue
            passing.append((int(left) + int(tw) // 2, int(top) + int(th) // 2))

        if not passing:
            return (None, None)
        return min(passing, key=lambda pt: pt[0])

    @staticmethod
    def find_active_removewall(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        template_threshold: float = 0.75,
        yellow_threshold: float = 0.3,
        max_matches: int = 32,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Locate an active (yellow) remove-wall control via ``removewall.png``."""
        matches = VisionService._find_template_matches(
            screen_img,
            "removewall.png",
            template_threshold,
            region,
            max_matches=max_matches,
        )
        if not matches:
            return (None, None)

        frame_h, frame_w = screen_img.shape[:2]
        passing = []
        for left, top, tw, th, _score in matches:
            x0 = max(0, min(int(left), frame_w))
            y0 = max(0, min(int(top), frame_h))
            x1 = max(0, min(int(left) + int(tw), frame_w))
            y1 = max(0, min(int(top) + int(th), frame_h))
            crop = screen_img[y0:y1, x0:x1]
            if VisionService.yellow_fraction(crop) < yellow_threshold:
                continue
            passing.append((int(left) + int(tw) // 2, int(top) + int(th) // 2))

        if not passing:
            return (None, None)
        return min(passing, key=lambda pt: pt[0])

    @staticmethod
    def scaled_multiupgrade_cost_redness_above(
        screen_w: int, screen_h: int
    ) -> Tuple[int, int, int]:
        """Vertical center-to-center offset and roi dimensions for cost box above multiupgrade."""
        key = resolve_aspect_key(screen_w, screen_h)
        c_off, rw, rh = _MULTIUPGRADE_COST_REDNESS_ABOVE_AT_BASELINE.get(
            key, _MULTIUPGRADE_COST_REDNESS_ABOVE_AT_BASELINE[ASPECT_16_9]
        )
        base_dim = ASPECT_BASELINE.get(key, ASPECT_BASELINE[ASPECT_16_9])
        scale = screen_h / base_dim[1]
        return (
            max(1, int(round(c_off * scale))),
            max(1, int(round(rw * scale))),
            max(1, int(round(rh * scale))),
        )

    @staticmethod
    def red_hue_fraction(
        bgr: np.ndarray,
        *,
        sat_floor: int = 80,
        val_floor: int = 80,
    ) -> float:
        """Fraction of pixels whose hue falls in red/orange-red ranges (OpenCV H 0–179)."""
        if bgr is None or bgr.size == 0:
            return 0.0
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        mask = ((h <= 10) | (h >= 170)) & (s >= sat_floor) & (v >= val_floor)
        return float(np.count_nonzero(mask) / mask.size)

    @staticmethod
    def _clip_rect_xywh(
        x: int, y: int, w: int, h: int, frame_w: int, frame_h: int
    ) -> Optional[Tuple[int, int, int, int]]:
        x0 = max(0, min(x, frame_w))
        y0 = max(0, min(y, frame_h))
        x1 = max(0, min(x + w, frame_w))
        y1 = max(0, min(y + h, frame_h))
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def _match_template_top_left(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        scale_template: bool = True,
    ) -> Tuple[Optional[int], Optional[int], int, int, float]:
        """Best ``cv2.matchTemplate`` match: ``(left, top, t_w, t_h, score)``."""
        try:
            template_path = get_template_path(template_name)
            if not template_path.exists():
                return (None, None, 0, 0, 0.0)

            template = cv2.imread(str(template_path))
            if template is None:
                return (None, None, 0, 0, 0.0)

            if scale_template:
                template = VisionService._resize_template_for_screen(template, screen_img)

            if region:
                x, y, w, h = region
                h_screen, w_screen = screen_img.shape[:2]
                if x + w > w_screen or y + h > h_screen:
                    return (None, None, 0, 0, 0.0)
                search_img = screen_img[y : y + h, x : x + w]
                offset_x, offset_y = x, y
            else:
                search_img = screen_img
                offset_x, offset_y = 0, 0

            t_h, t_w = template.shape[:2]
            s_h, s_w = search_img.shape[:2]
            if t_w > s_w or t_h > s_h:
                return (None, None, 0, 0, 0.0)

            result = cv2.matchTemplate(search_img, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val < threshold:
                return (None, None, t_w, t_h, float(max_val))

            left = offset_x + max_loc[0]
            top = offset_y + max_loc[1]
            return (left, top, t_w, t_h, float(max_val))

        except Exception as e:
            logger.error(f"Error in _match_template_top_left: {e}")
            return (None, None, 0, 0, 0.0)

    @staticmethod
    def _find_template_matches(
        screen_img: np.ndarray,
        template_name: str,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        scale_template: bool = True,
        max_matches: int = 12,
        suppress_pad_frac: float = 0.5,
    ) -> List[Tuple[int, int, int, int, float]]:
        """Up to ``max_matches`` non-overlapping ``matchTemplate`` hits ``(left, top, tw, th, score)``."""
        try:
            template_path = get_template_path(template_name)
            if not template_path.exists():
                return []

            template = cv2.imread(str(template_path))
            if template is None:
                return []

            if scale_template:
                template = VisionService._resize_template_for_screen(template, screen_img)

            if region:
                x, y, w, h = region
                h_screen, w_screen = screen_img.shape[:2]
                if x + w > w_screen or y + h > h_screen:
                    return []
                search_img = screen_img[y : y + h, x : x + w]
                offset_x, offset_y = x, y
            else:
                search_img = screen_img
                offset_x, offset_y = 0, 0

            t_h, t_w = template.shape[:2]
            s_h, s_w = search_img.shape[:2]
            if t_w > s_w or t_h > s_h:
                return []

            res = cv2.matchTemplate(search_img, template, cv2.TM_CCOEFF_NORMED)
            matches = []
            pad_x = max(1, int(round(t_w * suppress_pad_frac)))
            pad_y = max(1, int(round(t_h * suppress_pad_frac)))

            for _ in range(max_matches):
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if max_val < threshold:
                    break
                mx, my = max_loc
                left = offset_x + mx
                top = offset_y + my
                matches.append((left, top, t_w, t_h, float(max_val)))

                # Suppress neighborhood in result map
                x0 = max(0, mx - pad_x)
                y0 = max(0, my - pad_y)
                x1 = min(res.shape[1], mx + pad_x)
                y1 = min(res.shape[0], my + pad_y)
                res[y0:y1, x0:x1] = -1.0

            return matches

        except Exception as e:
            logger.error(f"Error in _find_template_matches: {e}")
            return []

    @staticmethod
    def _upgrade_cost_redness_for_template_rect(
        screen_img: np.ndarray,
        left: int,
        top: int,
        tw: int,
        th: int,
        conf: float,
        *,
        center_offset: int,
        roi_w: int,
        roi_h: int,
        frame_w: int,
        frame_h: int,
    ) -> UpgradeCostIconRedness:
        """Measure :meth:`red_hue_fraction` in an ``roi_w×roi_h`` area above the template."""
        cx = left + tw // 2
        cy = top + th // 2
        box_cy = cy - center_offset
        box_x = cx - roi_w // 2
        box_y = box_cy - roi_h // 2
        clipped = VisionService._clip_rect_xywh(box_x, box_y, roi_w, roi_h, frame_w, frame_h)
        if clipped is None:
            return UpgradeCostIconRedness(
                template="multiupgrade.png",
                found=True,
                match_confidence=conf,
                redness=0.0,
                cost_roi_xywh=None,
                center=(cx, cy),
            )
        bx, by, bw, bh = clipped
        crop = screen_img[by : by + bh, bx : bx + bw]
        red = VisionService.red_hue_fraction(crop)
        return UpgradeCostIconRedness(
            template="multiupgrade.png",
            found=True,
            match_confidence=conf,
            redness=red,
            cost_roi_xywh=(bx, by, bw, bh),
            center=(cx, cy),
        )

    @staticmethod
    def upgrade_cost_redness_by_resource_icons(
        screen_img: np.ndarray,
        match_threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> UpgradeCostRednessPair:
        """Locate ``multiupgrade.png`` (up to two matches), then score cost box redness."""
        miss = UpgradeCostIconRedness(
            template="multiupgrade.png",
            found=False,
            match_confidence=0.0,
            redness=0.0,
            cost_roi_xywh=None,
            center=None,
        )
        if screen_img is None or getattr(screen_img, "size", 0) == 0:
            return UpgradeCostRednessPair(gold=miss, elixir=miss)

        cfg = Config()
        cfg.set_target_size_from_frame(screen_img)
        frame_h, frame_w = screen_img.shape[:2]
        center_offset, roi_w, roi_h = VisionService.scaled_multiupgrade_cost_redness_above(
            frame_w, frame_h
        )
        matches = VisionService._find_template_matches(
            screen_img,
            "multiupgrade.png",
            match_threshold,
            region,
            max_matches=2,
        )
        if not matches:
            return UpgradeCostRednessPair(gold=miss, elixir=miss)

        def for_rect(left: int, top: int, tw: int, th: int, conf: float) -> UpgradeCostIconRedness:
            return VisionService._upgrade_cost_redness_for_template_rect(
                screen_img,
                left,
                top,
                tw,
                th,
                conf,
                center_offset=center_offset,
                roi_w=roi_w,
                roi_h=roi_h,
                frame_w=frame_w,
                frame_h=frame_h,
            )

        if len(matches) == 1:
            left, top, tw, th, conf = matches[0]
            half = max(1, tw // 2)
            gold = for_rect(left, top, half, th, conf)
            elixir = for_rect(left + half, top, tw - half, th, conf)
        else:
            matches = sorted(matches, key=lambda m: m[0])
            gold = for_rect(*matches[0])
            elixir = for_rect(*matches[1])

        return UpgradeCostRednessPair(gold=gold, elixir=elixir)

    @staticmethod
    def preprocess_bw_ui_text(
        bgr: np.ndarray,
        *,
        white_text: bool = True,
        brightness_floor: int = _WHITE_TEXT_BRIGHTNESS_FLOOR,
    ) -> np.ndarray:
        """Normalize high-contrast UI text to **black glyphs on white background**."""
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if white_text:
            _, binary = cv2.threshold(gray, brightness_floor, 255, cv2.THRESH_BINARY)
            return cv2.bitwise_not(binary)
        _, binary = cv2.threshold(gray, brightness_floor, 255, cv2.THRESH_BINARY)
        return binary

    @staticmethod
    def filter_binary_ink_by_component_area(
        binary: np.ndarray,
        min_area: int = 150,
        max_area: int = 800,
        ink_value: int = 0,
        background_value: int = 255,
    ) -> np.ndarray:
        """On a single-channel binary image, remove connected components outside area bounds."""
        if binary.ndim != 2:
            return binary
        fg_mask = np.uint8(binary == ink_value) * 255
        n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg_mask, connectivity=8)
        out_fg = np.zeros_like(fg_mask)
        for label in range(1, n_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            if min_area <= area <= max_area:
                out_fg[labels == label] = 255
        out = np.full_like(binary, background_value)
        out[out_fg == 255] = ink_value
        return out

    @staticmethod
    def scaled_cc_ink_bounds(screen_w: int, screen_h: int) -> Tuple[int, int]:
        """``(min_area, max_area)`` for :meth:`filter_binary_ink_by_component_area`."""
        key = resolve_aspect_key(screen_w, screen_h)
        base_lo, base_hi = _CC_INK_AREA_AT_BASELINE.get(
            key, _CC_INK_AREA_AT_BASELINE[ASPECT_16_9]
        )
        base_dim = ASPECT_BASELINE.get(key, ASPECT_BASELINE[ASPECT_16_9])
        scale = (screen_h / base_dim[1]) ** 2
        return (max(1, int(round(base_lo * scale))), max(2, int(round(base_hi * scale))))

    @staticmethod
    def scaled_top_center_menu_side(screen_w: int, screen_h: int) -> int:
        """Square side length (px) for :meth:`top_middle_square_roi`."""
        key = resolve_aspect_key(screen_w, screen_h)
        base = _TOP_CENTER_MENU_SQUARE_SIDE_AT_BASELINE.get(
            key, _TOP_CENTER_MENU_SQUARE_SIDE_AT_BASELINE[ASPECT_16_9]
        )
        base_dim = ASPECT_BASELINE.get(key, ASPECT_BASELINE[ASPECT_16_9])
        scale = screen_h / base_dim[1]
        return max(10, int(round(base * scale)))

    @staticmethod
    def scaled_wall_menu_cc_ink_bounds(screen_w: int, screen_h: int) -> Tuple[int, int]:
        """``(min_area, max_area)`` for wall / builder-menu letter filtering."""
        key = resolve_aspect_key(screen_w, screen_h)
        base_lo, base_hi = _WALL_MENU_LETTER_CC_AT_BASELINE.get(
            key, _WALL_MENU_LETTER_CC_AT_BASELINE[ASPECT_16_9]
        )
        base_dim = ASPECT_BASELINE.get(key, ASPECT_BASELINE[ASPECT_16_9])
        scale = (screen_h / base_dim[1]) ** 2
        return (max(1, int(round(base_lo * scale))), max(2, int(round(base_hi * scale))))

    @staticmethod
    def _ocr_query_matches(
        raw: str,
        query_norm: str,
        *,
        case_sensitive: bool = False,
        match_alnum_only: bool = False,
        fuzzy_min_ratio: Optional[float] = None,
    ) -> bool:
        if not query_norm:
            return True

        def norm_text(s: str) -> str:
            s = s.strip()
            return s if case_sensitive else s.lower()

        r = norm_text(raw)
        if not r:
            return False

        if match_alnum_only:
            ar = re.sub(r"[^a-z0-9]", "", r.lower())
            aq = re.sub(r"[^a-z0-9]", "", query_norm.lower())
            if aq and aq in ar:
                return True
        elif query_norm in r:
            return True

        if fuzzy_min_ratio is not None and fuzzy_min_ratio > 0.0:
            cr = re.sub(r"[^a-z0-9]", "", r.lower()) if match_alnum_only else r
            cq = re.sub(r"[^a-z0-9]", "", query_norm.lower()) if match_alnum_only else query_norm
            lo, hi = min(len(cq), len(cr)), max(len(cq), len(cr))
            if hi and (lo / hi) < 0.5:
                return False
            ratio = difflib.SequenceMatcher(None, cq, cr).ratio()
            if ratio >= fuzzy_min_ratio:
                return True

        return False

    @staticmethod
    def _ocr_username_match_tier(
        raw: str,
        query_norm: str,
        *,
        case_sensitive: bool = False,
        match_alnum_only: bool = False,
        fuzzy_min_ratio: Optional[float] = None,
    ) -> int:
        """Rank how well ``raw`` matches the username (higher is better)."""
        if not query_norm:
            return 0

        def norm_text(s: str) -> str:
            s = s.strip()
            return s if case_sensitive else s.lower()

        r = norm_text(raw)
        ar = re.sub(r"[^a-z0-9]", "", r.lower()) if match_alnum_only else ""
        aq = re.sub(r"[^a-z0-9]", "", query_norm.lower()) if match_alnum_only else ""

        if match_alnum_only and aq and aq in ar:
            return 3
        if query_norm in r:
            return 2
        if match_alnum_only and aq and ar and ar in aq:
            if len(ar) >= max(4, int(0.55 * len(aq))):
                return 1
        return 0

    @staticmethod
    def save_hud_ocr_debug_outputs(
        pil_mono: Image.Image,
        mono_gray: np.ndarray,
        tess_data: dict,
        tsv_path: Optional[Path] = None,
        boxes_png_path: Optional[Path] = None,
    ) -> None:
        """Write Tesseract ``image_to_tsv`` and a word-level bounding box overlay image for debugging."""
        if tsv_path is not None and pytesseract is not None:
            try:
                ensure_dir(tsv_path.parent)
                tsv_text = pytesseract.image_to_tsv(pil_mono, config="--psm 6")
                tsv_path.write_text(tsv_text, encoding="utf-8")
            except Exception as exc:
                logger.warning(f"Could not write HUD OCR debug TSV {tsv_path}: {exc}")

        if boxes_png_path is not None:
            try:
                ensure_dir(boxes_png_path.parent)
                vis = cv2.cvtColor(mono_gray, cv2.COLOR_GRAY2BGR)
                n = len(tess_data.get("text", []))
                for i in range(n):
                    raw = str(tess_data["text"][i] or "").strip()
                    if not raw:
                        continue
                    x = int(tess_data["left"][i])
                    y = int(tess_data["top"][i])
                    w = int(tess_data["width"][i])
                    h = int(tess_data["height"][i])
                    try:
                        conf = float(tess_data["conf"][i])
                    except (ValueError, TypeError):
                        conf = -1.0
                    cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 1)
                    lbl = f"{raw} ({conf:.0f})" if conf >= 0 else raw
                    cv2.putText(
                        vis,
                        lbl,
                        (x, max(0, y - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        (0, 0, 255),
                        1,
                        cv2.LINE_AA,
                    )
                cv2.imwrite(str(boxes_png_path), vis)
            except Exception as exc:
                logger.warning(f"Could not write HUD OCR debug boxes PNG {boxes_png_path}: {exc}")

    @staticmethod
    def _preprocess_ocr_region(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        preprocess: bool = True,
        white_text: bool = True,
        brightness_floor: Optional[int] = None,
        cc_filter_blobs: bool = False,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        roi_upscale: float = 1.0,
        save_preprocess_png: Optional[Path] = None,
    ) -> Optional[Tuple[Image.Image, np.ndarray, float, int, int]]:
        """Shared OCR preprocessing: ROI crop -> optional upscale -> binarize -> optional CC filter."""
        h_s, w_s = screen_img.shape[:2]
        if region:
            x, y, w, h = region
            clipped = VisionService._clip_rect_xywh(x, y, w, h, w_s, h_s)
            if clipped is None:
                return None
            rx, ry, rw, rh = clipped
            roi = screen_img[ry : ry + rh, rx : rx + rw]
            offset_x, offset_y = rx, ry
        else:
            roi = screen_img
            offset_x, offset_y = 0, 0

        coord_scale = 1.0
        if roi_upscale > 1.001:
            rh, rw = roi.shape[:2]
            nw = max(1, int(round(rw * roi_upscale)))
            nh = max(1, int(round(rh * roi_upscale)))
            roi = cv2.resize(roi, (nw, nh), interpolation=cv2.INTER_CUBIC)
            coord_scale = roi_upscale

        if preprocess:
            floor = (
                _WHITE_TEXT_BRIGHTNESS_FLOOR
                if brightness_floor is None
                else int(brightness_floor)
            )
            mono_gray = VisionService.preprocess_bw_ui_text(
                roi, white_text=white_text, brightness_floor=floor
            )
            if cc_filter_blobs:
                if cc_min_area is None or cc_max_area is None:
                    lo, hi = VisionService.scaled_cc_ink_bounds(w_s, h_s)
                else:
                    lo, hi = cc_min_area, cc_max_area
                if coord_scale > 1.001:
                    s2 = coord_scale * coord_scale
                    lo = max(1, int(round(lo * s2)))
                    hi = max(2, int(round(hi * s2)))
                mono_gray = VisionService.filter_binary_ink_by_component_area(
                    mono_gray, min_area=lo, max_area=hi
                )
        else:
            mono_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        if save_preprocess_png is not None:
            try:
                ensure_dir(save_preprocess_png.parent)
                cv2.imwrite(str(save_preprocess_png), mono_gray)
            except Exception as exc:
                logger.warning(f"Could not save OCR preprocess PNG {save_preprocess_png}: {exc}")

        pil_mono = Image.fromarray(mono_gray)
        return (pil_mono, mono_gray, coord_scale, offset_x, offset_y)

    @staticmethod
    def _tesseract_single_glyph_confidence_psm10(
        mono_gray: np.ndarray,
        left: int,
        top: int,
        right: int,
        bottom: int,
        tesseract_config: str = "",
        expected_char: str = "",
        pad_px: int = 2,
    ) -> float:
        """Run a cheap single-character Tesseract pass on a cropped glyph."""
        if pytesseract is None:
            return float("nan")
        gh, gw = mono_gray.shape[:2]
        x0 = max(0, left - pad_px)
        y0 = max(0, top - pad_px)
        x1 = min(gw, right + pad_px)
        y1 = min(gh, bottom + pad_px)
        if x1 <= x0 or y1 <= y0:
            return float("nan")
        crop = mono_gray[y0:y1, x0:x1]
        pil_crop = Image.fromarray(crop)
        cfg = "--psm 10 " + (tesseract_config or "")
        try:
            data = pytesseract.image_to_data(pil_crop, config=cfg, output_type=pytesseract.Output.DICT)
        except Exception:
            return float("nan")

        best_conf = float("nan")
        n = len(data.get("text", []))
        for i in range(n):
            txt = str(data["text"][i] or "").strip()
            if not txt:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                continue
            if expected_char and expected_char != txt:
                continue
            if math.isnan(best_conf) or conf > best_conf:
                best_conf = conf

        return best_conf

    @staticmethod
    def save_chars_ocr_debug_outputs(
        mono_gray: np.ndarray,
        raw_box_text: str,
        parsed_chars: Sequence[Tuple[str, int, int, int, int]],
        box_path: Optional[Path] = None,
        boxes_png_path: Optional[Path] = None,
        glyph_confidences: Optional[Sequence[float]] = None,
    ) -> None:
        """Write Tesseract image_to_boxes raw text and bounding box overlay."""
        if box_path is not None:
            try:
                ensure_dir(box_path.parent)
                box_path.write_text(raw_box_text or "", encoding="utf-8")
            except Exception as exc:
                logger.warning(f"Could not write char-OCR debug box file {box_path}: {exc}")

        if boxes_png_path is not None:
            try:
                ensure_dir(boxes_png_path.parent)
                vis = cv2.cvtColor(mono_gray, cv2.COLOR_GRAY2BGR)
                color = (0, 255, 0)
                for i, (ch, left, top, right, bottom) in enumerate(parsed_chars):
                    if right - left <= 0 or bottom - top <= 0:
                        continue
                    cv2.rectangle(vis, (left, top), (right - 1, bottom - 1), color, 1)
                    if not ch:
                        continue
                    if glyph_confidences is not None and i < len(glyph_confidences):
                        gc = glyph_confidences[i]
                        suff = f" {gc:.0f}" if isinstance(gc, (int, float)) and math.isfinite(float(gc)) else " ?"
                        label = (ch + suff)[:32]
                    else:
                        label = ch
                    cv2.putText(
                        vis,
                        label,
                        (left, max(0, top - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        color,
                        1,
                        cv2.LINE_AA,
                    )
                cv2.imwrite(str(boxes_png_path), vis)
            except Exception as exc:
                logger.warning(f"Could not write char-OCR debug boxes PNG {boxes_png_path}: {exc}")

    @staticmethod
    def find_chars_ocr(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        preprocess: bool = True,
        white_text: bool = True,
        tesseract_config: str = "--psm 6",
        cc_filter_blobs: bool = False,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        brightness_floor: Optional[int] = None,
        save_preprocess_png: Optional[Path] = None,
        roi_upscale: float = 1.0,
        ocr_debug_box_path: Optional[Path] = None,
        ocr_debug_boxes_png_path: Optional[Path] = None,
        psm10_glyph_confidence: bool = False,
    ) -> List[OcrWordBox]:
        """Character-level OCR via :func:`pytesseract.image_to_boxes`."""
        if pytesseract is None:
            VisionService._log_tesseract_missing()
            return []

        prep = VisionService._preprocess_ocr_region(
            screen_img,
            region=region,
            preprocess=preprocess,
            white_text=white_text,
            brightness_floor=brightness_floor,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            roi_upscale=roi_upscale,
            save_preprocess_png=save_preprocess_png,
        )
        if prep is None:
            return []

        pil_mono, mono_gray, coord_scale, offset_x, offset_y = prep
        try:
            raw_boxes = pytesseract.image_to_boxes(pil_mono, config=tesseract_config)
        except getattr(pytesseract, "TesseractNotFoundError", Exception):
            VisionService._log_tesseract_missing()
            return []

        parsed = []
        im_h = mono_gray.shape[0]
        for line in (raw_boxes or "").strip().splitlines():
            parts = line.strip().split()
            if len(parts) >= 6:
                ch = parts[0]
                x1 = int(parts[1])
                y1 = int(parts[2])
                x2 = int(parts[3])
                y2 = int(parts[4])
                top = im_h - y2
                bottom = im_h - y1
                parsed.append((ch, x1, top, x2, bottom))

        glyph_confs = None
        if psm10_glyph_confidence and parsed:
            glyph_confs = [
                VisionService._tesseract_single_glyph_confidence_psm10(
                    mono_gray, left, top, right, bottom, tesseract_config, expected_char=ch
                )
                for ch, left, top, right, bottom in parsed
            ]

        if ocr_debug_box_path is not None or ocr_debug_boxes_png_path is not None:
            VisionService.save_chars_ocr_debug_outputs(
                mono_gray,
                raw_boxes,
                parsed,
                box_path=ocr_debug_box_path,
                boxes_png_path=ocr_debug_boxes_png_path,
                glyph_confidences=glyph_confs,
            )

        inv = 1.0 / coord_scale
        out = []
        for i, (ch, left, top, right, bottom) in enumerate(parsed):
            w = max(1, right - left)
            h = max(1, bottom - top)
            sx = int(round(float(left) * inv)) + offset_x
            sy = int(round(float(top) * inv)) + offset_y
            sw = max(1, int(round(float(w) * inv)))
            sh = max(1, int(round(float(h) * inv)))
            conf = glyph_confs[i] if glyph_confs is not None else float("nan")
            out.append(
                OcrWordBox(
                    left=sx,
                    top=sy,
                    width=sw,
                    height=sh,
                    text=ch,
                    confidence=conf,
                )
            )

        return out

    @staticmethod
    def find_words_ocr(
        screen_img: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        *,
        query: Optional[str] = None,
        min_confidence: int = 30,
        case_sensitive: bool = False,
        preprocess: bool = True,
        white_text: bool = True,
        tesseract_config: str = "--psm 11",
        match_alnum_only: bool = False,
        fuzzy_min_ratio: Optional[float] = None,
        cc_filter_blobs: bool = False,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        brightness_floor: Optional[int] = None,
        save_preprocess_png: Optional[Path] = None,
        roi_upscale: float = 1.0,
        ocr_debug_tsv_path: Optional[Path] = None,
        ocr_debug_boxes_png_path: Optional[Path] = None,
    ) -> List[OcrWordBox]:
        """Locate words via OCR."""
        if pytesseract is None:
            VisionService._log_tesseract_missing()
            return []

        prep = VisionService._preprocess_ocr_region(
            screen_img,
            region=region,
            preprocess=preprocess,
            white_text=white_text,
            brightness_floor=brightness_floor,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            roi_upscale=roi_upscale,
            save_preprocess_png=save_preprocess_png,
        )
        if prep is None:
            return []

        pil_mono, mono_gray, coord_scale, offset_x, offset_y = prep
        try:
            data = pytesseract.image_to_data(
                pil_mono, config=tesseract_config, output_type=pytesseract.Output.DICT
            )
        except getattr(pytesseract, "TesseractNotFoundError", Exception):
            VisionService._log_tesseract_missing()
            return []

        if ocr_debug_tsv_path is not None or ocr_debug_boxes_png_path is not None:
            VisionService.save_hud_ocr_debug_outputs(
                pil_mono,
                mono_gray,
                data,
                tsv_path=ocr_debug_tsv_path,
                boxes_png_path=ocr_debug_boxes_png_path,
            )

        qnorm = None
        if query is not None:
            qnorm = query.strip() if case_sensitive else query.strip().lower()

        words = []
        n = len(data.get("text", []))
        for i in range(n):
            raw = str(data["text"][i] or "").strip()
            if not raw:
                continue
            try:
                conf = int(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1

            if min_confidence is not None and conf >= 0 and conf < min_confidence:
                continue

            if qnorm is not None:
                if not VisionService._ocr_query_matches(
                    raw,
                    qnorm,
                    case_sensitive=case_sensitive,
                    match_alnum_only=match_alnum_only,
                    fuzzy_min_ratio=fuzzy_min_ratio,
                ):
                    continue

            inv = 1.0 / coord_scale
            left = int(round(float(data["left"][i]) * inv)) + offset_x
            top = int(round(float(data["top"][i]) * inv)) + offset_y
            w = max(1, int(round(float(data["width"][i]) * inv)))
            h = max(1, int(round(float(data["height"][i]) * inv)))
            words.append(
                OcrWordBox(
                    left=left,
                    top=top,
                    width=w,
                    height=h,
                    text=raw,
                    confidence=float(conf) if conf >= 0 else math.nan,
                )
            )

        return words

    _TESSERACT_NUMBERS_HUD = "--psm 6 -c tessedit_char_whitelist=0123456789l"
    _TESSERACT_LETTERS_SPARSE = "--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    _TESSERACT_WALL_LABEL_SPARSE = "--psm 11 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

    @staticmethod
    def numbers_hud_roi_top_right(screen_w: int, screen_h: int) -> Tuple[int, int, int, int]:
        """Top-right HUD rectangle scaled from the aspect baseline."""
        key = resolve_aspect_key(screen_w, screen_h)
        base_w, base_h = _NUMBERS_HUD_ROI_AT_BASELINE.get(
            key, _NUMBERS_HUD_ROI_AT_BASELINE[ASPECT_16_9]
        )
        base_dim = ASPECT_BASELINE.get(key, ASPECT_BASELINE[ASPECT_16_9])
        scale_x = screen_w / base_dim[0]
        scale_y = screen_h / base_dim[1]
        w = max(10, int(round(base_w * scale_x)))
        h = max(10, int(round(base_h * scale_y)))
        x = max(0, screen_w - w)
        return (x, 0, w, h)

    @staticmethod
    def top_middle_square_roi(
        screen_w: int,
        screen_h: int,
        side: Optional[int] = None,
        aspect_key: Optional[str] = None,
    ) -> Tuple[int, int, int, int]:
        """A square anchored to the **top center**: ``y = 0``, horizontal center."""
        s = side if side is not None else VisionService.scaled_top_center_menu_side(screen_w, screen_h)
        x = max(0, (screen_w - s) // 2)
        return (x, 0, min(s, screen_w), min(s, screen_h))

    @staticmethod
    def ocr_letters_top_center(
        screen_img: np.ndarray,
        side: Optional[int] = None,
        *,
        min_confidence: int = 30,
        white_text: bool = True,
        brightness_floor: Optional[int] = None,
        cc_filter_blobs: bool = False,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        tesseract_config: Optional[str] = None,
        save_preprocess_png: Optional[Path] = None,
    ) -> List[OcrWordBox]:
        """Builder-menu style OCR in a square at the top center."""
        h_s, w_s = screen_img.shape[:2]
        roi = VisionService.top_middle_square_roi(w_s, h_s, side=side)
        cfg = (
            VisionService._TESSERACT_LETTERS_SPARSE.strip()
            if tesseract_config is None
            else str(tesseract_config).strip()
        )
        words = VisionService.find_words_ocr(
            screen_img,
            roi,
            min_confidence=min_confidence,
            preprocess=True,
            white_text=white_text,
            brightness_floor=brightness_floor,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            tesseract_config=cfg,
            save_preprocess_png=save_preprocess_png,
        )
        letter_only = re.compile(r"^[A-Za-z]+$")
        return [b for b in words if letter_only.fullmatch(b.text.strip())]

    @staticmethod
    def find_wall_upgrade_actions(
        screen_img: np.ndarray,
    ) -> WallUpgradeActionInfo:
        """Inspect the bottom action bar when a wall (or row of walls) is selected on the village map.

        Detects:
        - Select ROW button
        - Upgrade More button
        - Upgrade buttons (Gold and Elixir)
        - Measures redness in the cost box to check affordability (redness < 0.18 => affordable)
        """
        if screen_img is None or getattr(screen_img, "size", 0) == 0:
            return WallUpgradeActionInfo()

        h_s, w_s = screen_img.shape[:2]
        roi_y0, roi_y1 = int(h_s * 0.60), int(h_s * 0.98)
        roi_x0, roi_x1 = int(w_s * 0.15), int(w_s * 0.90)
        roi = screen_img[roi_y0:roi_y1, roi_x0:roi_x1]

        scale = w_s / 2560.0
        info_is_selected = False
        select_row_pt: Optional[Tuple[int, int]] = None
        upgrade_more_pt: Optional[Tuple[int, int]] = None
        gold_pt: Optional[Tuple[int, int]] = None
        elixir_pt: Optional[Tuple[int, int]] = None
        gold_affordable = False
        elixir_affordable = False

        from app.utils.common import get_template_path

        # 1. Template match for wall_hammer.png
        h_tpl_path = get_template_path("wall_hammer.png")
        hammers: List[Tuple[int, int]] = []
        if h_tpl_path.exists():
            h_tpl = cv2.imread(str(h_tpl_path))
            if h_tpl is not None and h_tpl.size > 0:
                sh = cv2.resize(h_tpl, (0, 0), fx=scale, fy=scale)
                if sh.shape[0] < roi.shape[0] and sh.shape[1] < roi.shape[1]:
                    res_h = cv2.matchTemplate(roi, sh, cv2.TM_CCOEFF_NORMED)
                    locs = np.where(res_h >= 0.70)
                    for pt in zip(*locs[::-1]):
                        cx = roi_x0 + pt[0] + sh.shape[1] // 2
                        cy = roi_y0 + pt[1] + sh.shape[0] // 2
                        if not any(abs(cx - p[0]) < int(50 * scale) for p in hammers):
                            hammers.append((int(cx), int(cy)))
                    hammers.sort(key=lambda p: p[0])

        # 2. Template match for selectrow.png
        sr_path = get_template_path("selectrow.png")
        if sr_path.exists():
            sr_tpl = cv2.imread(str(sr_path))
            if sr_tpl is not None and sr_tpl.size > 0:
                sa = cv2.resize(sr_tpl, (0, 0), fx=scale, fy=scale)
                if sa.shape[0] < roi.shape[0] and sa.shape[1] < roi.shape[1]:
                    res_sr = cv2.matchTemplate(roi, sa, cv2.TM_CCOEFF_NORMED)
                    _, max_v, _, max_l = cv2.minMaxLoc(res_sr)
                    if max_v >= 0.70:
                        select_row_pt = (roi_x0 + max_l[0] + sa.shape[1] // 2, roi_y0 + max_l[1] + sa.shape[0] // 2)
                        info_is_selected = True

        # 3. Template match for upgrademore_card.png
        um_path = get_template_path("upgrademore_card.png")
        if um_path.exists():
            um_tpl = cv2.imread(str(um_path))
            if um_tpl is not None and um_tpl.size > 0:
                sc = cv2.resize(um_tpl, (0, 0), fx=scale, fy=scale)
                if sc.shape[0] < roi.shape[0] and sc.shape[1] < roi.shape[1]:
                    res_um = cv2.matchTemplate(roi, sc, cv2.TM_CCOEFF_NORMED)
                    _, max_um, _, max_lc = cv2.minMaxLoc(res_um)
                    if max_um >= 0.70:
                        upgrade_more_pt = (roi_x0 + max_lc[0] + sc.shape[1] // 2, roi_y0 + max_lc[1] + sc.shape[0] // 2)
                        info_is_selected = True

        # 4. OCR fallback for text cards and selection confirmation
        ocr_upgrades: List[Tuple[int, int]] = []
        is_specifically_wall = False
        try:
            words = VisionService.find_words_ocr(screen_img, (roi_x0, roi_y0, roi_x1 - roi_x0, roi_y1 - roi_y0), min_confidence=20)
            reject_building_keywords = (
                "town", "hall", "cannon", "tower", "mortar", "inferno", "eagle",
                "scatter", "monolith", "spell", "barracks", "camp", "castle",
                "lab", "forge", "storage", "collector", "mine", "drill",
                "workshop", "smith", "pet", "hut", "altar", "air", "sweeper",
                "tesla", "defense", "artillery"
            )
            for wb in words:
                tl = wb.text.lower().strip()
                # Check for negative indicators of non-wall buildings
                if any(bldg in tl for bldg in reject_building_keywords):
                    # Definitely a non-wall building selected — never touch it as a wall!
                    return WallUpgradeActionInfo()
                clean = tl.replace("1", "l").replace("i", "l").replace("vv", "w")
                clean = clean.strip("_.:;~`'-|!*[]{} ")
                if ("wall" in clean or "wal" in clean) and "hall" not in clean:
                    idx = clean.find("wal")
                    if idx <= 2 and len(clean) <= 10:
                        is_specifically_wall = True
                elif "row" in tl or "select" in tl or "elect" in tl:
                    is_specifically_wall = True
                    if not select_row_pt:
                        select_row_pt = wb.center
                elif "more" in tl:
                    is_specifically_wall = True
                    if not upgrade_more_pt:
                        upgrade_more_pt = wb.center
                elif "upgrade" in tl or "pagrade" in tl or "grade" in tl:
                    ocr_upgrades.append(wb.center)
            ocr_upgrades.sort(key=lambda p: p[0])
        except Exception:
            pass

        # A target is ONLY confirmed as a wall if Select Row / Upgrade More is present,
        # OR the label specifically confirmed "Wall". Standard buildings with Upgrade buttons
        # must NEVER be mistaken for walls.
        if select_row_pt or upgrade_more_pt or is_specifically_wall:
            info_is_selected = True
        else:
            return WallUpgradeActionInfo()

        # Combine hammer template detections and OCR upgrade centers
        upgrade_centers = hammers if hammers else ocr_upgrades
        if upgrade_centers:
            if len(upgrade_centers) >= 2:
                gold_pt = upgrade_centers[0]
                elixir_pt = upgrade_centers[1]
            else:
                gold_pt = upgrade_centers[0]

        # 5. Check affordability (redness of cost numbers)
        for btn_type, pt in [("gold", gold_pt), ("elixir", elixir_pt)]:
            if pt is None:
                continue
            cx, cy = pt
            cy_cost = cy - int(60 * scale)
            box_half_w = int(70 * scale)
            box_half_h = int(25 * scale)
            y0, y1 = max(0, cy_cost - box_half_h), min(h_s, cy_cost + box_half_h)
            x0, x1 = max(0, cx - box_half_w), min(w_s, cx + box_half_w)
            crop = screen_img[y0:y1, x0:x1]
            if crop.size > 0:
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                red1 = cv2.inRange(hsv, (0, 100, 100), (10, 255, 255))
                red2 = cv2.inRange(hsv, (170, 100, 100), (180, 255, 255))
                redness = float((red1 | red2).mean() / 255.0)
                affordable = redness < 0.18
                if btn_type == "gold":
                    gold_affordable = affordable
                else:
                    elixir_affordable = affordable

        return WallUpgradeActionInfo(
            is_selected=info_is_selected,
            select_row=select_row_pt,
            upgrade_more=upgrade_more_pt,
            elixir_upgrade=elixir_pt,
            gold_upgrade=gold_pt,
            elixir_affordable=elixir_affordable,
            gold_affordable=gold_affordable,
        )

    @staticmethod
    def find_wall_labels_top_center_ocr(
        screen_img: np.ndarray,
        *,
        side: Optional[int] = None,
        min_confidence: int = 0,
        white_text: bool = True,
        brightness_floor: Optional[int] = None,
        cc_filter_blobs: bool = False,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        tesseract_config: Optional[str] = None,
        save_debug_preprocess: bool = False,
    ) -> Optional[Tuple[int, int]]:
        """Locate the 'Wall' row in the open builder popup.

        Same pipeline as :meth:`ocr_letters_top_center`, using the same ROI
        (top-center square). Returns the **lowest** word-box center whose text
        contains 'wall' (case-insensitive). ``None`` if no such word.

        Fenced to the builder popup body only: strictly rejects village map
        selection headers like "Wall (Level XX)" and non-wall buildings like
        "Town Hall" to prevent misclicking.
        """
        if screen_img is None or getattr(screen_img, "size", 0) == 0:
            return None

        cfg = (
            "--psm 11"
            if tesseract_config is None
            else str(tesseract_config).strip()
        )

        save_png = None
        if save_debug_preprocess:
            from app.utils.common import get_resource_path
            save_png = get_resource_path("glyph_debug/wall_find_preprocess.png")

        words = VisionService.ocr_letters_top_center(
            screen_img,
            side=side,
            min_confidence=min_confidence,
            white_text=white_text,
            brightness_floor=brightness_floor,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            tesseract_config=cfg,
            save_preprocess_png=save_png,
        )

        # Fence: only consider words in the label column of the builder popup
        # Builder popup lives in the upper-mid screen. y_max must cap before
        # the village selection title "Wall (Level XX)" at y >= 0.65 of frame.
        h_s, w_s = screen_img.shape[:2]
        x_min = int(w_s * 0.35)
        x_max = int(w_s * 0.55)
        y_min = int(h_s * 0.09)
        y_max = int(h_s * 0.65)

        def is_builder_wall_label(b) -> bool:
            t = b.text.lower().strip()
            reject_keywords = (
                "hall", "town", "clan", "castle", "mine", "drill", "tower",
                "cannon", "camp", "barracks", "lab", "forge", "storage",
                "collector", "hero", "level", "artillery", "scatter",
                "monolith", "workshop", "smith", "pet", "hut", "(", ")",
                "gold", "elixir", "dark", "upgrade"
            )
            if any(k in t for k in reject_keywords):
                return False
            # Normalize common OCR glyph confusions: 1 -> l, i -> l, vv -> w
            clean = t.replace("1", "l").replace("i", "l").replace("vv", "w")
            clean = clean.strip("_.:;~`'-|!*[]{} ")
            # Must contain "wal" (e.g. wall, walls, wal, tjwall, _jwalll)
            if "wall" in clean or "wal" in clean:
                idx = clean.find("wal")
                if idx <= 2 and len(clean) <= 10:
                    return True
            return False

        words = [
            b for b in words
            if x_min <= b.left < x_max and y_min <= b.top < y_max
        ]

        matches = [b for b in words if is_builder_wall_label(b)]
        if not matches:
            # Fallback: inspect raw word boxes in top center ROI without letter-only filter
            roi = VisionService.top_middle_square_roi(w_s, h_s, side=side)
            raw_words = VisionService.find_words_ocr(
                screen_img,
                roi,
                min_confidence=min_confidence,
                preprocess=True,
                white_text=white_text,
                brightness_floor=brightness_floor,
                cc_filter_blobs=False,
                tesseract_config=cfg,
            )
            raw_in_fence = [
                b for b in raw_words
                if x_min <= b.left < x_max and y_min <= b.top < y_max
            ]
            matches = [b for b in raw_in_fence if is_builder_wall_label(b)]

        if not matches:
            return None
        # Choose the lowest match within the builder popup
        best = max(matches, key=lambda b: b.top + b.height)
        logger.info("Found wall label %r at (%d, %d)", best.text, best.center[0], best.center[1])
        return best.center

    @staticmethod
    def detect_gem_spending_dialog(
        screen_img: np.ndarray,
    ) -> GemPromptDetection:
        """Strict Zero-Gem Policy: Detect any modal/dialog asking to spend gems.

        Checks for:
        1. Gem icon (bgem.png) in the modal center/bottom confirmation region.
        2. OCR text indicating missing resources or buying with gems.
        3. Attempts to locate the Cancel / 'X' button coordinates.
        """
        if screen_img is None or getattr(screen_img, "size", 0) == 0:
            return GemPromptDetection(detected=False)

        h, w = screen_img.shape[:2]
        # Modal body region (center 70% of screen horizontally, 15% to 85% vertically)
        modal_roi = (int(w * 0.15), int(h * 0.15), int(w * 0.70), int(h * 0.70))

        # Check 1: Gem icon template in the modal confirmation area (excluding top HUD gem counter)
        btn_roi = (int(w * 0.25), int(h * 0.40), int(w * 0.50), int(h * 0.45))
        try:
            from app.utils.common import get_template_path
            if get_template_path("bgem.png").exists():
                gx, gy = VisionService.find_template(
                    screen_img, "bgem.png", threshold=0.72, region=btn_roi
                )
                if gx is not None:
                    # Locate cancel button if present
                    cx, cy = VisionService.find_template(screen_img, "exit.png", region=modal_roi)
                    if not cx:
                        cx, cy = VisionService.find_template(screen_img, "needgold_x.png", region=modal_roi)
                    return GemPromptDetection(
                        detected=True,
                        reason=f"Gem icon detected in modal action button at ({gx}, {gy})",
                        cancel_point=(cx, cy) if cx else None,
                    )
        except Exception:
            logger.debug("Gem icon template check failed", exc_info=True)

        # Check 2: OCR text scan for gem purchase indicators in modal
        try:
            words = VisionService.find_words_ocr(
                screen_img,
                region=modal_roi,
                preprocess=True,
                white_text=True,
                min_confidence=25,
                tesseract_config="--psm 11",
            )
            raw_text = " ".join(w.text.lower() for w in words)
            gem_triggers = [
                "missing resources",
                "missing resource",
                "not enough gold",
                "not enough elixir",
                "not enough dark",
                "buy with gems",
                "purchase missing",
                "finish now for",
                "gems to finish",
                "buy for",
            ]
            for trig in gem_triggers:
                if trig in raw_text:
                    cancel_box = next((w for w in words if "cancel" in w.text.lower()), None)
                    cancel_pt = cancel_box.center if cancel_box else None
                    if not cancel_pt:
                        cx, cy = VisionService.find_template(screen_img, "exit.png", region=modal_roi)
                        if cx:
                            cancel_pt = (cx, cy)
                    return GemPromptDetection(
                        detected=True,
                        reason=f"Gem trigger phrase {trig!r} found in dialog text",
                        cancel_point=cancel_pt,
                    )

            has_gem_word = any(w.text.lower() in ("gem", "gems") for w in words)
            has_buy_word = any(w.text.lower() in ("buy", "cost", "finish", "purchase", "missing") for w in words)
            if has_gem_word and has_buy_word:
                cancel_box = next((w for w in words if "cancel" in w.text.lower()), None)
                return GemPromptDetection(
                    detected=True,
                    reason=f"Gem purchase keywords detected: {[w.text for w in words if w.text.lower() in ('gem', 'gems', 'buy', 'cost', 'finish', 'purchase')]}",
                    cancel_point=cancel_box.center if cancel_box else None,
                )
        except Exception:
            logger.debug("Gem OCR scan failed", exc_info=True)

        return GemPromptDetection(detected=False)

    @staticmethod
    def find_uncancelable_progression_button(
        screen_img: np.ndarray,
        *,
        min_confidence: int = 30,
    ) -> Optional[Tuple[int, int]]:
        """Find progression buttons in Supercell update/event announcement modals
        that have no 'X'/Cancel button (e.g. 'Okay', 'Continue', 'Claim', 'Awesome', 'Got it', 'Next').
        Ensures the button is NOT a gem purchase before returning its center.
        """
        if screen_img is None or getattr(screen_img, "size", 0) == 0:
            return None
        h, w = screen_img.shape[:2]
        # Search the bottom-half center modal button area
        btn_roi = (int(w * 0.20), int(h * 0.45), int(w * 0.60), int(h * 0.45))
        try:
            words = VisionService.find_words_ocr(
                screen_img,
                region=btn_roi,
                preprocess=True,
                white_text=True,
                min_confidence=min_confidence,
                tesseract_config="--psm 11",
            )
            PROGRESSION_KEYWORDS = ("okay", "continue", "claim", "awesome", "got it", "next", "start")
            for w_box in words:
                clean = "".join(ch for ch in w_box.text.lower() if ch.isalnum())
                if any(kw.replace(" ", "") in clean for kw in PROGRESSION_KEYWORDS):
                    (cx, cy) = w_box.center
                    patch = screen_img[max(0, cy - 25):min(h, cy + 25), max(0, cx - 60):min(w, cx + 60)]
                    if VisionService.red_hue_fraction(patch) < 0.15:
                        return (cx, cy)
        except Exception:
            logger.debug("Progression button OCR scan failed", exc_info=True)
        return None


    @staticmethod
    def _ocr_word_y_center(box: OcrWordBox) -> float:
        return box.top + box.height * 0.5

    @staticmethod
    def cluster_ocr_boxes_by_y(
        boxes: List[OcrWordBox], y_tolerance: float
    ) -> List[List[OcrWordBox]]:
        """Group OCR boxes that share a text line."""
        n = len(boxes)
        if n == 0:
            return []

        cy = [VisionService._ocr_word_y_center(b) for b in boxes]
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            pi = find(i)
            pj = find(j)
            if pi != pj:
                parent[pi] = pj

        tol = float(y_tolerance)
        for i in range(n):
            for j in range(i + 1, n):
                if abs(cy[i] - cy[j]) <= tol:
                    union(i, j)

        groups: Dict[int, List[OcrWordBox]] = {}
        for i in range(n):
            r = find(i)
            groups.setdefault(r, []).append(boxes[i])

        out = []
        for cl in groups.values():
            out.append(sorted(cl, key=lambda b: b.left))
        out.sort(key=lambda cl: VisionService._ocr_word_y_center(cl[0]))
        return out

    @staticmethod
    def merge_numeric_cluster(
        cluster: Sequence[OcrWordBox], join_separator: str = " "
    ) -> GroupedNumber:
        """Sort left-to-right and union bounding boxes into one :class:`GroupedNumber`."""
        parts = sorted(cluster, key=lambda b: b.left)
        text = join_separator.join(
            p.text.strip().replace("l", "1") for p in parts if p.text.strip()
        )
        left = min(p.left for p in parts)
        top = min(p.top for p in parts)
        right = max(p.left + p.width for p in parts)
        bottom = max(p.top + p.height for p in parts)
        confs = [p.confidence for p in parts if not math.isnan(p.confidence)]
        conf = float(sum(confs) / len(confs)) if confs else float("nan")
        return GroupedNumber(
            text=text,
            left=left,
            top=top,
            width=right - left,
            height=bottom - top,
            confidence=conf,
        )

    @staticmethod
    def extract_grouped_numbers_in_region(
        screen_img: np.ndarray,
        region: Tuple[int, int, int, int],
        *,
        min_confidence: int = 0,
        white_text: bool = True,
        tesseract_config: Optional[str] = None,
        y_tolerance_px: Optional[float] = None,
        cc_filter_blobs: bool = True,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        preprocess: bool = True,
        save_preprocess_png: Optional[Path] = None,
        roi_upscale: float = HUD_TOP_RIGHT_NUMBERS_ROI_UPSCALE,
        ocr_debug_box_path: Optional[Path] = None,
        ocr_debug_boxes_png_path: Optional[Path] = None,
        psm10_glyph_confidence: bool = False,
        hud_debug_char_clusters_out: Optional[List[List[OcrWordBox]]] = None,
        allow_hud_ocr_debug: bool = False,
    ) -> List[GroupedNumber]:
        """ROI crop -> optional upscale -> binarize -> char-level OCR -> cluster numbers."""
        h_s, w_s = screen_img.shape[:2]
        cfg = (
            VisionService._TESSERACT_NUMBERS_HUD
            if tesseract_config is None
            else tesseract_config
        )
        if not allow_hud_ocr_debug:
            save_preprocess_png = None
            ocr_debug_box_path = None
            ocr_debug_boxes_png_path = None
            psm10_glyph_confidence = False
            hud_debug_char_clusters_out = None

        chars = VisionService.find_chars_ocr(
            screen_img,
            region=region,
            preprocess=preprocess,
            white_text=white_text,
            tesseract_config=cfg,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            save_preprocess_png=save_preprocess_png,
            roi_upscale=roi_upscale,
            ocr_debug_box_path=ocr_debug_box_path,
            ocr_debug_boxes_png_path=ocr_debug_boxes_png_path,
            psm10_glyph_confidence=psm10_glyph_confidence,
        )
        digit_chars = [
            c for c in chars if c.text.isdigit() or c.text in ("l", "1")
        ]
        if not digit_chars:
            return []

        if y_tolerance_px is not None:
            y_tol = float(y_tolerance_px)
        else:
            med_h = float(
                np.median([c.height for c in digit_chars])
                if digit_chars
                else _NUMBERS_REF_LINE_HEIGHT_PX * (h_s / ASPECT_BASELINE[ASPECT_16_9][1])
            )
            y_tol = max(8.0, med_h * 0.45)

        clusters = VisionService.cluster_ocr_boxes_by_y(digit_chars, y_tol)
        if hud_debug_char_clusters_out is not None:
            hud_debug_char_clusters_out.clear()
            for cl in clusters:
                hud_debug_char_clusters_out.append(list(cl))

        return [
            VisionService.merge_numeric_cluster(cl, join_separator="")
            for cl in clusters
        ]

    @staticmethod
    def extract_top_right_hud_numbers(
        screen_img: np.ndarray,
        *,
        min_confidence: int = 0,
        white_text: bool = True,
        tesseract_config: Optional[str] = None,
        y_tolerance_px: Optional[float] = None,
        cc_filter_blobs: bool = True,
        cc_min_area: Optional[int] = None,
        cc_max_area: Optional[int] = None,
        preprocess: bool = True,
        save_preprocess_png: Optional[Path] = None,
        roi_upscale: float = HUD_TOP_RIGHT_NUMBERS_ROI_UPSCALE,
        ocr_debug_box_path: Optional[Path] = None,
        ocr_debug_boxes_png_path: Optional[Path] = None,
        psm10_glyph_confidence: bool = False,
        hud_debug_char_clusters_out: Optional[List[List[OcrWordBox]]] = None,
        allow_hud_ocr_debug: bool = False,
    ) -> List[GroupedNumber]:
        """Full top-right HUD number pipeline on screen_img."""
        cfg = Config()
        cfg.set_target_size_from_frame(screen_img)
        h_s, w_s = screen_img.shape[:2]
        roi = VisionService.numbers_hud_roi_top_right(w_s, h_s)
        return VisionService.extract_grouped_numbers_in_region(
            screen_img,
            roi,
            min_confidence=min_confidence,
            white_text=white_text,
            tesseract_config=tesseract_config,
            y_tolerance_px=y_tolerance_px,
            cc_filter_blobs=cc_filter_blobs,
            cc_min_area=cc_min_area,
            cc_max_area=cc_max_area,
            preprocess=preprocess,
            save_preprocess_png=save_preprocess_png,
            roi_upscale=roi_upscale,
            ocr_debug_box_path=ocr_debug_box_path,
            ocr_debug_boxes_png_path=ocr_debug_boxes_png_path,
            psm10_glyph_confidence=psm10_glyph_confidence,
            hud_debug_char_clusters_out=hud_debug_char_clusters_out,
            allow_hud_ocr_debug=allow_hud_ocr_debug,
        )

    @staticmethod
    def parse_loot_amount_from_grouped_text(text: str) -> Optional[int]:
        """Parse a HUD resource quantity from OCR text (digits only; commas and spaces ignored)."""
        digits = re.sub(r"\D", "", text or "")
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    @staticmethod
    def parse_hud_resources_triplet(
        groups: List[GroupedNumber],
        screen_h: Optional[int] = None,
    ) -> Optional[Tuple[int, int, int]]:
        """From :meth:`extract_top_right_hud_numbers` clusters, derive ``(gold, elixir, dark_elixir)``.

        Uses vertical position bands relative to screen height to assign each number
        to its true resource row:
        - Gold:        0.010 <= cy / H < 0.075
        - Elixir:      0.075 <= cy / H < 0.135
        - Dark Elixir: 0.135 <= cy / H < 0.195
        - Gems / etc:  cy / H >= 0.195 (strictly ignored)

        Includes automatic fallback to vertical row sorting (Row 1: Gold, Row 2: Elixir,
        Row 3: Dark Elixir) for non-standard window bounds or scaling.
        """
        if not groups:
            return None

        if screen_h is None or screen_h <= 0:
            try:
                screen_h = Config().target_size[1]
            except Exception:
                screen_h = 1080

        h_val = float(screen_h)
        gold_val = None
        elixir_val = None
        dark_val = None

        for g in groups:
            v = VisionService.parse_loot_amount_from_grouped_text(g.text)
            if v is None:
                continue
            cy = float(g.top) + float(g.height) * 0.5
            ratio = cy / h_val

            if 0.010 <= ratio < 0.075:
                # Gold row (if multiple pieces, pick the one with most digits)
                if gold_val is None or len(str(v)) > len(str(gold_val)):
                    gold_val = v
            elif 0.075 <= ratio < 0.135:
                # Elixir row
                if elixir_val is None or len(str(v)) > len(str(elixir_val)):
                    elixir_val = v
            elif 0.135 <= ratio < 0.195:
                # Dark Elixir row
                if dark_val is None or len(str(v)) > len(str(dark_val)):
                    dark_val = v
            # ratio >= 0.195 is Gems / Pass / etc. -> DO NOT assign to dark_elixir!

        # Both Gold and Elixir present via ratio bands
        if gold_val is not None and elixir_val is not None:
            return (gold_val, elixir_val, dark_val if dark_val is not None else 0)

        # Fallback: vertical top-to-bottom sorting (Row 1: Gold, Row 2: Elixir, Row 3: Dark Elixir)
        valid_rows: List[Tuple[int, int]] = []
        for g in groups:
            v = VisionService.parse_loot_amount_from_grouped_text(g.text)
            if v is not None and v > 0:
                valid_rows.append((g.top, v))

        if len(valid_rows) >= 2:
            valid_rows.sort(key=lambda r: r[0])
            g_cand = valid_rows[0][1]
            e_cand = valid_rows[1][1]
            d_cand = valid_rows[2][1] if len(valid_rows) >= 3 else 0
            if g_cand <= 35_000_000 and e_cand <= 35_000_000 and d_cand <= 10_000_000:
                return (g_cand, e_cand, d_cand)

        return None

    @staticmethod
    def numbers_enemy_loot_roi(screen_w: int, screen_h: int) -> Tuple[int, int, int, int]:
        """Top-left scouting loot rectangle containing available Gold, Elixir, and Dark Elixir."""
        x = max(0, int(round(screen_w * 0.02)))
        y = max(0, int(round(screen_h * 0.05)))
        w = min(screen_w - x, int(round(screen_w * 0.25)))
        h = min(screen_h - y, int(round(screen_h * 0.30)))
        return (x, y, w, h)

    @staticmethod
    def extract_enemy_loot(
        screen_img: np.ndarray,
    ) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Extracts available enemy loot ``(gold, elixir, dark_elixir)`` from the scout/attack screen."""
        if screen_img is None or screen_img.size == 0:
            return (None, None, None)
        h_s, w_s = screen_img.shape[:2]
        roi = VisionService.numbers_enemy_loot_roi(w_s, h_s)

        # 1. Primary extractor: grouped numeric clusters in the top-left ROI
        groups = VisionService.extract_grouped_numbers_in_region(
            screen_img,
            roi,
            white_text=True,
            preprocess=True,
            min_confidence=15,
        )

        parsed_rows: list[tuple[int, int]] = []
        for g in groups:
            v = VisionService.parse_loot_amount_from_grouped_text(g.text)
            if v is not None and v > 0:
                parsed_rows.append((g.top, v))

        # 2. Secondary fallback: OCR word boxes in the same ROI if grouped extraction found < 2 lines
        if len(parsed_rows) < 2:
            words = VisionService.find_words_ocr(
                screen_img,
                region=roi,
                white_text=True,
                preprocess=True,
                min_confidence=15,
            )
            for w in words:
                v = VisionService.parse_loot_amount_from_grouped_text(w.text)
                if v is not None and v > 0:
                    if not any(abs(p[0] - w.top) < 18 for p in parsed_rows):
                        parsed_rows.append((w.top, v))

        if not parsed_rows:
            return (None, None, None)

        # Sort from top to bottom (Gold is row 1, Elixir is row 2, Dark Elixir is row 3)
        parsed_rows.sort(key=lambda r: r[0])

        # Exclude stray single/double digit numbers (e.g. trophy count +28 or town hall badge < 100)
        candidates = [val for (_, val) in parsed_rows if val >= 50]
        if not candidates:
            return (None, None, None)

        gold = candidates[0] if len(candidates) >= 1 else None
        elixir = candidates[1] if len(candidates) >= 2 else None
        dark_elixir = candidates[2] if len(candidates) >= 3 else 0

        return (gold, elixir, dark_elixir)

    @staticmethod
    def _ocr_confidence_key(w: OcrWordBox) -> float:
        if math.isnan(w.confidence):
            return -1.0
        return float(w.confidence)

    @staticmethod
    def find_word_on_screen(
        screen_img: np.ndarray,
        word_or_phrase: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        **kwargs: Any,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Returns the center ``(x, y)`` of the best OCR match for ``word_or_phrase``, or ``(None, None)``."""
        matches = VisionService.find_words_ocr(
            screen_img, region=region, query=word_or_phrase, **kwargs
        )
        if not matches:
            return (None, None)

        case_sensitive = bool(kwargs.get("case_sensitive", False))
        match_alnum_only = bool(kwargs.get("match_alnum_only", False))
        fuzzy_min_ratio = kwargs.get("fuzzy_min_ratio")
        qnorm = word_or_phrase.strip() if case_sensitive else word_or_phrase.strip().lower()

        def pick_key(w: OcrWordBox) -> Tuple[int, int, float]:
            tier = VisionService._ocr_username_match_tier(
                w.text,
                qnorm,
                case_sensitive=case_sensitive,
                match_alnum_only=match_alnum_only,
                fuzzy_min_ratio=fuzzy_min_ratio,
            )
            if match_alnum_only:
                alen = len(re.sub(r"[^a-z0-9]", "", w.text.lower()))
            else:
                alen = len(w.text.strip())
            return (tier, alen, VisionService._ocr_confidence_key(w))

        best = max(matches, key=pick_key)
        return best.center

    @staticmethod
    def extract_battle_loot(screen_img: np.ndarray) -> Tuple[Optional[int], Optional[int], Optional[int]]:
        """Extracts enemy available Gold, Elixir, and Dark Elixir from the top-left HUD in matchmaking.

        Returns (gold, elixir, dark_elixir) as integers.
        Dark elixir may be 0 (TH6 and below) or a positive integer.
        Returns (None, None, None) if the loot numbers cannot be detected.
        """
        if pytesseract is None or screen_img is None or getattr(screen_img, "size", 0) == 0:
            return (None, None, None)

        h_s, w_s = screen_img.shape[:2]
        rx = int(w_s * 0.015)
        ry = int(h_s * 0.02)
        rw = int(w_s * 0.32)
        rh = int(h_s * 0.35)
        roi = screen_img[ry : ry + rh, rx : rx + rw]
        if roi.size == 0:
            return (None, None, None)

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh_bin = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
        _, thresh_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        passes = [thresh_bin, thresh_otsu, gray]

        for img_pass in passes:
            try:
                data = pytesseract.image_to_data(img_pass, config="--psm 6", output_type=pytesseract.Output.DICT)
            except Exception:
                continue

            words = []
            header_y = None
            for i in range(len(data.get("text", []))):
                raw = str(data["text"][i] or "").strip()
                try:
                    conf = float(data["conf"][i])
                except (ValueError, TypeError):
                    conf = 0.0
                if not raw or conf < 15:
                    continue
                top = int(data["top"][i])
                left = int(data["left"][i])
                words.append((top, left, raw, conf))
                low = raw.lower()
                if any(w in low for w in ("avail", "loot", "botin", "butin", "beute", "dispo", "saque", "zugreif")):
                    if header_y is None or top < header_y:
                        header_y = top

            filtered = [w for w in words if header_y is None or w[0] > (header_y - 5)]

            candidates = []
            for top, left, raw, conf in filtered:
                # Exclude any word with letters (opponent name, clan name)
                if any(c.isalpha() for c in raw):
                    continue
                # Exclude trophy changes (+XX or -YY)
                if "+" in raw or "-" in raw:
                    continue
                digits = "".join(c for c in raw if c.isdigit())
                if not digits:
                    continue
                candidates.append((top, left, digits, raw))

            if not candidates:
                continue

            # Sort first by vertical row band, then left-to-right
            line_band = max(14, int(rh * 0.08))
            candidates.sort(key=lambda c: (c[0] // line_band, c[1]))

            # Cluster space-separated number chunks on the same line
            clustered = []
            for c in candidates:
                if not clustered:
                    clustered.append(c)
                else:
                    prev = clustered[-1]
                    if abs(c[0] - prev[0]) < line_band:
                        merged_digits = prev[2] + c[2]
                        clustered[-1] = (prev[0], min(prev[1], c[1]), merged_digits, prev[3] + " " + c[3])
                    else:
                        clustered.append(c)

            # Filter out any isolated small level/clan badge numbers (e.g. <= 500) appearing before large loot
            while len(clustered) >= 3:
                first_val = int(clustered[0][2]) if clustered[0][2].isdigit() else 0
                second_val = int(clustered[1][2]) if clustered[1][2].isdigit() else 0
                if first_val <= 500 and second_val >= 5000:
                    clustered.pop(0)
                else:
                    break

            if len(clustered) >= 2:
                try:
                    gold = int(clustered[0][2])
                    elixir = int(clustered[1][2])
                    dark = int(clustered[2][2]) if len(clustered) >= 3 else 0
                    if gold >= 0 and elixir >= 0:
                        logger.info("Matchmaking loot extracted: Gold=%d, Elixir=%d, Dark=%d", gold, elixir, dark)
                        return (gold, elixir, dark)
                except (ValueError, TypeError):
                    pass

        return (None, None, None)

