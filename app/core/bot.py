import time
import random
import threading
from typing import Callable, Optional, Tuple

from app.config import ASPECT_16_10, ASPECT_16_9, Config
from app.core.run_plan import BUILDER as RP_BUILDER, HOME as RP_HOME, RunPlan
from app.core.strategies import AttackStrategy, EdragStrategy, TroopSpamStrategy, _EDRAG_DELAY
from app.services.input import InputService
from app.services.vision import BOTTOM_HALF_BOT_TEMPLATES, TOP_HALF_BOT_TEMPLATES, VisionService
from app.services.window import WindowService
from app.services.antiban import AntiBanService
from app.core.loot_filter import LootFilterEngine
from app.core.watchdog import AutoRecoveryWatchdog
from app.services.notifications import NotificationService
from app.services.webhook import (
    notify_bot_started,
    notify_raid_complete,
    notify_break,
    notify_bot_stopped,
)
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import EARTHQUAKE_METHOD_CURVE

logger = setup_logger("BotCore")

_HOME_VILLAGE_BUILDER_TEMPLATES: tuple = ("builder.png", "gbuilder.png")

_WALL_OCR_RETRY_DRAG_BASELINE: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    ASPECT_16_10: ((1300, 280), (1300, 980)),
    ASPECT_16_9: ((1300, 280), (1300, 830)),
}

_BB_METHOD_BABY_DRAGONS: int = 5
_BB_METHOD_NIGHT_WITCHES: int = 6
_BB_BABY_DRAGON_TEMPLATE: str = "babydragon.png"
_BB_NIGHT_WITCH_TEMPLATE: str = "nightwitch.png"
_BB_BABY_DRAGON_RECLICK_WAIT: float = 10.0
_BB_NIGHT_WITCH_RECLICK_WAIT: float = 3.0
_BB_MACHINE_ABILITY_WAIT: float = 3.0
_BB_RETURN_HOME_TEMPLATE: str = "breturnhome.png"
_BB_RETURN_HOME_TEMPLATE_1080P: str = "breturnhome1920.png"
_BB_1080P_CAPTURE_SIZE: tuple[int, int] = (1920, 1080)
_BB_1080P_SIZE_TOLERANCE: int = 40
_BB_TEMPLATE_SUPPRESS_PAD: float = 0.1
_BB_FULL_ELIXIR_CART_TEMPLATES: tuple[str, ...] = ("fullecart.png", "fullecart2.png", "fullecart3.png")
_BB_COLLECT_TEMPLATE: str = "collect.png"
_BB_STAR_BONUS_TEMPLATE: str = "bstar.png"
_BB_BATTLE_STAR_TEMPLATE: str = "bbstar.png"
_BB_BATTLE_MACHINE_TEMPLATE: str = "battlemachine.png"
_BB_FLYING_MACHINE_TEMPLATE: str = "flyingmachine.png"
_BB_GOLD_PRIORITISE_MIN_STARS: int = 2
_BB_RETURN_HOME_END_BATTLE_RETRIES: int = 5
_STAR_BONUS_THRESHOLD: float = 0.75
_RETURN_HOME_THRESHOLD: float = 0.75


