"""Smart Loot Filtration and Search Analytics Engine for Clash AutoLoot.

Provides:
- Configurable minimum resource thresholds: Gold, Elixir, Dark Elixir.
- Match conditions: 'Either Gold or Elixir', 'Both Gold and Elixir', 'Dark Elixir Priority'.
- Dead base / full collector preference.
- Max skip budget management.
- Live session statistics tracking (Gold/hr, Elixir/hr, Dark Elixir/hr, Raids, Skips).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.utils.common import ensure_dir, get_user_app_data_dir
from app.utils.logger import setup_logger

logger = setup_logger("LootFilter")

FILTER_MODE_OR = "Either Gold or Elixir"
FILTER_MODE_AND = "Both Gold and Elixir"
FILTER_MODE_DE = "Dark Elixir Priority"
FILTER_MODES = (FILTER_MODE_OR, FILTER_MODE_AND, FILTER_MODE_DE)

LOOT_FILTER_CONFIG_FILENAME = "loot_filter.json"


@dataclass
class LootFilterConfig:
    enabled: bool = True
    min_gold: int = 350000
    min_elixir: int = 350000
    min_dark_elixir: int = 3000
    filter_mode: str = FILTER_MODE_OR
    dead_base_only: bool = False
    max_skips: int = 40


def get_loot_filter_config_path() -> Path:
    dest = get_user_app_data_dir() / LOOT_FILTER_CONFIG_FILENAME
    ensure_dir(dest.parent)
    return dest


def load_loot_filter_config() -> LootFilterConfig:
    path = get_loot_filter_config_path()
    if not path.is_file():
        return LootFilterConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return LootFilterConfig()
        return LootFilterConfig(
            enabled=bool(raw.get("enabled", True)),
            min_gold=int(raw.get("min_gold", 350000)),
            min_elixir=int(raw.get("min_elixir", 350000)),
            min_dark_elixir=int(raw.get("min_dark_elixir", 3000)),
            filter_mode=str(raw.get("filter_mode", FILTER_MODE_OR)),
            dead_base_only=bool(raw.get("dead_base_only", False)),
            max_skips=int(raw.get("max_skips", 40)),
        )
    except Exception as e:
        logger.warning(f"Could not load loot filter config: {e}")
        return LootFilterConfig()


def save_loot_filter_config(config: LootFilterConfig) -> None:
    path = get_loot_filter_config_path()
    try:
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save loot filter config: {e}")


@dataclass
class LootFilterDecision:
    should_attack: bool
    reason: str
    gold: int = 0
    elixir: int = 0
    dark_elixir: int = 0


@dataclass
class RaidRecord:
    raid_num: int
    timestamp_str: str
    gold: int
    elixir: int
    dark_elixir: int
    skips: int
    status: str = "Victory"


class SessionStats:
    def __init__(self) -> None:
        self.start_time = time.time()
        self.total_gold = 0
        self.total_elixir = 0
        self.total_dark_elixir = 0
        self.raids_completed = 0
        self.bases_skipped = 0
        self.raid_history: list[RaidRecord] = []

    def reset(self) -> None:
        self.start_time = time.time()
        self.total_gold = 0
        self.total_elixir = 0
        self.total_dark_elixir = 0
        self.raids_completed = 0
        self.bases_skipped = 0
        self.raid_history.clear()

    def record_raid(
        self,
        gold: int,
        elixir: int,
        dark_elixir: int,
        skips: int = 0,
        status: str = "Victory",
    ) -> RaidRecord:
        self.total_gold += max(0, gold)
        self.total_elixir += max(0, elixir)
        self.total_dark_elixir += max(0, dark_elixir)
        self.raids_completed += 1
        rec = RaidRecord(
            raid_num=self.raids_completed,
            timestamp_str=time.strftime("%H:%M:%S"),
            gold=max(0, gold),
            elixir=max(0, elixir),
            dark_elixir=max(0, dark_elixir),
            skips=skips,
            status=status,
        )
        self.raid_history.append(rec)
        if len(self.raid_history) > 100:
            self.raid_history.pop(0)
        return rec

    def record_skip(self) -> None:
        self.bases_skipped += 1

    @property
    def elapsed_hours(self) -> float:
        return max(0.001, (time.time() - self.start_time) / 3600.0)

    @property
    def gold_per_hour(self) -> int:
        return int(self.total_gold / self.elapsed_hours)

    @property
    def elixir_per_hour(self) -> int:
        return int(self.total_elixir / self.elapsed_hours)

    @property
    def dark_elixir_per_hour(self) -> int:
        return int(self.total_dark_elixir / self.elapsed_hours)


class LootFilterEngine:
    _instance: Optional[LootFilterEngine] = None

    def __new__(cls) -> LootFilterEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.config = load_loot_filter_config()
            cls._instance.stats = SessionStats()
        return cls._instance

    def reload_config(self) -> None:
        self.config = load_loot_filter_config()

    def evaluate(
        self,
        gold: Optional[int],
        elixir: Optional[int],
        dark_elixir: Optional[int],
        current_skip_count: int = 0,
    ) -> LootFilterDecision:
        """Evaluates detected enemy loot against configured filter rules."""
        if not self.config.enabled:
            return LootFilterDecision(
                should_attack=True,
                reason="Loot filter disabled",
                gold=gold or 0,
                elixir=elixir or 0,
                dark_elixir=dark_elixir or 0,
            )

        g = gold or 0
        e = elixir or 0
        de = dark_elixir or 0

        # Safety override: if skip budget is exhausted, attack the current base
        if current_skip_count >= self.config.max_skips:
            return LootFilterDecision(
                should_attack=True,
                reason=f"Max search skips reached ({current_skip_count}/{self.config.max_skips})",
                gold=g,
                elixir=e,
                dark_elixir=de,
            )

        # Dead base evaluation
        if self.config.dead_base_only:
            min_dead_thresh = max(200000, min(self.config.min_gold, self.config.min_elixir) // 2)
            if g < min_dead_thresh or e < min_dead_thresh:
                return LootFilterDecision(
                    should_attack=False,
                    reason=f"Not a dead base (G: {g:,} / E: {e:,} < {min_dead_thresh:,})",
                    gold=g,
                    elixir=e,
                    dark_elixir=de,
                )

        # Mode evaluation
        if self.config.filter_mode == FILTER_MODE_OR:
            if g >= self.config.min_gold or e >= self.config.min_elixir:
                return LootFilterDecision(
                    should_attack=True,
                    reason=f"Matched threshold (G: {g:,} / E: {e:,})",
                    gold=g,
                    elixir=e,
                    dark_elixir=de,
                )
        elif self.config.filter_mode == FILTER_MODE_AND:
            if g >= self.config.min_gold and e >= self.config.min_elixir:
                return LootFilterDecision(
                    should_attack=True,
                    reason=f"Matched both thresholds (G: {g:,} & E: {e:,})",
                    gold=g,
                    elixir=e,
                    dark_elixir=de,
                )
        elif self.config.filter_mode == FILTER_MODE_DE:
            if de >= self.config.min_dark_elixir:
                return LootFilterDecision(
                    should_attack=True,
                    reason=f"Matched Dark Elixir (DE: {de:,})",
                    gold=g,
                    elixir=e,
                    dark_elixir=de,
                )

        return LootFilterDecision(
            should_attack=False,
            reason=f"Below target (G: {g:,} / E: {e:,} / DE: {de:,})",
            gold=g,
            elixir=e,
            dark_elixir=de,
        )
