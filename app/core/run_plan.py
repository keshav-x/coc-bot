"""What one press of Start does: villages to visit, per-village settings, accounts to rotate.

Built by the Run page, executed by :meth:`app.core.bot.Bot.start`. Lives apart from
``bot.py`` so the UI can build a plan without importing the vision/window stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.utils.player_list_store import PlayerEntry

HOME = "home"
BUILDER = "builder"

VILLAGE_LABELS = {
    HOME: "Home Village",
    BUILDER: "Builder Base",
}

VILLAGE_ORDER = (HOME, BUILDER)


@dataclass(frozen=True)
class VillageStep:
    """One village's farming session. Absent from a plan = that village is skipped."""

    village: str
    method: int
    duration_seconds: int
    star_bonus: bool = False
    ranked_fill: bool = False
    upgrade_walls: bool = False
    loot_prioritise: str = "both"

    @property
    def label(self) -> str:
        return VILLAGE_LABELS.get(self.village, self.village)


@dataclass(frozen=True)
class RunPlan:
    """A full run. ``players`` is ``None`` for the account already logged in."""

    steps: Tuple[VillageStep, ...] = ()
    collect_resources: bool = True
    players: Optional[Tuple[PlayerEntry, ...]] = None

    @property
    def rotating(self) -> bool:
        return self.players is not None

    def step_for(self, village: str) -> Optional[VillageStep]:
        for step in self.steps:
            if step.village == village:
                return step
        return None

    def includes(self, village: str) -> bool:
        return self.step_for(village) is not None

    @property
    def enabled_players(self) -> Tuple[PlayerEntry, ...]:
        if self.players is None:
            return ()
        return tuple(p for p in self.players if p.enabled and p.name.strip())

    def is_empty(self) -> bool:
        """Nothing to do — no village sessions and no collecting."""
        return not self.steps and not self.collect_resources

    def describe(self) -> str:
        """One-line summary for the log."""
        if self.players is None:
            who = "current account"
        else:
            who = f"{len(self.enabled_players)} accounts"
        parts = []
        for village in VILLAGE_ORDER:
            step = self.step_for(village)
            if step is not None:
                if step.star_bonus:
                    when = "star bonus"
                else:
                    when = f"{step.duration_seconds // 60}m"
                parts.append(f"{step.label}({step.method}, {when})")
        if self.collect_resources:
            parts.append("collect")
        return f"{who}: " + (" -> ".join(parts) if parts else "nothing")