class Bot:
    def __init__(self) -> None:
        self.config: Config = Config()
        self.window: WindowService = WindowService()
        self.stop_event: threading.Event = threading.Event()
        self.input: InputService = InputService(self.window, self.stop_event)
        self.vision: VisionService = VisionService()
        self.running: bool = False
        self._earthquake_method: str = EARTHQUAKE_METHOD_CURVE
        self._loot_totals: tuple[int, int, int] = (0, 0, 0)
        self._loot_prev_resources: Optional[tuple[int, int, int]] = None
        self._loot_session_start_mono: float = 0.0
        self._loot_callback: Optional[Callable[[int, int, int, float], None]] = None
        self._suppress_loot_negative_error_once: bool = False
        self._loot_prioritise: str = "both"
        self.antiban: AntiBanService = AntiBanService()
        self.loot_filter: LootFilterEngine = LootFilterEngine()
        self.watchdog: AutoRecoveryWatchdog = AutoRecoveryWatchdog(
            self.vision,
            self.input,
            self.window,
            status_callback=lambda msg: self._status_callback(msg) if hasattr(self, "_status_callback") and self._status_callback else None,
        )

    def start(
        self,
        plan: RunPlan,
        status_callback: Optional[Callable[[str], None]] = None,
        loot_callback: Optional[Callable[[int, int, int, float], None]] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        """Runs ``plan`` once per account (or once for the current account if not rotating)."""
        self._status_callback = status_callback
        self._loot_callback = loot_callback
        self._earthquake_method = earthquake_method
        if not self.window.find_window():
            raise RuntimeError("Clash of Clans window not found. Please ensure the game is open.")
        is_empty_val = plan.is_empty() if callable(getattr(plan, "is_empty", None)) else getattr(plan, "is_empty", False)
        if is_empty_val:
            raise RuntimeError("Run plan is empty — include a village or resource collection.")
        self._reset_loot_session()
        self._emit_loot_update()
        self.antiban.reset_session()
        self.loot_filter.stats.reset()
        notify_bot_started(plan.describe())
        self.running = True
        self.stop_event.clear()
        logger.info(f"Bot started. Plan: {plan.describe()}, Earthquake: {earthquake_method}")
        try:
            if not plan.rotating:
                self._run_account_session(plan)
            else:
                queue = plan.enabled_players
                if not queue:
                    raise RuntimeError("Multi-run: no players marked Run")
                self._ensure_correct_village(builder_base=False)
                for player in queue:
                    self._check_stop()
                    self._switch_account_and_load_home(player.name)
                    self._check_stop()
                    self._run_account_session(plan)
                    self._check_stop()
        except InterruptedError:
            pass
        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            raise
        finally:
            self.running = False
            self._earthquake_method = EARTHQUAKE_METHOD_CURVE
            notify_bot_stopped("Finished" if not self.stop_event.is_set() else "User stopped")
            logger.info("Bot stopped.")

    def _run_account_session(self, plan: RunPlan) -> None:
        """
One account's turn through the plan:

Home Village session → collect on home → boat → collect in Builder Base →
Builder Base session → boat home.

Steps the plan excludes are skipped, but the **boat trips are not part of
collecting** — they are travel, and they still run whenever Builder Base is
visited. Turning collection off must never strand the run in the wrong village.
"""
        home_step = plan.step_for(RP_HOME)
        builder_step = plan.step_for(RP_BUILDER)
        visit_builder = (builder_step is not None) or plan.collect_resources
        builder_only = (home_step is None) and (not plan.collect_resources)
        if builder_only:
            self._ensure_correct_village(builder_base=True)
        else:
            self._ensure_correct_village(builder_base=False)
            if home_step is not None:
                self._loot_prioritise = home_step.loot_prioritise
                self._run_loop(
                    home_step.method,
                    home_step.duration_seconds,
                    home_step.star_bonus,
                    home_step.ranked_fill,
                    home_step.upgrade_walls,
                )
                self._check_stop()
            if plan.collect_resources:
                self._collect_home_village_resources()
                self._check_stop()
            if not visit_builder:
                return
            if not self._go_to_builder_base_with_boat():
                msg = "Builder Base: boat not found — skipping the Builder Base leg"
                logger.warning(msg)
                cb = getattr(self, "_status_callback", None)
                if cb:
                    cb(msg)
                return
        try:
            if plan.collect_resources:
                self._collect_builder_base_resources()
                self._check_stop()
            if builder_step is not None:
                self._loot_prioritise = builder_step.loot_prioritise
                self._run_builder_base_loop(
                    builder_step.duration_seconds,
                    star_bonus=builder_step.star_bonus,
                    method=builder_step.method,
                )
        finally:
            if not builder_only or plan.rotating:
                self._leave_builder_base_with_nboat(settle_before_drag=True)

    def stop(self) -> None:
        """Signals the bot to stop."""
        self.running = False
        self.stop_event.set()

    def _reset_loot_session(self) -> None:
        """Reset counters for a new :meth:`start` — no disk persistence."""
        self._loot_totals = (0, 0, 0)
        self._loot_prev_resources = None
        self._loot_session_start_mono = time.monotonic()
        self._suppress_loot_negative_error_once = False

    def _emit_loot_update(self) -> None:
        cb = self._loot_callback
        if not cb:
            return
        g, el, de = self._loot_totals
        elapsed = max(0.0, time.monotonic() - float(self._loot_session_start_mono))
        cb(g, el, de, elapsed)

    def _loot_snapshot_before_attack(self) -> None:
        frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            self._emit_loot_update()
            return
        self._update_config_size(frame)
        groups = VisionService.extract_top_right_hud_numbers(frame)
        triplet = VisionService.parse_hud_resources_triplet(groups)
        if triplet is None:
            logger.debug("Loot tracker: could not parse top-right HUD (%d groups)", len(groups))
            self._emit_loot_update()
            return
        cur_g, cur_el, cur_de = triplet
        prev = self._loot_prev_resources
        skipped_due_to_negative_delta = False
        if prev is not None:
            lg, le, ld = prev
            dg = cur_g - lg
            d_el = cur_el - le
            d_de = cur_de - ld
            if dg >= 0 and d_el >= 0 and d_de >= 0:
                tg, te, td = self._loot_totals
                self._loot_totals = (tg + dg, te + d_el, td + d_de)
                logger.info(
                    "Loot tracker: +%s / +%s / +%s (G/E/DE) → session %s / %s / %s",
                    dg,
                    d_el,
                    d_de,
                    self._loot_totals[0],
                    self._loot_totals[1],
                    self._loot_totals[2],
                )
            else:
                skipped_due_to_negative_delta = True
                logger.warning(
                    "Loot tracker: negative delta — previous gold/elixir/dark=%s/%s/%s current read=%s/%s/%s",
                    lg,
                    le,
                    ld,
                    cur_g,
                    cur_el,
                    cur_de,
                )
        self._loot_prev_resources = triplet
        self._emit_loot_update()
        if skipped_due_to_negative_delta:
            if self._suppress_loot_negative_error_once:
                self._suppress_loot_negative_error_once = False
                return
            return
        self._suppress_loot_negative_error_once = False

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise InterruptedError("Bot stopped by user")

    def _update_config_size(self, frame) -> None:
        """Reload aspect profile if screenshot size implies a different template folder."""
        self.config.set_target_size_from_frame(frame)

    def _scroll_point(self) -> Tuple[int, int]:
        """Scroll anchor in authoring space [1000,1000]; scaled to current capture."""
        x, y = self.config.scale_point([1000, 1000])
        return (x, y)

    def _nudge_view_to_reveal_attack(self) -> None:
        """Click neutral empty space to dismiss any loose popup overlays (without zooming)."""
        empty_pt = self.config.get_point("empty")
        self.input.click(empty_pt, pause=0.15, rand=False)

    def _find_home_village_builder(self, frame, region=None) -> Tuple[Optional[int], Optional[int]]:
        for name in _HOME_VILLAGE_BUILDER_TEMPLATES:
            x, y = self.vision.find_template(frame, name, region=region)
            if x:
                return (x, y)
        return (None, None)

    def _wall_menu_drag_to_bottom(self) -> None:
        """
Drag the builder upgrade list to its bottom so ``Wall`` (list end) is revealed.

Touch-style swipe up: click low in the list, drag to the top, release — the reverse of
the old wheel scroll. Baseline coords are scaled via :meth:`Config.scale_point`. Dragging
past the bottom is a harmless no-op, so this can be called repeatedly.
"""
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning("wall menu drag: unknown aspect %r; skipping drag", self.config.aspect_key)
            return
        top_ref, bottom_ref = pair
        top = self.config.scale_point([top_ref[0], top_ref[1]])
        bottom = self.config.scale_point([bottom_ref[0], bottom_ref[1]])
        x_top, y_top = int(top[0]), int(top[1])
        x_bot, y_bot = int(bottom[0]), int(bottom[1])
        self.input.move(x_bot, y_bot)
        self.input.mouse_down(x_bot, y_bot)
        try:
            self.input.human_move(x_bot, y_bot, x_top, y_top, duration=0.5)
        finally:
            self.input.mouse_up(x_top, y_top)

    def _wall_menu_drag_retry_nudge(self) -> None:
        """Vertical drag in the builder list when ``wall`` OCR misses (~0.5s eased move + hold pause)."""
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning("wall OCR retry drag: unknown aspect %r; skipping drag", self.config.aspect_key)
            return
        p1_ref, p2_ref = pair
        p1 = self.config.scale_point([p1_ref[0], p1_ref[1]])
        p2 = self.config.scale_point([p2_ref[0], p2_ref[1]])
        x1, y1 = int(p1[0]), int(p1[1])
        x2, y2 = int(p2[0]), int(p2[1])
        self.input.move(x1, y1)
        self.input.mouse_down(x1, y1)
        try:
            self.input.human_move(x1, y1, x2, y2, duration=0.5)
            if self.stop_event.wait(0.3):
                return
        finally:
            self.input.mouse_up(x2, y2)

    def _should_upgrade_walls(self) -> bool:
        """True when either full gold or full elixir hero-bar icon matches on the current home frame."""
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        gx, gy = VisionService.find_active_hgoldfull(frame)
        ex, ey = VisionService.find_active_helixirfull(frame)
        return (gx is not None) or (ex is not None)

    def _maybe_upgrade_walls(self, upgrade_walls: bool) -> None:
        """Upgrade walls on home when enabled and storages look full."""
        if not upgrade_walls or not self._should_upgrade_walls():
            return
        self._loot_snapshot_before_attack()
        for _ in range(2):
            self._check_stop()
            self._upgrade_walls()
        self._suppress_loot_negative_error_once = True

    def _upgrade_walls_pick_resource_and_okay(self) -> None:
        """Fresh frame → redness above multiupgrade → click affordable slot → Okay."""
        frame = self.window.screenshot()
        if frame is None:
            return
        self._update_config_size(frame)
        pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
        if pair.gold.redness < 0.2 and pair.gold.center:
            self.input.click(pair.gold.center, pause=0.3)
        elif pair.elixir.redness < 0.2 and pair.elixir.center:
            self.input.click(pair.elixir.center, pause=0.3)
        frame = self.window.screenshot()
        if frame is None:
            return
        self._update_config_size(frame)
        ox, oy = self.vision.find_template(frame, "okay.png")
        if ox:
            self.input.click(ox, oy, pause=0.3)

    def _upgrade_walls(self) -> None:
        """Open builder menu, scroll to Wall, add walls → remove if both red → Okay."""
        frame = self.window.screenshot()
        if frame is None:
            return
        self._update_config_size(frame)
        top_roi = VisionService.top_half_region(frame)
        bx, by = self._find_home_village_builder(frame, top_roi)
        if not bx:
            return
        self.input.click(bx, by, pause=0.4)
        for _ in range(8):
            self._check_stop()
            self._wall_menu_drag_to_bottom()
            if self.stop_event.wait(0.15):
                return
        wall_pt = None
        for attempt in range(10):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return
            self._update_config_size(frame)
            wall_pt = VisionService.find_wall_labels_top_center_ocr(frame)
            if wall_pt:
                break
            if attempt < 9:
                self._wall_menu_drag_retry_nudge()
                if self.stop_event.wait(0.12):
                    return
        if not wall_pt:
            return
        self.input.click(wall_pt, pause=0.6)
        frame = self.window.screenshot()
        if frame is None:
            return
        self._update_config_size(frame)
        bot_roi = VisionService.bottom_half_region(frame)
        umx, umy = self.vision.find_template(frame, "upgrademore.png", region=bot_roi)
        if not umx:
            return
        self.input.click(umx, umy, pause=0.4)
        while True:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return
            self._update_config_size(frame)
            pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
            gold_red = pair.gold.redness
            elixir_red = pair.elixir.redness
            if gold_red < 0.2 or elixir_red < 0.2:
                bot_roi = VisionService.bottom_half_region(frame)
                awx, awy = VisionService.find_active_addwall(frame, region=bot_roi)
                if awx:
                    self.input.click(awx, awy, pause=0.3)
                    continue
                else:
                    self._upgrade_walls_pick_resource_and_okay()
                    return
            else:
                break
        while True:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return
            self._update_config_size(frame)
            pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
            if pair.gold.redness < 0.2 or pair.elixir.redness < 0.2:
                self._upgrade_walls_pick_resource_and_okay()
                return
            bot_roi = VisionService.bottom_half_region(frame)
            rwx, rwy = VisionService.find_active_removewall(frame, region=bot_roi)
            if not rwx:
                self._upgrade_walls_pick_resource_and_okay()
                return
            self.input.click(rwx, rwy, pause=0.4)

    def _dismiss_okay_or_exit_on_frame(self, frame) -> bool:
        """If ``okay.png`` or ``exit.png`` is visible (full frame), click it. Returns True if dismissed."""
        for name in ("okay.png", "exit.png"):
            x, y = self.vision.find_template(frame, name)
            if x:
                self.input.click(x, y, pause=0.15)
                return True
        return False

    def _wait_for_attack_with_nudge(
        self, timeout: int = 10, error: bool = True
    ) -> Tuple[Optional[int], Optional[int]]:
        """Poll bottom-half ``attack.png``; dismiss ``okay`` / ``exit`` popups first; else empty click + fallback."""
        start = time.time()
        attempts = 0
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.3):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.25):
                    return (None, None)
                continue
            search_region = self._search_region_for_template(frame, "attack.png", None, None, 200)
            ax, ay = self.vision.find_template(frame, "attack.png", threshold=0.70, region=search_region)
            if ax:
                return (ax, ay)
            # Try lower threshold on bottom half
            ax, ay = self.vision.find_template(
                frame, "attack.png", threshold=0.62, region=VisionService.bottom_half_region(frame)
            )
            if ax:
                return (ax, ay)
            attempts += 1
            if attempts >= 3:
                # Guaranteed fallback: Attack button is at bottom-left corner of Home Village
                h, w = frame.shape[:2]
                fallback_x = int(w * 0.058)
                fallback_y = int(h * 0.915)
                logger.info(f"Using bottom-left calibrated fallback for Attack button: ({fallback_x}, {fallback_y})")
                return (fallback_x, fallback_y)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.25):
                return (None, None)
        if error:
            logger.warning("Timeout waiting for attack.png")
        return (None, None)

    def _run_loop(
        self,
        method_id: int,
        duration_seconds: int,
        star_bonus: bool,
        ranked_fill: bool,
        upgrade_walls: bool,
    ) -> None:
        start_time = time.time()
        if self.stop_event.wait(0.5):
            return
        frame = self.window.screenshot()
        if frame is not None:
            self._update_config_size(frame)
        empty_pt = self.config.get_point("empty")
        self.input.click(empty_pt, pause=0.2, rand=False)
        delay = random.uniform(0.1, 0.2)
        if self.stop_event.wait(delay):
            return
        if star_bonus and self._is_star_bonus_claimed():
            logger.info(
                "Star bonus mode: no star bonus template matched on home — nothing to collect. Finishing without attacks."
            )
            return
        self._maybe_upgrade_walls(upgrade_walls)
        while time.time() - start_time < duration_seconds:
            self._check_stop()
            if self.antiban.execute_break_if_due(self.stop_event, status_callback=self._status_callback):
                notify_break(self.antiban.config.min_break_mins)
            self._check_stop()
            troop_failed = self._find_match_and_attack(method_id, ranked_fill)
            self._return_home()
            self._home_screen_recovery()
            if troop_failed:
                return
            self._maybe_upgrade_walls(upgrade_walls)
            if self.stop_event.wait(random.uniform(0.15, 0.25)):
                return
            if star_bonus and self._is_star_bonus_claimed():
                logger.info("Star bonus claimed (star icons no longer visible). Stopping.")
                return

    def _run_builder_base_loop(
        self, duration_seconds: int, star_bonus: bool = False, method: int = _BB_METHOD_BABY_DRAGONS
    ) -> None:
        """
Builder Base farming, then one last elixir-cart sweep before the session ends.

The in-loop sweep only runs after a completed attack, so a session that ends on
a retry path (no Attack button, Find Now missing, deploy failed) — or on the
star-bonus early exit — would otherwise leave a full cart sitting there.
"""
        self._bb_attack_loop(duration_seconds, star_bonus=star_bonus, method=method)
        if self.stop_event.is_set():
            return
        logger.info("Builder Base: session finished — final elixir cart check")
        self._bb_collect_elixir_cart_after_attack()

    def _bb_attack_loop(
        self,
        duration_seconds: int,
        star_bonus: bool = False,
        method: int = _BB_METHOD_BABY_DRAGONS,
    ) -> None:
        """Attack → Find Now → troop deploy → end battle or surrender → Return Home, until time is up."""
        troop_template = (
            _BB_NIGHT_WITCH_TEMPLATE if method == _BB_METHOD_NIGHT_WITCHES else _BB_BABY_DRAGON_TEMPLATE
        )
        start_time = time.time()
        cb = getattr(self, "_status_callback", None)
        if self.stop_event.wait(1):
            return
        frame = self.window.screenshot()
        if frame is not None:
            self._update_config_size(frame)
        empty_pt = self.config.get_point("empty")
        self.input.click(empty_pt, pause=0.2, rand=False)
        if self.stop_event.wait(random.uniform(0.1, 0.2)):
            return
        if star_bonus and self._is_bb_star_bonus_finished():
            msg = "Builder Base star bonus: bstar.png not visible — nothing to collect. Finishing without attacks."
            logger.info(msg)
            if cb:
                cb(msg)
            return
        while time.time() - start_time < duration_seconds:
            self._check_stop()
            if self.stop_event.wait(random.uniform(0.1, 0.2)):
                return
            ax, ay = self._wait_for_image("attack.png", timeout=10, threshold=0.70)
            if not ax:
                logger.warning("Builder Base: attack.png not found")
                continue
            self.input.click(ax, ay, pause=0.3)
            fx, fy = self._wait_for_image("findnow.png", timeout=10, threshold=0.70)
            if not fx:
                logger.warning("Builder Base: findnow.png not found")
                continue
            self.input.click(fx, fy, pause=0.3)
            bx, by = self._wait_for_image(troop_template, timeout=30, error=False, threshold=0.70)
            if not bx:
                msg = f"Builder Base: {troop_template} not found after Find Now"
                logger.warning(msg)
                if cb:
                    cb(msg)
                continue
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            if method == _BB_METHOD_NIGHT_WITCHES:
                deployed = self._deploy_bb_night_witches(frame)
            else:
                deployed = self._deploy_bb_baby_dragons(frame)
            if not deployed:
                logger.warning("Builder Base: %s lost after zoom nudge / deploy failed", troop_template)
                continue
            if self._loot_prioritise == "elixir":
                self._bb_surrender_and_return_home()
            elif self._loot_prioritise == "gold":
                self._bb_gold_prioritise_end_battle_and_return_home()
            else:
                self._bb_end_battle_and_return_home()
            self._bb_collect_elixir_cart_after_attack()
            if star_bonus and self._is_bb_star_bonus_finished():
                logger.info("Builder Base star bonus finished (bstar.png no longer visible). Stopping.")
                return
            if self.stop_event.wait(random.uniform(0.35, 0.6)):
                return

    def _bb_pan_down_left_from_center(self) -> None:
        """Pan BB view down-left from screen center (~500px) to reveal the boat / elixir cart."""
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return
        self._update_config_size(frame)
        h, w = frame.shape[:2]
        cx = w // 2 + random.randint(-25, 25)
        cy = h // 2 + random.randint(-25, 25)
        cx = max(8, min(w - 8, cx))
        cy = max(8, min(h - 8, cy))
        self.input.move(cx, cy, 0)
        self.input.mouse_up(cx, cy)
        if self.stop_event.wait(0.06):
            self._check_stop()
        step = 500
        x2 = max(8, min(w - 8, cx - step))
        y2 = max(8, min(h - 8, cy + step))
        self.input.mouse_down(cx, cy)
        self.input.human_move(cx, cy, x2, y2, duration=random.uniform(0.35, 0.55))
        self.input.mouse_up(x2, y2)
        if self.stop_event.wait(0.45):
            self._check_stop()
            return

    def _find_bb_full_elixir_cart(self, attempts: int) -> Tuple[Optional[int], Optional[int]]:
        """Up to ``attempts`` screenshots; try fullecart templates in order (top-right quadrant)."""
        empty_pt = self.config.get_point("empty")
        for _ in range(attempts):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is not None:
                self._update_config_size(frame)
                roi = VisionService.top_right_quadrant_region(frame)
                for template in _BB_FULL_ELIXIR_CART_TEMPLATES:
                    x, y = self.vision.find_template(frame, template, threshold=0.8, region=roi)
                    if x:
                        return (x, y)
            self.input.click(empty_pt, pause=0.15)
        return (None, None)

    def _bb_collect_elixir_cart_after_attack(self) -> None:
        """After a BB raid: dismiss popups, pan to cart, collect full elixir cart if visible."""
        if self.stop_event.wait(0.35):
            return
        self.input.click(self.config.get_point("empty"), pause=0.15)
        if self.stop_event.wait(0.15):
            return
        self._bb_pan_down_left_from_center()
        cx, cy = self._find_bb_full_elixir_cart(attempts=3)
        if cx:
            self.input.click(cx, cy, pause=0.2)
            coll_x, coll_y = self._wait_for_image(_BB_COLLECT_TEMPLATE, timeout=8, error=False)
            if coll_x:
                self.input.click(coll_x, coll_y, pause=0.2)
            else:
                logger.warning("Builder Base: collect.png not found after elixir cart")
        else:
            logger.debug("Builder Base: fullecart not visible — skipping cart collect")
        self.input.click(self.config.get_point("empty"), pause=0.15)

    def _deploy_bb_baby_dragons(self, frame) -> bool:
        """Find all Baby Dragon icons, deploy on diamond edges, wait, then re-click saved icons."""
        strategy = AttackStrategy(self.input, self.vision, self.config, self.stop_event)
        roi = VisionService.bottom_half_region(frame)
        centers = VisionService.find_all_template_centers(
            frame,
            _BB_BABY_DRAGON_TEMPLATE,
            region=roi,
            max_matches=12,
            suppress_pad_frac=_BB_TEMPLATE_SUPPRESS_PAD,
        )
        if not centers:
            return False
        deploy_count = len(centers)
        self.input.click(centers[0][0], centers[0][1], pause=0.3, rand=False)
        if self.stop_event.wait(0.2):
            return True
        deploy_reverse = random.choice((False, True))
        logger.debug(
            "Builder Base: deploying %d baby dragons %s",
            deploy_count,
            "right→top→left" if deploy_reverse else "left→top→right",
        )
        for px, py in strategy._even_diamond_top_perimeter_points(
            frame, deploy_count, reserve_top_corner_slot=True, reverse=deploy_reverse
        ):
            self._check_stop()
            self.input.click(px, py, pause=_EDRAG_DELAY, rand=False)
        self._deploy_bb_battle_or_flying_machine(strategy)
        if self._loot_prioritise != "elixir":
            if self.stop_event.wait(_BB_BABY_DRAGON_RECLICK_WAIT):
                return True
            for x, y in centers:
                self._check_stop()
                self.input.click(x, y, pause=0.15, rand=False)
        return True

    def _deploy_bb_night_witches(self, frame) -> bool:
        """Find all Night Witch icons, deploy randomly on diamond front arc, wait, re-click."""
        strategy = AttackStrategy(self.input, self.vision, self.config, self.stop_event)
        roi = VisionService.bottom_half_region(frame)
        centers = VisionService.find_all_template_centers(
            frame,
            _BB_NIGHT_WITCH_TEMPLATE,
            region=roi,
            max_matches=12,
            suppress_pad_frac=_BB_TEMPLATE_SUPPRESS_PAD,
        )
        if not centers:
            return False
        deploy_count = len(centers)
        self.input.click(centers[0][0], centers[0][1], pause=0.3, rand=False)
        if self.stop_event.wait(0.2):
            return True
        logger.debug("Builder Base: deploying %d night witches along left→top→right (random)", deploy_count)
        for px, py in strategy._random_diamond_top_perimeter_points(frame, deploy_count):
            self._check_stop()
            self.input.click(px, py, pause=_EDRAG_DELAY, rand=False)
        self._deploy_bb_battle_or_flying_machine(strategy)
        if self._loot_prioritise != "elixir":
            if self.stop_event.wait(_BB_NIGHT_WITCH_RECLICK_WAIT):
                return True
            for x, y in centers:
                self._check_stop()
                self.input.click(x, y, pause=0.15, rand=False)
        return True

    def _deploy_bb_battle_or_flying_machine(self, strategy: AttackStrategy) -> None:
        """Deploy Battle Machine or Flying Machine, then re-tap its icon to activate ability."""
        frame = self.window.screenshot()
        if frame is None:
            return
        self._update_config_size(frame)
        roi = VisionService.bottom_half_region(frame)
        template_name = _BB_BATTLE_MACHINE_TEMPLATE
        tx, ty = self.vision.find_template(frame, template_name, region=roi)
        if not tx:
            template_name = _BB_FLYING_MACHINE_TEMPLATE
            tx, ty = self.vision.find_template(frame, template_name, region=roi)
        if not tx:
            logger.debug("Builder Base: %s / %s not found on troop bar", _BB_BATTLE_MACHINE_TEMPLATE, _BB_FLYING_MACHINE_TEMPLATE)
            return
        icon_x, icon_y = tx, ty
        px, py = strategy._random_diamond_perimeter_point(frame)
        self.input.click(icon_x, icon_y, pause=0.3, rand=False)
        if self.stop_event.wait(0.2):
            return
        self.input.click(px, py, pause=_EDRAG_DELAY, rand=False)
        if self.stop_event.wait(_BB_MACHINE_ABILITY_WAIT):
            return
        logger.debug("Builder Base: activating %s ability (re-tap troop icon)", template_name)
        self.input.click(icon_x, icon_y, pause=0.15, rand=False)

    def _bb_end_battle_and_return_home(self) -> None:
        """Wait for natural battle end, dismiss Okay, then tap BB Return Home."""
        ex, ey = self._wait_for_image("endbattle.png", timeout=90, error=False)
        if ex:
            self.input.click(ex, ey, pause=0.15)
        else:
            logger.warning("Builder Base: endbattle.png not found")
            return
        self._bb_dismiss_okay_and_return_home()

    def _bb_gold_prioritise_end_battle_and_return_home(self) -> None:
        start = time.time()
        timeout = 90
        end_battle_clicked = False
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return
                continue
            self._update_config_size(frame)
            bot_roi = VisionService.bottom_half_region(frame)
            stars = VisionService.find_all_template_centers(
                frame,
                _BB_BATTLE_STAR_TEMPLATE,
                threshold=0.8,
                region=bot_roi,
                max_matches=3,
                suppress_pad_frac=0.35,
            )
            if len(stars) >= _BB_GOLD_PRIORITISE_MIN_STARS:
                bot_roi = VisionService.bottom_half_region(frame)
                ex, ey = self.vision.find_template(frame, "endbattle.png", region=bot_roi)
                if ex:
                    logger.info("Builder Base (gold): %d bbstar.png — clicking endbattle", len(stars))
                    self.input.click(ex, ey, pause=0.15)
                    end_battle_clicked = True
                    break
            if self.stop_event.wait(0.5):
                return
        if not end_battle_clicked:
            logger.warning("Builder Base (gold): timed out waiting for %d+ %s", _BB_GOLD_PRIORITISE_MIN_STARS, _BB_BATTLE_STAR_TEMPLATE)
            return
        self._bb_dismiss_okay_and_return_home()

    def _bb_return_home_template_for_screen(self, width: int, height: int) -> Tuple[str, bool]:
        """Return (template name, scale_template) for Builder Base Return Home."""
        tw, th = _BB_1080P_CAPTURE_SIZE
        tol = _BB_1080P_SIZE_TOLERANCE
        if abs(width - tw) <= tol and abs(height - th) <= tol:
            return (_BB_RETURN_HOME_TEMPLATE_1080P, False)
        return (_BB_RETURN_HOME_TEMPLATE, True)

    def _wait_for_bb_return_home(self, timeout: int = 15) -> Tuple[Optional[int], Optional[int], str]:
        """Wait for BB Return Home; picks 1080p-native template when capture is ~1920x1080."""
        start = time.time()
        template_name = _BB_RETURN_HOME_TEMPLATE
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            h, w = frame.shape[:2]
            template_name, scale_template = self._bb_return_home_template_for_screen(w, h)
            search_region = self._search_region_for_template(frame, template_name, None, None, 200)
            x, y = self.vision.find_template(
                frame, template_name, threshold=0.8, region=search_region, scale_template=scale_template
            )
            if x:
                return (x, y, template_name)
            if self.stop_event.wait(0.5):
                return (None, None, template_name)
        return (None, None, template_name)

    def _bb_dismiss_okay_and_return_home(
        self,
        retry_battle_template: str = "endbattle.png",
        max_retries: int = _BB_RETURN_HOME_END_BATTLE_RETRIES,
    ) -> None:
        """Dismiss Okay, tap Return Home; retry battle-end + Okay if Return Home stays hidden."""
        return_home_template = _BB_RETURN_HOME_TEMPLATE
        for attempt in range(max_retries + 1):
            self._check_stop()
            if attempt > 0:
                bx, by = self._wait_for_image(retry_battle_template, timeout=3, error=False)
                if bx:
                    self.input.click(bx, by, pause=0.15)
                else:
                    logger.debug(
                        "Builder Base: %s retry %d/%d — control not visible",
                        retry_battle_template,
                        attempt,
                        max_retries,
                    )
            okay_timeout = 10 if attempt == 0 else 5
            ox, oy = self._wait_for_image("okay.png", timeout=okay_timeout, error=False)
            if ox:
                self.input.click(ox, oy, pause=0.15)
            rx, ry, return_home_template = self._wait_for_bb_return_home(timeout=15)
            if rx:
                self.input.click(rx, ry, pause=0.2)
                if attempt > 0:
                    logger.info("Builder Base: return home after %d %s retry(ies)", attempt, retry_battle_template)
                return
            if attempt < max_retries:
                logger.info(
                    "Builder Base: %s not found — retrying %s + okay (%d/%d)",
                    return_home_template,
                    retry_battle_template,
                    attempt + 1,
                    max_retries,
                )
        logger.warning(
            "Builder Base: %s not found after %d %s retries",
            return_home_template,
            max_retries,
            retry_battle_template,
        )

    def _bb_surrender_and_return_home(self) -> None:
        """Elixir prioritise: surrender right after deploy, then Okay + Return Home."""
        sx, sy = self._wait_for_image("surrender.png", timeout=10, error=False)
        if sx:
            self.input.click(sx, sy, pause=0.15)
        else:
            logger.warning("Builder Base (elixir): surrender.png not found")
            return
        self._bb_dismiss_okay_and_return_home(retry_battle_template="surrender.png")

    def _find_match_and_attack(self, method_id: int, ranked_fill: bool = False) -> bool:
        """Returns True if the bot should stop (troop not found, or ranked limit reached)."""
        ax, ay = self._wait_for_attack_with_nudge()
        if not ax:
            return False
        self.input.click(ax, ay, pause=0.6)

        if ranked_fill:
            battle_template = "rankedbattle.png"
            fx, fy = self._wait_for_image(battle_template, timeout=6, threshold=0.70)
            if not fx:
                msg = "Ranked battle button not found — daily limit may be reached. Stopping."
                logger.info(msg)
                cb = getattr(self, "_status_callback", None)
                if cb:
                    cb(msg)
                return True
            self.input.click(fx, fy, pause=0.6)
            a2x, a2y = self._wait_for_image("attack2.png", timeout=6, threshold=0.70)
            if a2x:
                self.input.click(a2x, a2y, pause=0.5)
            rx, ry = self._wait_for_image("rankedattackconfirm.png", timeout=8, threshold=0.70)
            if rx:
                self.input.click(rx, ry, pause=0.4)
        else:
            # Regular multiplayer farming
            # Check for farmbattle.png (Find a Match) or attack2.png directly
            fx, fy = self._wait_for_any_image(
                ("farmbattle.png", "attack2.png"), timeout=5, threshold=0.70, error=False
            )
            if fx:
                self.input.click(fx, fy, pause=0.6)
                # If farmbattle was clicked, attack2 (confirmation) might pop up
                a2x, a2y = self._wait_for_image("attack2.png", timeout=3, error=False, threshold=0.70)
                if a2x:
                    self.input.click(a2x, a2y, pause=0.5)
            else:
                # Modal fallback click: Find a Match is located at ~72% W, ~75% H in attack dialog
                frame = self.window.screenshot()
                if frame is not None:
                    h, w = frame.shape[:2]
                    fb_x = int(w * 0.72)
                    fb_y = int(h * 0.74)
                    logger.info(f"Using modal fallback coordinates for Find a Match: ({fb_x}, {fb_y})")
                    self.input.click(fb_x, fb_y, pause=0.6)

        self._wait_for_any_image(("surrender.png", "endbattle.png", "findnow.png"), timeout=35)

        # Smart Loot Filtration & Base Skipping (multiplayer farming)
        last_loot_detected = (0, 0, 0)
        skip_count = 0
        if not ranked_fill and self.loot_filter.config.enabled:
            while not self.stop_event.is_set():
                self._check_stop()
                frame = self.window.screenshot()
                if frame is None:
                    break
                self._update_config_size(frame)
                gold, elixir, dark = VisionService.extract_battle_loot(frame)
                decision = self.loot_filter.evaluate(gold, elixir, dark, skip_count)
                if gold or elixir or dark:
                    last_loot_detected = (gold or 0, elixir or 0, dark or 0)

                if decision.should_attack:
                    logger.info(f"Loot filter approved base: {decision.reason}")
                    cb = getattr(self, "_status_callback", None)
                    if cb:
                        cb(f"Attacking: {decision.reason}")
                    break

                # Base is below filter threshold -> skip it!
                skip_count += 1
                self.loot_filter.stats.record_skip()
                cb = getattr(self, "_status_callback", None)
                if cb:
                    cb(f"Skipping base (#{skip_count}): {decision.reason}")
                logger.info(f"Loot filter: skipping base #{skip_count} ({decision.reason})")

                next_x, next_y = self._wait_for_image("findnow.png", timeout=6, error=False, threshold=0.70)
                if not next_x:
                    logger.warning("Next button (findnow.png) not found during base search; attacking current base.")
                    break
                self.input.click(next_x, next_y, pause=0.25)
                self._wait_for_any_image(("surrender.png", "endbattle.png"), timeout=25)
                if self.stop_event.wait(0.35):
                    return False

        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        strategy = self._get_strategy(method_id)
        result = strategy.execute(frame, self.stop_event)
        self._wait_for_battle_end(is_sneaky=(method_id not in (2, 3, 4)))

        # Record raid statistics and notify webhook & native desktop notification
        self.loot_filter.stats.record_raid(*last_loot_detected, skips=skip_count)
        notify_raid_complete(
            last_loot_detected[0],
            last_loot_detected[1],
            last_loot_detected[2],
            self.loot_filter.stats.bases_skipped,
        )
        NotificationService.notify_mega_raid(*last_loot_detected)
        return result is False

    def _get_strategy(self, method_id: int) -> AttackStrategy:
        cb = getattr(self, "_status_callback", None)
        eq = getattr(self, "_earthquake_method", EARTHQUAKE_METHOD_CURVE)
        if method_id == 1:
            return TroopSpamStrategy(
                self.input, self.vision, self.config, self.stop_event, "sneaky", 15, status_callback=cb, earthquake_method=eq
            )
        elif method_id == 2:
            return TroopSpamStrategy(
                self.input, self.vision, self.config, self.stop_event, "superminion", 3.1, status_callback=cb, earthquake_method=eq
            )
        elif method_id == 3:
            return TroopSpamStrategy(
                self.input, self.vision, self.config, self.stop_event, "valkyrie", 5.5, status_callback=cb, earthquake_method=eq
            )
        elif method_id == 4:
            return EdragStrategy(
                self.input, self.vision, self.config, self.stop_event, status_callback=cb, earthquake_method=eq
            )
        else:
            return TroopSpamStrategy(
                self.input, self.vision, self.config, self.stop_event, "sneaky", 15, status_callback=cb, earthquake_method=eq
            )

    def _wait_for_battle_end(self, is_sneaky: bool) -> None:
        """Wait for the raid to finish.

        Sneaky Goblins are given 35-45s of active combat to path and loot resources
        before checking for surrender. If the battle concludes naturally earlier
        (all troops defeated or 100% destruction), exits immediately.
        """
        cb = getattr(self, "_status_callback", None)
        min_combat_seconds = 35 if is_sneaky else 60
        max_timeout = 50 if is_sneaky else 150
        start = time.time()

        logger.info(
            "Waiting for battle resolution (strategy=%s, min_combat=%ds, timeout=%ds)",
            "sneaky" if is_sneaky else "standard",
            min_combat_seconds,
            max_timeout,
        )

        while time.time() - start < max_timeout:
            self._check_stop()
            elapsed = time.time() - start

            frame = self.window.screenshot()
            if frame is not None:
                self._update_config_size(frame)

                # Check if battle has naturally concluded (victory/defeat summary or return home)
                ox, oy = self.vision.find_template(frame, "okay.png", threshold=0.75)
                if ox:
                    logger.info("Battle concluded naturally: okay.png detected after %.1fs", elapsed)
                    return

                rx, _ = self.vision.find_template(frame, "returnhome.png", threshold=0.75)
                if rx:
                    logger.info("Battle concluded naturally: returnhome.png detected after %.1fs", elapsed)
                    return

                # Check for endbattle button (appears when 3 stars reached or army depleted)
                bx, by = self.vision.find_template(frame, "endbattle.png", threshold=0.75)
                if bx:
                    logger.info("End battle button detected after %.1fs", elapsed)
                    self.input.click(bx, by, pause=0.2)
                    return

                # If combat duration has elapsed for sneaky goblins, safely surrender
                if is_sneaky and elapsed >= min_combat_seconds:
                    sx, sy = self.vision.find_template(frame, "surrender.png", threshold=0.75)
                    if sx:
                        logger.info("Loot phase complete (%.1fs elapsed). Surrendering raid.", elapsed)
                        if cb:
                            cb("Raid finished — surrendering")
                        self.input.click(sx, sy, pause=0.35)
                        # Handle potential surrender confirmation dialog
                        if self.stop_event.wait(0.5):
                            return
                        c_frame = self.window.screenshot()
                        if c_frame is not None:
                            cx, cy = self.vision.find_template(c_frame, "okay.png", threshold=0.75)
                            if cx:
                                self.input.click(cx, cy, pause=0.2)
                        return

            if self.stop_event.wait(0.8):
                return

        # Fallback if timeout reached: surrender if button is present
        logger.info("Battle timeout (%ds) reached; attempting surrender.", max_timeout)
        sx, sy = self._wait_for_image("surrender.png", timeout=3, error=False)
        if sx:
            self.input.click(sx, sy, pause=0.2)
            c_ox, c_oy = self._wait_for_image("okay.png", timeout=2, error=False)
            if c_ox:
                self.input.click(c_ox, c_oy, pause=0.2)

    def _return_home(self) -> bool:
        """Dismiss Okay if present, then wait for ``returnhome.png`` (+ ``returnhome2.png`` on 16:10) or ``chestclaim.png`` (mutually exclusive)."""
        ox, oy = self._wait_for_image("okay.png", timeout=2, error=False)
        if ox:
            self.input.click(ox, oy, pause=0.1)
        kind, hx, hy = self._wait_for_return_home_or_chest_claim(timeout=10)
        if kind == "return" and hx:
            self.input.click(hx, hy, pause=0.1)
            return ox is not None
        elif kind == "chest" and hx:
            logger.info("Post-battle UI: chestclaim.png (replacing return home); running chest flow")
            self.input.click(hx, hy, pause=0.2)
            if self.stop_event.wait(0.35):
                return ox is not None
            self._tap_empty_until_chest_continue()
        return ox is not None

    def _wait_for_return_home_or_chest_claim(
        self, timeout: int = 10
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None, None)
                continue
            self._update_config_size(frame)
            rx, ry = None, None
            returnhome_tpls = (
                ("returnhome.png", "returnhome2.png")
                if self.config.aspect_key == ASPECT_16_10
                else ("returnhome.png",)
            )
            for tpl in returnhome_tpls:
                rx, ry = self.vision.find_template(frame, tpl, threshold=_RETURN_HOME_THRESHOLD)
                if rx:
                    break
            if rx:
                return ("return", rx, ry)
            cx, cy = self.vision.find_template(frame, "chestclaim.png")
            if cx:
                return ("chest", cx, cy)
            if self.stop_event.wait(0.5):
                return (None, None, None)
        logger.warning("Timeout waiting for returnhome.png / returnhome2.png (16:10) or chestclaim.png")
        return (None, None, None)

    def _random_point_chest_tap_through(self) -> Tuple[int, int]:
        """Random point near center-right of the capture for chest tap-through (±85 px from anchor)."""
        w, h = self.config.width, self.config.height
        if w <= 1 or h <= 1:
            w, h = self.config.ref_width, self.config.ref_height
        cx = int(w * 0.75)
        cy = h // 2
        j = 85
        return (
            max(0, min(w - 1, cx + random.randint(-j, j))),
            max(0, min(h - 1, cy + random.randint(-j, j))),
        )

    def _tap_empty_until_chest_continue(self) -> None:
        """After ``chestclaim`` was clicked: tap center-right (±85px) until ``chestcontinue.png``, then click it (home)."""
        CHEST_TAP_TIMEOUT = 120.0
        deadline = time.time() + CHEST_TAP_TIMEOUT
        while time.time() < deadline:
            self._check_stop()
            nx, ny = self._random_point_chest_tap_through()
            self.input.click_at(nx, ny, rand=False)
            t0 = time.time()
            if self.stop_event.wait(0.15):
                return
            frame2 = self.window.screenshot()
            if frame2 is not None:
                self._update_config_size(frame2)
                tx, ty = self.vision.find_template(frame2, "chestcontinue.png")
                if tx:
                    logger.info("Chest reward: chestcontinue.png found; clicking (expect home village)")
                    self.input.click(tx, ty, pause=0.25)
                    return
            elapsed = time.time() - t0
            to_wait = max(0.05, 0.5 - elapsed)
            if self.stop_event.wait(to_wait):
                return
        logger.warning(f"chestcontinue.png not seen within {int(CHEST_TAP_TIMEOUT)}s after chest claim; continuing bot loop")

    def _is_star_bonus_claimed(self) -> bool:
        """True when neither emptystar nor glowstar is visible (bonus claimed or absent)."""
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        for template in ("emptystar.png", "glowstar.png"):
            _, confidence = self.vision.find_template_with_confidence(frame, template, threshold=0.0)
            if confidence >= _STAR_BONUS_THRESHOLD:
                return False
        return True

    def _is_bb_star_bonus_finished(self) -> bool:
        """True when ``bstar.png`` is not visible in the bottom half (BB star bonus attacks done)."""
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        bot_roi = VisionService.bottom_half_region(frame)
        _, confidence = self.vision.find_template_with_confidence(
            frame, _BB_STAR_BONUS_TEMPLATE, threshold=0.0, region=bot_roi
        )
        return confidence < _STAR_BONUS_THRESHOLD

    def _home_screen_recovery(self) -> None:
        """Ensures we are back at home screen. Dismisses any popup via Watchdog before considering home."""
        for _ in range(15):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(1):
                    return
                continue
            self._update_config_size(frame)
            if self.watchdog.check_and_recover(frame):
                continue
            ox, oy = self.vision.find_template(frame, "okay.png")
            if ox:
                self.input.click(ox, oy)
                if self.stop_event.wait(0.3):
                    return
                continue
            top_roi = VisionService.top_half_region(frame)
            hx, hy = self._find_home_village_builder(frame, top_roi)
            if hx:
                return
            if self.stop_event.wait(1):
                return

    def _switch_account_and_load_home(self, username: str) -> None:
        cb = getattr(self, "_status_callback", None)
        msg = f"Multi-run: switching to {username!r}"
        logger.info(msg)
        if cb:
            cb(msg)
        stx, sty = self._wait_for_image("settings.png")
        if not stx:
            raise RuntimeError("Multi-run: settings button not found")
        self.input.click(stx, sty, pause=0.25)
        cux, cuy = self._wait_for_image("changeuser.png")
        if not cux:
            raise RuntimeError("Multi-run: change user button not found")
        self.input.click(cux, cuy, pause=1.0)
        ucx, ucy = self._wait_for_player_name(
            username,
            timeout=25,
            min_confidence=70,
            tesseract_config="--psm 11",
            match_alnum_only=True,
            fuzzy_min_ratio=0.8,
            white_text=True,
        )
        if not ucx:
            err = f'Multi-run: could not find username "{username}" on screen (OCR)'
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self.input.click(ucx, ucy, pause=0.2)
        if self.stop_event.wait(1.0):
            self._check_stop()
        ax, ay = self._wake_home_and_wait_for_attack(timeout=30)
        if not ax:
            err = f"Multi-run: Home Village not ready after loading {username!r} (builder.png|gbuilder.png / attack.png timeout after login / leaving Builder Base)"
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self._loot_prev_resources = None

    def _wake_home_and_wait_for_attack(self, timeout: int = 30) -> Tuple[Optional[int], Optional[int]]:
        """
After switching accounts: dismiss idle UI, then poll the **top half** for village type
(``mbuilder.png`` = Builder Base; ``builder.png`` or ``gbuilder.png`` = Home Village). If Builder Base,
leave via :meth:`_leave_builder_base_with_nboat`. When Home Village is detected, return
``attack.png`` coordinates from the **bottom half** (battle bar) once visible — same
template as :meth:`_find_match_and_attack` uses to start battles.
Each iteration dismisses ``okay.png`` / ``exit.png`` if present, then village / attack logic; else nudge.
"""
        frame = self.window.screenshot()
        self._update_config_size(frame)
        empty_pt = self.config.get_point("empty")
        self.input.click(empty_pt, pause=0.2, rand=False)
        delay = random.uniform(0.1, 0.2)
        if self.stop_event.wait(delay):
            return (None, None)
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                self._nudge_view_to_reveal_attack()
                if self.stop_event.wait(0.35):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.25):
                    return (None, None)
                continue
            top_roi = VisionService.top_half_region(frame)
            mx, my = self.vision.find_template(frame, "mbuilder.png", region=top_roi)
            if mx:
                logger.info("Account loaded in Builder Base (mbuilder.png); leaving to Home Village")
                cb = getattr(self, "_status_callback", None)
                if cb:
                    cb("Multi-run: Builder Base on login — leaving (nboat)")
                self._leave_builder_base_with_nboat(settle_before_drag=False)
                if self.stop_event.wait(1.0):
                    return (None, None)
                continue
            hx, hy = self._find_home_village_builder(frame, top_roi)
            if hx:
                bot_roi = VisionService.bottom_half_region(frame)
                ax, ay = self.vision.find_template(frame, "attack.png", region=bot_roi)
                if ax:
                    return (ax, ay)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.35):
                return (None, None)
        return (None, None)

    def _detect_village_type(self, frame=None) -> Optional[str]:
        """Return ``"home"``, ``"builder"``, or ``None`` from top-half builder portraits."""
        if frame is None:
            frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self._update_config_size(frame)
        top_roi = VisionService.top_half_region(frame)
        mx, my = self.vision.find_template(frame, "mbuilder.png", region=top_roi)
        if mx:
            return "builder"
        hx, hy = self._find_home_village_builder(frame, top_roi)
        if hx:
            return "home"
        return None

    def _go_to_builder_base_with_boat(self) -> bool:
        """Home Village → Builder Base via ``boat.png``."""
        self._check_stop()
        bx, by = self._wait_for_image("boat.png", timeout=15, error=False)
        if not bx:
            logger.warning("boat.png not found — cannot switch to Builder Base")
            return False
        self.input.click(bx, by, pause=0.25)
        if self.stop_event.wait(1.0):
            return False
        mx, my = self._wait_for_image("mbuilder.png", timeout=15, error=False)
        if not mx:
            logger.warning("mbuilder.png not found after boat — may still be in Home Village")
            return False
        return True

    def _ensure_correct_village(self, builder_base: bool) -> None:
        """Before farming: switch villages if the wrong builder portrait is showing."""
        self._check_stop()
        self.input.click(self.config.get_point("empty"), pause=0.15)
        if self.stop_event.wait(0.2):
            return
        village = self._detect_village_type()
        if builder_base:
            if village == "builder":
                return
            if village == "home":
                logger.info("Startup: in Home Village but Builder Base was selected — taking boat")
                self._go_to_builder_base_with_boat()
                return
            logger.warning("Startup: could not detect village (expected Builder Base)")
            return
        else:
            if village == "home":
                return
            if village == "builder":
                logger.info("Startup: in Builder Base but Home Village was selected — leaving (nboat)")
                self._leave_builder_base_with_nboat()
                return
            logger.warning("Startup: could not detect village (expected Home Village)")
            return

    def _leave_builder_base_with_nboat(self, settle_before_drag: bool = True) -> None:
        """
Pan down-left from screen center (~500px), then click ``nboat.png`` to return to Home Village.
Does not check ``mbuilder.png`` first — call only when a BB→HV trip is intended.

``settle_before_drag``: small delay after prior UI (e.g. collect clicks) before capturing
dimensions and dragging.
"""
        self._check_stop()
        if settle_before_drag:
            if self.stop_event.wait(0.75):
                self._check_stop()
        logger.info("Leaving Builder Base (drag + nboat)")
        cb = getattr(self, "_status_callback", None)
        if cb:
            cb("Returning to Home Village")
        self.input.click(self.config.get_point("empty"), pause=0.15)
        frame = self.window.screenshot()
        if frame is not None:
            self._update_config_size(frame)
            self._dismiss_okay_or_exit_on_frame(frame)
        self._bb_pan_down_left_from_center()
        nx, ny = self._wait_for_image("nboat.png", timeout=12, error=False)
        if nx:
            self.input.click(nx, ny, pause=0.25)
            return
        logger.warning("nboat.png not found after Builder Base drag — may still be in Builder Base")

    def _collect_home_village_resources(self) -> None:
        """Tap the Home Village collect bubbles if visible. Caller must already be on home."""
        cb = getattr(self, "_status_callback", None)
        logger.info("Collect: Home Village (hgold, helixir, hdelixir)")
        if cb:
            cb("Collecting Home Village resources")
        for tpl in ("hgold.png", "helixir.png", "hdelixir.png"):
            self._check_stop()
            rx, ry = self._find_template_once(tpl, threshold=0.7)
            if rx:
                self.input.click(rx, ry, pause=0.15)

    def _collect_builder_base_resources(self) -> None:
        """
Tap the Builder Base collect bubbles, then run the clock boost chain.

Caller must already be in Builder Base — travel is the caller's job, so that
turning collection off never removes a boat trip (see :meth:`_run_account_session`).

The clock boost is counted as collecting: it costs nothing and is claimed on the
same visit, so it follows the same toggle as the resource bubbles.
"""
        cb = getattr(self, "_status_callback", None)
        logger.info("Collect: Builder Base (bgold, belixir, bgem, clock boost)")
        if cb:
            cb("Collecting Builder Base resources")
        for tpl in ("bgold.png", "belixir.png", "bgem.png"):
            self._check_stop()
            rx, ry = self._find_template_once(tpl, threshold=0.7)
            if rx:
                self.input.click(rx, ry, pause=0.15)
        self._check_stop()
        cx, cy = self._wait_for_image("bclock.png", timeout=2, error=False)
        if cx:
            self.input.click(cx, cy, pause=0.2)
            if self.stop_event.wait(1.0):
                self._check_stop()
            cbx, cby = self._wait_for_image("clockboost.png", timeout=10, error=False)
            if cbx:
                self.input.click(cbx, cby, pause=0.2)
            if self.stop_event.wait(1.0):
                self._check_stop()
            bux, buy = self._wait_for_image("boost.png", timeout=10, error=False)
            if bux:
                self.input.click(bux, buy, pause=0.15)

    def _frame_shows_supercell_login_prompt(self, frame) -> bool:
        """True if OCR sees the Supercell ID login line (list scroll won't help)."""
        if frame is None or frame.size == 0:
            return False
        words = self.vision.find_words_ocr(
            frame,
            query=None,
            min_confidence=20,
            preprocess=True,
            tesseract_config="--psm 11",
            white_text=True,
        )
        blob = " ".join(w.text for w in words).lower()
        if "supercell id" in blob:
            return True
        if "log in" in blob and "supercell" in blob:
            return True
        return False

    def _scroll_player_list_with_drag(self, frame) -> None:
        """Drag ~200px upward from lower-right (client coords) to scroll the change-user list."""
        if frame is None or frame.size == 0:
            return
        h, w = frame.shape[:2]
        x1 = int(w * 0.86) + random.randint(-15, 15)
        x1 = max(int(w * 0.72), min(w - 8, x1))
        y1 = int(h * 0.86) + random.randint(-12, 12)
        y1 = max(int(h * 0.55), min(h - 12, y1))
        y2 = max(int(h * 0.12), y1 - 200)
        x2 = x1
        self.input.mouse_down(x1, y1)
        self.input.human_move(x1, y1, x2, y2, duration=random.uniform(0.28, 0.42))
        self.input.mouse_up(x2, y2)

    def _wait_for_player_name(
        self,
        text: str,
        timeout: int = 25,
        error: bool = True,
        region: Optional[Tuple[int, int, int, int]] = None,
        **ocr_kwargs,
    ) -> Tuple[Optional[int], Optional[int]]:
        """
Like :meth:`_wait_for_text`, but after each failed OCR pass drags upward in the lower-right
to scroll the account list before trying again.

OCR is limited to the right half of the window unless ``region`` is passed explicitly.
"""
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            roi = region if region is not None else VisionService.right_half_region(frame)
            x, y = self.vision.find_word_on_screen(frame, text, region=roi, **ocr_kwargs)
            if x:
                return (x, y)
            if self._frame_shows_supercell_login_prompt(frame):
                msg = f'Multi-run: "Log in to Supercell ID" is showing and {text!r} was not found — log in or dismiss that screen, then retry.'
                logger.warning(msg)
                cb = getattr(self, "_status_callback", None)
                if cb:
                    cb(msg)
                raise RuntimeError(msg)
            self._scroll_player_list_with_drag(frame)
            if self.stop_event.wait(0.45):
                return (None, None)
        if error:
            logger.warning(f"Timeout waiting for player name OCR match: {text!r}")
        return (None, None)

    def _wait_for_text(
        self,
        text: str,
        timeout: int = 10,
        error: bool = True,
        region: Optional[Tuple[int, int, int, int]] = None,
        **ocr_kwargs,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Poll screenshots until OCR finds ``text`` (substring match). Returns click center."""
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            x, y = self.vision.find_word_on_screen(frame, text, region=region, **ocr_kwargs)
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f"Timeout waiting for OCR text containing {text!r}")
        return (None, None)

    def _ensure_valkyrie_army_from_recipes(self) -> bool:
        """If Valkyrie army template is missing, load it from Saved Recipes. Returns False on failure."""
        vx, vy = self._wait_for_image("valkarmy.png", timeout=3, error=False)
        if vx:
            return True
        sx, sy = self._wait_for_image("savedrecipes.png")
        if not sx:
            logger.warning("Saved Recipes button not found while ensuring Valkyrie army")
            return False
        self.input.click(sx, sy, pause=0.2)
        rx, ry = self._wait_for_image("valkrecipe.png")
        if not rx:
            logger.warning("Valkyrie recipe template not found")
            return False
        ux, uy = self._wait_for_image("use.png", y_anchor=ry, y_slop=200)
        if not ux:
            logger.warning("Use button not found near Valkyrie recipe row")
            return False
        self.input.click(ux, uy, pause=0.2)
        if self.stop_event.wait(0.35):
            return False
        vx2, _ = self._wait_for_image("valkarmy.png", timeout=5, error=False)
        if not vx2:
            logger.warning("valkarmy.png still not visible after applying saved recipe")
            return False
        return True

    def _search_region_for_template(
        self,
        frame,
        template: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        y_anchor: Optional[int] = None,
        y_slop: int = 200,
    ) -> Optional[Tuple[int, int, int, int]]:
        if region is not None:
            return region
        if y_anchor is not None:
            h, w = frame.shape[:2]
            y0 = max(0, y_anchor - y_slop)
            y1 = min(h, y_anchor + y_slop)
            return (0, y0, w, y1 - y0)
        if template in TOP_HALF_BOT_TEMPLATES:
            return VisionService.top_half_region(frame)
        if template in BOTTOM_HALF_BOT_TEMPLATES:
            return VisionService.bottom_half_region(frame)
        return None

    def _find_template_once(
        self,
        template: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        y_anchor: Optional[int] = None,
        y_slop: int = 200,
        threshold: float = 0.8,
    ) -> Tuple[Optional[int], Optional[int]]:
        """One screenshot; match template or return (None, None). No polling."""
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None:
            return (None, None)
        self._update_config_size(frame)
        search_region = self._search_region_for_template(
            frame, template, region, y_anchor, y_slop
        )
        return self.vision.find_template(
            frame, template, threshold=threshold, region=search_region
        )

    def _wait_for_any_image(
        self,
        templates: tuple[str, ...],
        timeout: int = 10,
        error: bool = True,
        threshold: float = 0.8,
        region: Optional[Tuple[int, int, int, int]] = None,
        region_from_frame: Optional[Callable] = None,
    ) -> Tuple[Optional[int], Optional[int]]:
        """First ordered template match wins (checked left-to-right each frame)."""
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.2):
                    return (None, None)
                continue
            self._update_config_size(frame)
            search_region = region
            if search_region is None and region_from_frame is not None:
                search_region = region_from_frame(frame)
            for template in templates:
                tpl_region = search_region
                if tpl_region is None:
                    tpl_region = self._search_region_for_template(
                        frame, template, None, None, 200
                    )
                x, y = self.vision.find_template(
                    frame, template, threshold=threshold, region=tpl_region
                )
                if x:
                    return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f"Timeout waiting for any of {templates}")
        return (None, None)

    def _wait_for_image(
        self,
        template: str,
        timeout: int = 10,
        error: bool = True,
        region: Optional[Tuple[int, int, int, int]] = None,
        y_anchor: Optional[int] = None,
        y_slop: int = 200,
        threshold: float = 0.8,
    ) -> Tuple[Optional[int], Optional[int]]:
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.2):
                    return (None, None)
                continue
            self._update_config_size(frame)
            search_region = self._search_region_for_template(
                frame, template, region, y_anchor, y_slop
            )
            x, y = self.vision.find_template(
                frame, template, threshold=threshold, region=search_region
            )
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f"Timeout waiting for {template}")
        return (None, None)
