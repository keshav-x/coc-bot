"""Intelligent Anti-Ban and Humanization Suite for Clash AutoLoot.

Provides:
- Non-linear humanized Bezier mouse trajectories with physiological acceleration and micro-tremors.
- Natural click dwell duration (variable down/up timings).
- Dynamic fatigue & break simulation (periodic human pauses).
- Natural idle interactions (village inspection, camera nudge).
- Action Rate Limiting (APM ceiling).
- Profiles: STEALTH (maximum safety), BALANCED (default), FAST.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from app.utils.common import ensure_dir, get_user_app_data_dir
from app.utils.logger import setup_logger

logger = setup_logger("AntiBan")

PROFILE_STEALTH = "Stealth"
PROFILE_BALANCED = "Balanced"
PROFILE_FAST = "Fast"
PROFILE_OPTIONS = (PROFILE_STEALTH, PROFILE_BALANCED, PROFILE_FAST)

ANTIBAN_CONFIG_FILENAME = "antiban.json"


@dataclass
class AntiBanConfig:
    profile: str = PROFILE_BALANCED
    breaks_enabled: bool = False
    min_session_mins: int = 25
    max_session_mins: int = 45
    min_break_mins: int = 2
    max_break_mins: int = 5
    human_curves_enabled: bool = True
    idle_inspection_enabled: bool = True
    random_clicks_enabled: bool = True
    max_apm: int = 160


def get_antiban_config_path() -> Path:
    dest = get_user_app_data_dir() / ANTIBAN_CONFIG_FILENAME
    ensure_dir(dest.parent)
    return dest


def load_antiban_config() -> AntiBanConfig:
    path = get_antiban_config_path()
    if not path.is_file():
        return AntiBanConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return AntiBanConfig()
        return AntiBanConfig(
            profile=str(raw.get("profile", PROFILE_BALANCED)),
            breaks_enabled=bool(raw.get("breaks_enabled", False)),
            min_session_mins=int(raw.get("min_session_mins", 25)),
            max_session_mins=int(raw.get("max_session_mins", 45)),
            min_break_mins=int(raw.get("min_break_mins", 2)),
            max_break_mins=int(raw.get("max_break_mins", 5)),
            human_curves_enabled=bool(raw.get("human_curves_enabled", True)),
            idle_inspection_enabled=bool(raw.get("idle_inspection_enabled", True)),
            random_clicks_enabled=bool(raw.get("random_clicks_enabled", True)),
            max_apm=int(raw.get("max_apm", 160)),
        )
    except Exception as e:
        logger.warning(f"Could not load antiban config: {e}")
        return AntiBanConfig()


def save_antiban_config(config: AntiBanConfig) -> None:
    path = get_antiban_config_path()
    try:
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save antiban config: {e}")


class AntiBanService:
    _instance: Optional[AntiBanService] = None

    def __new__(cls) -> AntiBanService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self) -> None:
        self.config = load_antiban_config()
        self.session_start = time.time()
        self.next_break_time = self._calculate_next_break()
        self._action_timestamps: List[float] = []

    def reload_config(self) -> None:
        self.config = load_antiban_config()
        self.next_break_time = self._calculate_next_break()

    def reset_session(self) -> None:
        self.session_start = time.time()
        self.next_break_time = self._calculate_next_break()
        self._action_timestamps.clear()

    def _calculate_next_break(self) -> float:
        min_s = self.config.min_session_mins * 60
        max_s = max(min_s + 60, self.config.max_session_mins * 60)
        return time.time() + random.uniform(min_s, max_s)

    def is_break_due(self) -> bool:
        if not self.config.breaks_enabled:
            return False
        return time.time() >= self.next_break_time

    def execute_break_if_due(
        self,
        stop_event,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """If a human fatigue break is due, pauses execution for a realistic rest interval."""
        if not self.is_break_due():
            return False

        min_b = self.config.min_break_mins * 60
        max_b = max(min_b + 30, self.config.max_break_mins * 60)
        break_duration = int(random.uniform(min_b, max_b))
        logger.info(f"Anti-Ban: taking a human break for {break_duration}s (~{break_duration // 60} mins)")

        start = time.time()
        while time.time() - start < break_duration:
            if stop_event and stop_event.is_set():
                return False
            remaining = int(break_duration - (time.time() - start))
            mins = remaining // 60
            secs = remaining % 60
            msg = f"Anti-Ban Human Break: {mins:02d}:{secs:02d} remaining"
            if status_callback:
                status_callback(msg)
            if stop_event:
                if stop_event.wait(1.0):
                    return False
            else:
                time.sleep(1.0)

        logger.info("Anti-Ban: Human break finished. Resuming bot.")
        self.next_break_time = self._calculate_next_break()
        return True

    def generate_bezier_path(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        steps: int = 25,
    ) -> List[Tuple[int, int]]:
        """Generates realistic human hand movement coordinates using Cubic Bezier with natural jitter."""
        dist = math.hypot(x2 - x1, y2 - y1)
        if dist < 5:
            return [(int(x2), int(y2))]

        # Deviation angle & offset proportional to distance
        deviation = dist * random.uniform(0.1, 0.25)
        angle = math.atan2(y2 - y1, x2 - x1)
        normal_angle = angle + (math.pi / 2) * random.choice((-1, 1))

        # Control Point 1 (closer to start)
        cx1 = x1 + (x2 - x1) * random.uniform(0.2, 0.4) + math.cos(normal_angle) * deviation
        cy1 = y1 + (y2 - y1) * random.uniform(0.2, 0.4) + math.sin(normal_angle) * deviation

        # Control Point 2 (closer to target)
        cx2 = x1 + (x2 - x1) * random.uniform(0.6, 0.8) + math.cos(normal_angle) * deviation * 0.7
        cy2 = y1 + (y2 - y1) * random.uniform(0.6, 0.8) + math.sin(normal_angle) * deviation * 0.7

        points: List[Tuple[int, int]] = []
        for i in range(1, steps + 1):
            t = i / float(steps)
            # S-curve ease-in ease-out for human acceleration profile
            ease_t = 3 * (t**2) - 2 * (t**3)

            # Cubic Bezier formula
            u = 1 - ease_t
            bx = (u**3) * x1 + 3 * (u**2) * ease_t * cx1 + 3 * u * (ease_t**2) * cx2 + (ease_t**3) * x2
            by = (u**3) * y1 + 3 * (u**2) * ease_t * cy1 + 3 * u * (ease_t**2) * cy2 + (ease_t**3) * y2

            # Add physiological hand micro-tremor (±1-2px) in the middle of movement
            if 0.1 < t < 0.9:
                bx += random.uniform(-1.5, 1.5)
                by += random.uniform(-1.5, 1.5)

            points.append((int(round(bx)), int(round(by))))

        # Guarantee exact target at the end
        points[-1] = (int(round(x2)), int(round(y2)))
        return points

    def record_action(self) -> None:
        """Records an action timestamp and rate-limits if exceeding max APM."""
        now = time.time()
        self._action_timestamps.append(now)
        # Prune older than 60s
        self._action_timestamps = [t for t in self._action_timestamps if now - t <= 60.0]

        if len(self._action_timestamps) > self.config.max_apm:
            # Over APM ceiling -> insert a subtle human pause
            cooldown = random.uniform(0.35, 0.85)
            time.sleep(cooldown)

    def gaussian_point(self, x: int, y: int, sigma: float = 4.0) -> Tuple[int, int]:
        """Displaces a coordinate using a normal (Gaussian) distribution around the center."""
        gx = int(round(random.gauss(x, sigma)))
        gy = int(round(random.gauss(y, sigma)))
        return (gx, gy)
