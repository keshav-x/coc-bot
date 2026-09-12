import time
import random
import threading
from typing import Callable, List, Optional, Tuple
from app.config import ASPECT_16_10, ASPECT_16_9, Config
from app.core.strategies import AttackStrategy, EdragStrategy, TroopSpamStrategy, _EDRAG_DELAY
from app.core.upgrader import AUTO_UPGRADE_MODES, LIVE_UPGRADE_MODES, MODE_OFF, UpgradeAdvisor
from app.core.village_state import read_hud_triplet_stable, read_village_state, read_village_state_stable
from app.services.input import InputService
from app.services.vision import BOTTOM_HALF_BOT_TEMPLATES, TOP_HALF_BOT_TEMPLATES, VisionService
from app.services.window import WindowService
from app.utils.common import get_template_path
from app.utils.logger import setup_logger
from app.utils.player_list_store import PlayerEntry
from app.utils.profile_settings_store import EARTHQUAKE_METHOD_CURVE
from app.core.run_plan import BUILDER as RP_BUILDER, HOME as RP_HOME, RunPlan
from app.core.loot_filter import LootFilterEngine
from app.services.notifications import NotificationService
from app.services.webhook import (
    notify_bot_started,
    notify_break,
    notify_raid_complete,
)
from app.services.antiban import AntiBanService

logger = setup_logger('BotCore')
_HOME_VILLAGE_BUILDER_TEMPLATES = ('builder.png', 'gbuilder.png')
_WALL_OCR_RETRY_DRAG_BASELINE: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    ASPECT_16_9: ((1300, 280), (1300, 830)),
    ASPECT_16_10: ((1300, 280), (1300, 980)) }
_BB_BABY_DRAGON_RECLICK_WAIT = 10
_BB_RETURN_HOME_TEMPLATE = 'breturnhome.png'
_BB_RETURN_HOME_TEMPLATE_1080P = 'breturnhome1920.png'
_BB_1080P_CAPTURE_SIZE = (1920, 1080)
_BB_1080P_SIZE_TOLERANCE = 40
_BB_TEMPLATE_SUPPRESS_PAD = 0.1
_BB_FULL_ELIXIR_CART_TEMPLATES = ('fullecart.png', 'fullecart2.png', 'fullecart3.png')
_BB_COLLECT_TEMPLATE = 'collect.png'
_BB_STAR_BONUS_TEMPLATE = 'bstar.png'
_BB_BATTLE_STAR_TEMPLATE = 'bbstar.png'
_BB_BATTLE_MACHINE_TEMPLATE = 'battlemachine.png'
_BB_FLYING_MACHINE_TEMPLATE = 'flyingmachine.png'
_BB_GOLD_PRIORITISE_MIN_STARS = 2
_BB_RETURN_HOME_END_BATTLE_RETRIES = 5
_STAR_BONUS_THRESHOLD = 0.75
_TROOP_FAILURE_LIMIT = 4
_TROOP_RETRY_WAIT_SECONDS = 15  # training is instant since the Mar 2025 "Clash Anytime" update — this only lets the UI settle
_RELOAD_GRACE_SECONDS = 180  # let a quick phone check finish before reconnecting over it
_WALL_BATCH_MAX_ADDS = 15
_WALL_MENU_SCROLL_STEPS = 8  # OCR positions polled: as-opened + 7 wheel nudges down the list
_WALL_MENU_WHEEL_CLICKS = 2  # ~3-4 rows per nudge; the OCR band spans the whole popup so a nudge cannot jump the Wall row past it
_WALL_ROW_STABLE_TOL = 30  # ref px: max y drift between consecutive frames before the row is trusted for a click
_AUTO_UPGRADE_SCAN_INTERVAL_SECONDS = 600  # full popup scan is OCR-heavy (~15-25s); keep it rare vs the ~35s attack cycle
_IDLE_RECHECK_SECONDS = 300  # while idling (storages full, nothing startable): wake, recover the screen, re-read state
# Loot-tracker plausibility caps per snapshot interval (one battle): a raid tops out
# well under these even with boosts — anything larger is an OCR misread that slipped
# past the ≥0 filter (live repro: "+15.5M elixir" in one battle).
_LOOT_DELTA_MAX_MAIN = 3000000
_LOOT_DELTA_MAX_DARK = 50000
_WALL_MENU_SCROLL_BASELINE: dict[str, tuple[int, int]] = {
    ASPECT_16_9: (1305, 605),
    ASPECT_16_10: (1305, 672) }

class Bot:
    '''Main Bot Logic.'''
    
    def __init__(self):
        self.config = Config()
        self.window = WindowService()
        self.stop_event = threading.Event()
        self.input = InputService(self.window, self.stop_event)
        self.vision = VisionService()
        self.running = False
        self._earthquake_method = EARTHQUAKE_METHOD_CURVE
        self._loot_totals = (0, 0, 0)
        self._loot_prev_resources = None
        self._loot_session_start_mono = 0
        self._loot_callback = None
        self._suppress_loot_negative_error_once = False
        self._last_hud_triplet = None
        self.antiban = AntiBanService()
        self.loot_filter = LootFilterEngine()

    
    def start(self, method, run_time_minutes = 0, star_bonus = False, status_callback = None, loot_callback = None, multi_run_players = None, ranked_fill = False, upgrade_walls = False, earthquake_method = EARTHQUAKE_METHOD_CURVE, builder_base = False, loot_prioritise = 'both', wall_upgrade_threshold = 0, auto_upgrade = MODE_OFF, reserve_builders = 1, state_callback = None, upgrade_order = None):
        '''Starts the bot loop. With ``multi_run_players``, runs a full session per enabled player.
        ``run_time_minutes <= 0`` (single Home Village runs only) means UNLIMITED — farm,
        upgrade and idle until the user stops the bot ("run until maxed").'''
        self._status_callback = status_callback
        self._loot_callback = loot_callback
        self._state_callback = state_callback
        self._earthquake_method = earthquake_method
        if not self.window.find_window():
            raise RuntimeError('Clash of Clans window not found. Please ensure the game is open.')
        self._reset_loot_session()
        self._emit_loot_update()
        self.running = True
        self.stop_event.clear()
        unlimited = not star_bonus and multi_run_players is None and not builder_base and int(run_time_minutes or 0) <= 0
        duration = 900 if star_bonus else (0 if unlimited else max(1, int(run_time_minutes)) * 60)
        mr = multi_run_players is not None
        self._builder_base = builder_base
        self._loot_prioritise = loot_prioritise
        self._wall_upgrade_threshold = max(0, int(wall_upgrade_threshold or 0))
        self._auto_upgrade_mode = auto_upgrade if auto_upgrade in AUTO_UPGRADE_MODES else MODE_OFF
        self._auto_upgrade_last_scan = 0
        self._reserve_builders = max(0, int(reserve_builders or 0))
        self._upgrade_order = upgrade_order
        self._advisor = None  # one UpgradeAdvisor per session (it holds execution cooldowns)
        if isinstance(method, RunPlan):
            plan = method
            is_empty_val = plan.is_empty() if callable(getattr(plan, 'is_empty', None)) else getattr(plan, 'is_empty', False)
            if is_empty_val:
                raise RuntimeError('Run plan is empty — include a village or resource collection.')
            self.antiban.reset_session()
            self.loot_filter.stats.reset()
            self._builder_base = (plan.step_for(RP_BUILDER) is not None)
            notify_bot_started(plan.describe())
            logger.info(f'Bot started with Plan: {plan.describe()}, Earthquake: {earthquake_method}')
            try:
                if not plan.rotating:
                    self._run_account_session(plan)
                else:
                    queue = plan.enabled_players
                    if not queue:
                        raise RuntimeError('Multi-run: no players marked Run')
                    self._ensure_correct_village(builder_base = False)
                    for player in queue:
                        self._check_stop()
                        self._switch_account_and_load_home(player.name)
                        self._check_stop()
                        self._run_account_session(plan)
                        self._check_stop()
            except InterruptedError:
                logger.info('Bot stopped by user.')
            except Exception as e:
                logger.error(f'Bot crashed: {e}', exc_info = True)
                raise
            finally:
                self.running = False
                self._earthquake_method = EARTHQUAKE_METHOD_CURVE
                logger.info('Bot stopped.')
            return

        logger.info(f'''Bot started. Method: {method}, Time: {'unlimited' if unlimited else f'{run_time_minutes}m'}, StarBonus: {star_bonus}, MultiRun: {mr}, RankedFill: {ranked_fill}, UpgradeWalls: {upgrade_walls}, WallThreshold: {self._wall_upgrade_threshold}, AutoUpgrade: {self._auto_upgrade_mode}, ReserveBuilders: {self._reserve_builders}, Earthquake: {earthquake_method}, BuilderBase: {builder_base}, LootPrioritise: {loot_prioritise}''')

        try:

            if not multi_run_players is None:
                self._ensure_correct_village(builder_base = False)
                queue = [ p for p in multi_run_players if p.enabled ]
                if not queue:
                    raise RuntimeError('Multi-run: no players marked Run')
                for player in queue:
                    self._check_stop()
                    self._switch_account_and_load_home(player.name)
                    self._check_stop()
                    self._run_loop(method, duration, star_bonus, ranked_fill, upgrade_walls)
                    self._check_stop()
                    if self._builder_base:
                        self._multi_run_builder_base_after_session()
                    self._check_stop()
            elif self._builder_base:  # [recovered: decompiler nested this single-run block inside the multi-run `if`]
                self._ensure_correct_village(builder_base = True)
                self._run_builder_base_loop(duration, star_bonus = star_bonus)
            else:
                self._ensure_correct_village(builder_base = False)
                self._run_loop(method, duration, star_bonus, ranked_fill, upgrade_walls)
        except InterruptedError:
            logger.info('Bot stopped by user.')
        except Exception as e:
            logger.error(f'''Bot crashed: {e}''', exc_info = True)
            raise
        finally:
            self.running = False
            self._earthquake_method = EARTHQUAKE_METHOD_CURVE
            logger.info('Bot stopped.')

    
    def stop(self):
        '''Signals the bot to stop.'''
        self.running = False
        self.stop_event.set()

    def _run_account_session(self, plan: RunPlan) -> None:
        home_step = plan.step_for(RP_HOME)
        builder_step = plan.step_for(RP_BUILDER)
        visit_builder = builder_step is not None
        builder_only = (home_step is None) and visit_builder
        if builder_only:
            self._ensure_correct_village(builder_base = True)
        else:
            self._ensure_correct_village(builder_base = False)
            if home_step is not None:
                self._loot_prioritise = home_step.loot_prioritise
                self._run_loop(
                    home_step.method,
                    home_step.duration_seconds,
                    star_bonus = home_step.star_bonus,
                    ranked_fill = home_step.ranked_fill,
                    upgrade_walls = home_step.upgrade_walls,
                )
                self._check_stop()
            if plan.collect_resources:
                self._multi_run_collect_home_village_resources()
                self._check_stop()
            if not visit_builder:
                return
            if not self._go_to_builder_base_with_boat():
                msg = 'Builder Base: boat not found — skipping the Builder Base leg'
                logger.warning(msg)
                cb = getattr(self, '_status_callback', None)
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
                    star_bonus = builder_step.star_bonus,
                    method = builder_step.method,
                )
        finally:
            if not builder_only or plan.rotating:
                self._leave_builder_base_with_nboat(settle_before_drag = True)

    
    def _reset_loot_session(self):
        '''Reset counters for a new :meth:`start` — no disk persistence.'''
        self._loot_totals = (0, 0, 0)
        self._loot_prev_resources = None
        self._loot_session_start_mono = time.monotonic()
        self._suppress_loot_negative_error_once = False
        self._last_hud_triplet = None
        self._gold_pinned = False
        self._elixir_pinned = False
        if hasattr(self, "loot_filter") and hasattr(self.loot_filter, "stats"):
            self.loot_filter.stats.reset()

    
    def _emit_loot_update(self):
        cb = self._loot_callback
        if not cb:
            return None
        (g, el, de) = self._loot_totals
        elapsed = max(0, time.monotonic() - float(self._loot_session_start_mono))
        cb(g, el, de, elapsed)

    
    def _record_completed_raid_and_update_loot(self):
        '''Always records a completed raid into SessionStats and updates UI telemetry.
        Uses actual HUD storage delta if measured; falls back to accepted target base loot (75% extraction).'''
        if not getattr(self, '_raid_just_completed', False):
            return None

        target_loot = getattr(self, '_last_accepted_target_loot', (0, 0, 0))
        skips = getattr(self, '_last_raid_skips', 0)

        # 1. Try reading the HUD triplet for exact storage delta
        triplet = self._read_hud_triplet_stable()
        prev = self._loot_prev_resources

        gain_g = 0
        gain_el = 0
        gain_de = 0
        used_hud = False

        if triplet is not None and prev is not None:
            (cur_g, cur_el, cur_de) = triplet
            (lg, le, ld) = prev
            raw_dg = cur_g - lg
            raw_del = cur_el - le
            raw_dde = cur_de - ld

            g_cand = max(0, raw_dg) if raw_dg >= -5000 else 0
            el_cand = max(0, raw_del) if raw_del >= -2000 else 0
            de_cand = max(0, raw_dde) if raw_dde >= -500 else 0

            if g_cand <= _LOOT_DELTA_MAX_MAIN and el_cand <= _LOOT_DELTA_MAX_MAIN and de_cand <= _LOOT_DELTA_MAX_DARK:
                if g_cand > 0 or el_cand > 0 or de_cand > 0:
                    gain_g = g_cand
                    gain_el = el_cand
                    gain_de = de_cand
                    used_hud = True

        if triplet is not None:
            self._last_hud_triplet = triplet
            self._loot_prev_resources = triplet

        # 2. Fallback to target base loot if HUD delta was not measured or storages full
        if not used_hud:
            (tg_raw, te_raw, td_raw) = target_loot
            gain_g = int(tg_raw * 0.75) if tg_raw > 0 else 0
            gain_el = int(te_raw * 0.75) if te_raw > 0 else 0
            gain_de = int(td_raw * 0.75) if td_raw > 0 else 0
            logger.info(
                'Loot tracker: using target base fallback (+%s G, +%s E, +%s DE) [HUD read=%s]',
                f'{gain_g:,}', f'{gain_el:,}', f'{gain_de:,}', 'yes' if triplet is not None else 'no'
            )

        # 3. Always increment session totals and record raid telemetry
        (tg, te, td) = self._loot_totals
        self._loot_totals = (tg + gain_g, te + gain_el, td + gain_de)
        rec = self.loot_filter.stats.record_raid(gain_g, gain_el, gain_de, skips=skips)
        logger.info(
            'Loot tracker: RAID #%d RECORDED: +%s / +%s / +%s (G/E/DE, %d skips) -> session totals %s / %s / %s',
            self.loot_filter.stats.raids_completed,
            f'{gain_g:,}', f'{gain_el:,}', f'{gain_de:,}', skips,
            f'{self._loot_totals[0]:,}', f'{self._loot_totals[1]:,}', f'{self._loot_totals[2]:,}'
        )
        notify_raid_complete(gain_g, gain_el, gain_de, skips)
        self._last_raid_skips = 0
        self._raid_just_completed = False

        # 4. Immediately notify UI
        self._emit_loot_update()
        return rec

    def _loot_snapshot_before_attack(self):
        '''Establish or refresh the pre-attack HUD baseline.'''
        if getattr(self, '_raid_just_completed', False):
            self._record_completed_raid_and_update_loot()
            return None

        triplet = self._read_hud_triplet_stable()
        if triplet is None:
            self._emit_loot_update()
            return None
        self._last_hud_triplet = triplet
        (cur_g, cur_el, cur_de) = triplet
        prev = self._loot_prev_resources
        if prev is not None:
            self._gold_pinned = cur_g == prev[0]
            self._elixir_pinned = cur_el == prev[1]
        self._loot_prev_resources = triplet
        self._emit_loot_update()
        self._suppress_loot_negative_error_once = False

    
    def _check_stop(self):
        if self.stop_event.is_set():
            raise InterruptedError('Bot stopped by user')

    
    def _update_config_size(self, frame):
        '''Reload aspect profile if screenshot size implies a different template folder.'''
        self.config.set_target_size_from_frame(frame)

    
    def _scroll_point(self):
        '''Scroll anchor in authoring space [1000,1000]; scaled to current capture.'''
        (x, y) = self.config.scale_point([
            1000,
            1000])
        return (x, y)

    
    def _nudge_view_to_reveal_attack(self):
        '''Click ``empty`` (``data.json``) and scroll at anchor to nudge village until Attack is findable.'''
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        self.input.scroll(*self._scroll_point(), 5)

    
    def _find_home_village_builder(self, frame, region):
        for name in _HOME_VILLAGE_BUILDER_TEMPLATES:
            (x, y) = self.vision.find_template(frame, name, region = region)
            if not x:
                continue
            return (x, y)
        return (None, None)

    
    def _wall_menu_drag_to_bottom(self):
        '''Drag the builder upgrade list to its bottom so ``Wall`` (list end) is revealed.

Touch-style swipe up: click low in the list, drag to the top, release — the reverse of
the old wheel scroll. Baseline coords are scaled via :meth:`Config.scale_point`. Dragging
past the bottom is a harmless no-op, so this can be called repeatedly.
'''
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning('wall menu drag: unknown aspect %r; skipping drag', self.config.aspect_key)
            return None
        (top_ref, bottom_ref) = pair
        top = self.config.scale_point([
            top_ref[0],
            top_ref[1]])
        bottom = self.config.scale_point([
            bottom_ref[0],
            bottom_ref[1]])
        (x_top, y_top) = (int(top[0]), int(top[1]))  # [recovered: pycdc reversed STORE_FAST_STORE_FAST pairs]
        (x_bot, y_bot) = (int(bottom[0]), int(bottom[1]))
        self.input.move(x_bot, y_bot)
        self.input.mouse_down(x_bot, y_bot)
        
        try:
            self.input.human_move(x_bot, y_bot, x_top, y_top, duration = 0.5)
            self.input.mouse_up(x_top, y_top)
            return None
        except:
            self.input.mouse_up(x_top, y_top)


    
    def _wall_menu_drag_retry_nudge(self):
        '''Vertical drag in the builder list when ``wall`` OCR misses (~0.5s eased move + hold pause).'''
        pair = _WALL_OCR_RETRY_DRAG_BASELINE.get(self.config.aspect_key)
        if pair is None:
            logger.warning('wall OCR retry drag: unknown aspect %r; skipping drag', self.config.aspect_key)
            return None
        (p1_ref, p2_ref) = pair
        p1 = self.config.scale_point([
            p1_ref[0],
            p1_ref[1]])
        p2 = self.config.scale_point([
            p2_ref[0],
            p2_ref[1]])
        (x_top, y_top) = (int(p1[0]), int(p1[1]))
        (x_bot, y_bot) = (int(p2[0]), int(p2[1]))
        self.input.move(x_bot, y_bot)
        self.input.mouse_down(x_bot, y_bot)
        
        try:
            self.input.human_move(x_bot, y_bot, x_top, y_top, duration = 0.5)
            if self.stop_event.wait(0.3):
                self.input.mouse_up(x_top, y_top)
                return None
            self.input.mouse_up(x_top, y_top)
            return None
        except:
            self.input.mouse_up(x_top, y_top)

    def _wall_menu_nudge_drag(self):
        '''Gentle vertical touch drag in builder popup (150-180px) to scroll down reliably without flinging.'''
        (sx, sy) = self._wall_menu_scroll_point()
        offset = int(self.config.scale_scalar(85))
        y_bot = int(sy + offset)
        y_top = int(sy - offset)
        self.input.move(sx, y_bot)
        self.input.mouse_down(sx, y_bot)
        try:
            self.input.human_move(sx, y_bot, sx, y_top, duration = 0.28)
            if self.stop_event.wait(0.12):
                self.input.mouse_up(sx, y_top)
                return None
            self.input.mouse_up(sx, y_top)
            return None
        except Exception:
            self.input.mouse_up(sx, y_top)
            return None



    
    def _find_wall_row_once(self):
        '''One fresh screenshot → Wall label OCR, both polarities (dark popup text first).'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        # Blob filter kills the small label glyphs at this capture size (live A/B:
        # 0/83 hits with filter, 14/83 without), keep it off.
        for white in (False, True):
            pt = VisionService.find_wall_labels_top_center_ocr(frame, white_text = white, cc_filter_blobs = False)
            if pt:
                return pt
        return None


    def _wall_menu_scroll_point(self):
        '''Wheel target inside the builder popup body (authoring space, per aspect).'''
        ref = _WALL_MENU_SCROLL_BASELINE.get(self.config.aspect_key)
        if ref is None:
            ref = _WALL_MENU_SCROLL_BASELINE[ASPECT_16_10]
        (x, y) = self.config.scale_point([
            ref[0],
            ref[1]])
        return (int(x), int(y))


    def _should_upgrade_walls(self):
        '''True when a full-storage hero-bar icon shows, or HUD gold/elixir is at/above the configured threshold.'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        (gx, gy) = VisionService.find_active_hgoldfull(frame)
        (ex, ey) = VisionService.find_active_helixirfull(frame)
        if gx is not None or ex is not None:
            logger.info('Wall upgrades: full-storage icon detected')
            return True
        threshold = int(getattr(self, '_wall_upgrade_threshold', 0) or 0)
        triplet = getattr(self, '_last_hud_triplet', None)
        if triplet is None:
            groups = VisionService.extract_top_right_hud_numbers(frame)
            triplet = VisionService.parse_hud_resources_triplet(groups)
        if triplet is not None:
            (gold, elixir, _) = triplet
            if threshold > 0:
                if gold >= threshold or elixir >= threshold:
                    logger.info('Wall upgrades: loot gold=%s elixir=%s reached threshold %s', gold, elixir, threshold)
                    return True
            else:
                if gold >= 2000000 or elixir >= 2000000:
                    logger.info('Wall upgrades: high HUD balance gold=%s elixir=%s', gold, elixir)
                    return True
        return False


    def _deselect_wall_ui(self):
        '''Tap empty ground to close the wall selection bar / gem dialog remnants. The wall
bar has no X button — while it is open, the next tap anywhere is swallowed by the
deselect, which would eat the upcoming Attack click.'''
        self._dismiss_open_popup()
        self.input.click(pause = 0.3, *self.config.get_point('empty'))


    def _maybe_upgrade_walls(self, upgrade_walls):
        '''Upgrade walls on home when enabled and loot is high enough (threshold or full storages).'''
        if not upgrade_walls or not self._should_upgrade_walls():  # [recovered: decompiler dropped the second `not`, so it upgraded only when storages were NOT full]
            return None
        cb = getattr(self, '_status_callback', None)
        if cb:
            cb('Upgrading walls...')
        self._loot_snapshot_before_attack()
        for _ in range(2):
            self._check_stop()
            self._upgrade_walls()
            self._deselect_wall_ui()
        # Re-baseline after spending on walls so the spend is not counted as negative raid loot
        triplet = self._read_hud_triplet_stable()
        if triplet is not None:
            self._loot_prev_resources = triplet
        self._suppress_loot_negative_error_once = True


    def _maybe_auto_upgrade(self, force = False):
        '''Interval-gated builder-popup scan + upgrade decision/execution (see
        UpgradeAdvisor). ``force=True`` bypasses the interval (used when storages fill
        up — the idle gate needs a spend attempt NOW, not in 10 minutes). A failure
        here must never take down the farm loop. Returns the PassResult or None.'''
        mode = getattr(self, '_auto_upgrade_mode', MODE_OFF)
        if mode == MODE_OFF:
            return None
        now = time.monotonic()
        if not force and now - getattr(self, '_auto_upgrade_last_scan', 0) < _AUTO_UPGRADE_SCAN_INTERVAL_SECONDS:
            return None
        self._auto_upgrade_last_scan = now
        try:
            if getattr(self, '_advisor', None) is None:
                self._advisor = UpgradeAdvisor(self.window, self.input, self.vision, self.config, self.stop_event)
            result = self._advisor.run_pass(mode, reserve_builders = getattr(self, '_reserve_builders', 1),
                                            order = getattr(self, '_upgrade_order', None))
            cb = getattr(self, '_status_callback', None)
            if cb and result is not None and result.pick is not None:
                cb(f'''Upgrades: {result.note}''')
            self._emit_state(note = result.note if result else None,
                             builders = result.scan.chip if result and result.scan else None)
            return result
        except InterruptedError:
            raise
        except Exception:
            logger.warning('Auto-upgrade pass failed; continuing farm loop', exc_info = True)
            return None

    def _emit_state(self, state = None, builders = None, lab = None, storages = None, note = None):
        '''Push a live-state update to the UI panel (best-effort, never raises).'''
        cb = getattr(self, '_state_callback', None)
        if not cb:
            return None
        try:
            cb({ 'state': state, 'builders': builders, 'lab': lab, 'storages': storages, 'note': note })
        except Exception:
            logger.debug('State callback failed', exc_info = True)

    def _read_state_stable(self, attempts = 3):
        def _capture():
            frame = self.window.screenshot()
            if frame is not None and frame.size:
                self._update_config_size(frame)
            return frame
        return read_village_state_stable(_capture, self.stop_event.wait, attempts)

    def _read_hud_triplet_stable(self):
        def _capture():
            frame = self.window.screenshot()
            if frame is not None and frame.size:
                self._update_config_size(frame)
            return frame
        return read_hud_triplet_stable(_capture, self.stop_event.wait)

    @staticmethod
    def _fmt_resource(value):
        value = int(value)
        if value >= 1000000:
            return f'''{value / 1000000:.1f}M'''
        if value >= 10000:
            return f'''{value / 1000:.0f}k'''
        return str(value)

    def _emit_village_state(self, state, mode_label):
        if state is None:
            return None
        # Storages field: real OCR'd amounts (from the last stable loot snapshot) plus
        # the game's bar-fill flags. The flat-swatch "full" templates fire from ~90%
        # up, so they are labeled "~full", never "full".
        flags = []
        if state.gold_full:
            flags.append('gold ~full')
        if state.elixir_full:
            flags.append('elixir ~full')
        triplet = getattr(self, '_last_hud_triplet', None)
        if triplet is not None:
            storages = f'''{self._fmt_resource(triplet[0])} / {self._fmt_resource(triplet[1])} / {self._fmt_resource(triplet[2])}'''
            if flags:
                storages += f''' ({', '.join(flags)})'''
        else:
            storages = ', '.join(flags) if flags else 'filling'
        self._emit_state(state = mode_label, builders = state.builders, lab = state.lab, storages = storages)

    def _maybe_idle(self, deadline):
        '''The "run until maxed" idle gate. When both main storages are full and a
        forced upgrade pass could not spend anything, attacking earns nothing — wait
        in place (game session kept alive via recovery on each wake) until a builder
        frees up or loot is spent, instead of stopping or attacking pointlessly.

        Dark elixir has no full-storage indicator; while gold/elixir still have room
        the normal farm loop is what fills DE. Pet House state is invisible on the
        home screen (no HUD chip, no builder-popup row — verified live), so pets are
        the user's manual job and never block idling; the status line calls out an
        idle LAB so research (also manual for now) is never silently forgotten.'''
        if getattr(self, '_auto_upgrade_mode', MODE_OFF) not in LIVE_UPGRADE_MODES:
            return None
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        state = read_village_state(frame)
        self._emit_village_state(state, 'farming')
        if state is None:
            return None
        reserve = getattr(self, '_reserve_builders', 1)
        free = state.free_builders
        # Spend eagerly: ANY full storage with a spare builder is money leaking (live
        # pain: Grand Warden started with elixir, then the free builder sat next to a
        # full gold storage for 10 minutes waiting on the interval pass).
        eager = free is not None and free > reserve and (state.gold_full or state.elixir_full)
        if not state.storages_full and not eager:
            return None
        if not state.storages_full:
            # Eager-only trigger: rate-limit so a full-gold stretch with nothing
            # startable does not burn a ~20s scan every battle cycle.
            now = time.monotonic()
            if now - getattr(self, '_eager_spend_last', 0) < 180:
                return None
            self._eager_spend_last = now
        logger.info('Idle gate: spend burst (%s) — forcing upgrade passes', state.summary())
        # Burn through candidates NOW instead of one per 5-minute wake: every failed
        # pick lands on cooldown so each retry reaches the next candidate, and every
        # SUCCESS frees loot but may leave another builder idle — keep going until
        # nothing is pickable or the attempts are spent.
        for _attempt in range(5):
            result = self._maybe_auto_upgrade(force = True)
            if result is None:
                break  # scan preconditions failed
            if result.pick is None and not result.collecting:
                break  # genuinely nothing pickable remains (a collect pass is not a verdict)
        state = self._read_state_stable()
        if state is None or not state.storages_full:
            return None
        if not (getattr(self, '_gold_pinned', False) and getattr(self, '_elixir_pinned', False)):
            # Icons say ~full but the values are still moving — real headroom remains
            # (live: idled at 18M/21M gold, wasting ~3M of farmable gold). Keep
            # farming until both numbers pin at their caps.
            logger.info('Idle gate: storages ~full but still filling (gold pinned=%s, elixir pinned=%s) — farming on', getattr(self, '_gold_pinned', False), getattr(self, '_elixir_pinned', False))
            return None
        reserve = getattr(self, '_reserve_builders', 1)
        cb = getattr(self, '_status_callback', None)
        logger.info('Idle gate: nothing startable with storages full (%s) — pausing attacks, rechecking every %ds', state.summary(), _IDLE_RECHECK_SECONDS)
        while True:
            self._check_stop()
            if deadline and time.time() >= deadline:
                return None
            msg = f'''Idling — {state.summary() if state else 'state unreadable'}; recheck in {_IDLE_RECHECK_SECONDS // 60}m'''
            if state is not None and state.lab_idle:
                msg += ' — LAB IS IDLE: start a research!'
            if cb:
                cb(msg)
            self._emit_village_state(state, 'idling')
            if self.stop_event.wait(_IDLE_RECHECK_SECONDS):
                return None
            # The game disconnects after a few idle minutes — recovery clicks Reload
            # (after its own grace period) and walks back to the home screen.
            self._home_screen_recovery()
            state = self._read_state_stable()
            if state is None:
                continue
            if not state.storages_full:
                if state.builders is None:
                    # Unreadable builder chip = probably not a clean home frame (mid-
                    # recovery, reload dialog) — the missing full-icons prove nothing.
                    # Stay idle; the next wake re-reads (live repro: one wake exited on
                    # "builders ? free, storages filling" right after a disconnect).
                    logger.info('Idle: degraded read (%s) — staying idle', state.summary())
                    continue
                logger.info('Idle over: storages have room again (%s)', state.summary())
                break
            free = state.free_builders
            if free is not None and free > reserve:
                logger.info('Idle over: %d builder(s) free (%s)', free, state.summary())
                break
        self._auto_upgrade_last_scan = 0  # resume with an immediate scan so the freed builder is used
        if cb:
            cb('Resuming — ' + state.summary())
        self._emit_village_state(state, 'farming')


    def _upgrade_walls_pick_resource_and_okay(self):
        '''Fresh frame → click an affordable resource slot → Okay. If neither resource can pay, close the popup instead (never confirm a red cost).'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
        for _ in range(2):
            if pair.gold.cost_roi_xywh or pair.elixir.cost_roi_xywh:
                break
            # The popup re-renders for a beat after the last add click and the cost buttons
            # can miss the template match — settle and re-read before giving up.
            if self.stop_event.wait(0.4):
                return None
            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)
            pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
        picked = False
        # cost_roi_xywh None means the cost text could not be measured — never click a slot
        # on a blind reading (an unaffordable click opens the buy-with-gems dialog).
        # Elixir first: attacking costs GOLD (Find a Match entry fee), so spend elixir on
        # walls whenever it can pay and keep gold for matchmaking.
        if pair.elixir.redness < 0.2 and pair.elixir.cost_roi_xywh and pair.elixir.center:
            logger.info('Wall upgrade: paying with elixir (redness %.2f)', pair.elixir.redness)
            self.input.click(pause = 0.3, *pair.elixir.center)
            picked = True
        elif pair.gold.redness < 0.2 and pair.gold.cost_roi_xywh and pair.gold.center:
            logger.info('Wall upgrade: paying with gold (redness %.2f)', pair.gold.redness)
            self.input.click(pause = 0.3, *pair.gold.center)
            picked = True
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        if not picked:
            logger.info('Wall upgrade: no affordable resource slot (gold %.2f, elixir %.2f) — dismissing without confirming', pair.gold.redness, pair.elixir.redness)
            if not pair.gold.cost_roi_xywh and not pair.elixir.cost_roi_xywh:
                try:
                    import time as _time
                    import cv2 as _cv2
                    from app.utils.common import get_user_app_data_dir
                    dbg = get_user_app_data_dir() / 'debug'
                    dbg.mkdir(parents = True, exist_ok = True)
                    path = dbg / f'''wallfail_{int(_time.time())}.jpg'''
                    _cv2.imwrite(str(path), frame, [_cv2.IMWRITE_JPEG_QUALITY, 88])
                    logger.info('Wall upgrade: confirm-time frame saved to %s', path)
                except Exception:
                    logger.debug('Wall upgrade: debug frame dump failed', exc_info = True)
            self._deselect_wall_ui()
            return None
        (ox, oy) = self.vision.find_template(frame, 'okay.png')
        if ox:
            self.input.click(ox, oy, pause = 0.3)
            logger.info('Wall upgrade batch confirmed')
            if self.stop_event.wait(0.35):
                return None
            self._dismiss_gem_prompt_if_open()

    
    def _upgrade_walls(self):
        '''Upgrade walls: handles already-selected walls, builder suggested upgrades, row upgrades, and single-wall upgrades.'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)

        # 1. Zero-Gem check
        if self._dismiss_gem_prompt_if_open(frame):
            return None

        # 2. Check if a wall is ALREADY selected on the village map right now
        actions = VisionService.find_wall_upgrade_actions(frame)
        if actions.is_selected and (actions.elixir_upgrade or actions.gold_upgrade or actions.upgrade_more or actions.select_row):
            logger.info('Wall upgrade: wall is already selected on the village screen')
            return self._execute_wall_upgrade_actions(actions)

        # 3. Not selected: ensure we are on the home screen
        home_roi = VisionService.bottom_half_region(frame)
        (hax, hay) = self.vision.find_template(frame, 'attack.png', region = home_roi)
        if not hax:
            logger.info('Wall upgrade: not on the home screen (Attack button missing) — skipping this pass')
            return None

        # 4. Open builder menu
        top_roi = VisionService.top_half_region(frame)
        (bx, by) = self._find_home_village_builder(frame, top_roi)
        if not bx:
            logger.info('Wall upgrade: builder portrait not found — skipping this pass')
            return None
        self.input.click(bx, by, pause = 0.5)

        # 5. Builder popup open: wait for render
        if self.stop_event.wait(0.35):
            return None

        # 6. Search for Wall row with gentle touch-drag scrolling if needed
        wall_pt = None
        scrolls = 0
        for _ in range(_WALL_MENU_SCROLL_STEPS * 2):
            self._check_stop()
            found = self._find_wall_row_once()
            if found:
                wall_pt = found
                if scrolls:
                    logger.info('Wall upgrade: Wall row found after %d scroll nudge(s)', scrolls)
                break
            scrolls += 1
            if scrolls >= _WALL_MENU_SCROLL_STEPS:
                break
            self.input.scroll(*self._wall_menu_scroll_point(), _WALL_MENU_WHEEL_CLICKS)
            self._wall_menu_nudge_drag()
            if self.stop_event.wait(0.4):
                return None

        if not wall_pt:
            logger.info('Wall upgrade: Wall label OCR missed at all scroll positions — skipping this pass')
            self._deselect_wall_ui()
            return None

        # Click the Wall row in the builder popup
        self.input.click(pause = 0.6, *wall_pt)

        # 7. Camera pans to the wall — poll for the wall action buttons to appear (up to 8 polls)
        actions = None
        for _ in range(8):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)
            if self._dismiss_gem_prompt_if_open(frame):
                return None
            actions = VisionService.find_wall_upgrade_actions(frame)
            if actions.is_selected and (actions.elixir_upgrade or actions.gold_upgrade or actions.upgrade_more or actions.select_row):
                break
            # Legacy template fallback
            bot_roi = VisionService.bottom_half_region(frame)
            (umx, umy) = self.vision.find_template(frame, 'upgrademore.png', region = bot_roi)
            if umx:
                from app.services.vision import WallUpgradeActionInfo
                actions = WallUpgradeActionInfo(is_selected = True, upgrade_more = (umx, umy))
                break
            if self.stop_event.wait(0.4):
                return None

        if not actions or not actions.is_selected:
            logger.info('Wall upgrade: no wall upgrade buttons visible after Wall row click — dismissing')
            self._dismiss_okay_or_exit_on_frame(frame)
            return None

        return self._execute_wall_upgrade_actions(actions)

    def _execute_wall_upgrade_actions(self, actions):
        '''Execute wall upgrade with excess resources: prefer Elixir over Gold, support rows and single walls.'''
        frame = self.window.screenshot()
        if self._dismiss_gem_prompt_if_open(frame):
            return None

        upgraded = False

        # Attempt 1: If Upgrade More or Select Row is available, try batch upgrade
        if actions.upgrade_more or actions.select_row:
            target = actions.upgrade_more if actions.upgrade_more else actions.select_row
            logger.info('Wall upgrade: clicking %s at %s', 'Upgrade More' if actions.upgrade_more else 'Select Row', target)
            self.input.click(pause = 0.4, *target)
            if self.stop_event.wait(0.35):
                return None

            frame = self.window.screenshot()
            if frame is not None:
                self._update_config_size(frame)
                if self._dismiss_gem_prompt_if_open(frame):
                    return None

                # Check if the multi-upgrade batch dialog opened (with addwall/removewall and gold/elixir cost buttons)
                pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
                if pair.gold.cost_roi_xywh or pair.elixir.cost_roi_xywh:
                    added = 0
                    for _ in range(_WALL_BATCH_MAX_ADDS):
                        self._check_stop()
                        frame = self.window.screenshot()
                        if frame is None:
                            break
                        self._update_config_size(frame)
                        pair = VisionService.upgrade_cost_redness_by_resource_icons(frame)
                        if pair.gold.redness >= 0.2 and pair.elixir.redness >= 0.2:
                            break
                        (fh, fw) = frame.shape[:2]
                        mid_roi = (fw // 4, fh // 2, fw // 2, fh - fh // 2)
                        (awx, awy) = VisionService.find_active_addwall(frame, region = mid_roi)
                        if not awx:
                            break
                        self.input.click(awx, awy, pause = 0.25)
                        added += 1

                    (fh, fw) = frame.shape[:2]
                    mid_roi = (fw // 4, fh // 2, fw // 2, fh - fh // 2)
                    if added and pair.gold.redness >= 0.2 and pair.elixir.redness >= 0.2:
                        (rwx, rwy) = VisionService.find_active_removewall(frame, region = mid_roi)
                        if rwx:
                            self.input.click(rwx, rwy, pause = 0.3)
                    elif added > 1 and pair.elixir.redness >= 0.2 and pair.gold.redness < 0.2 and pair.gold.cost_roi_xywh:
                        (rwx, rwy) = VisionService.find_active_removewall(frame, region = mid_roi)
                        if rwx:
                            self.input.click(rwx, rwy, pause = 0.3)

                    logger.info('Wall upgrade: %d wall(s) added to batch', added)
                    self._upgrade_walls_pick_resource_and_okay()
                    upgraded = True
                else:
                    # Row selection expanded: re-read actions for row upgrade buttons
                    row_actions = VisionService.find_wall_upgrade_actions(frame)
                    if row_actions.elixir_upgrade and row_actions.elixir_affordable:
                        logger.info('Wall upgrade: paying row with elixir at %s', row_actions.elixir_upgrade)
                        self.input.click(pause = 0.4, *row_actions.elixir_upgrade)
                        upgraded = True
                    elif row_actions.gold_upgrade and row_actions.gold_affordable:
                        logger.info('Wall upgrade: paying row with gold at %s', row_actions.gold_upgrade)
                        self.input.click(pause = 0.4, *row_actions.gold_upgrade)
                        upgraded = True

                    if upgraded:
                        if self.stop_event.wait(0.35):
                            return None
                        frame = self.window.screenshot()
                        if frame is not None:
                            (ox, oy) = self.vision.find_template(frame, 'okay.png')
                            if ox:
                                self.input.click(ox, oy, pause = 0.3)
                            self._dismiss_gem_prompt_if_open(frame)

        # Attempt 2: If batch upgrade wasn't done, do single-wall upgrade
        if not upgraded:
            frame = self.window.screenshot()
            if frame is not None:
                self._update_config_size(frame)
                cur_actions = VisionService.find_wall_upgrade_actions(frame)
                # Prefer Elixir so Gold is saved for matchmaking entry fee
                if cur_actions.elixir_upgrade and cur_actions.elixir_affordable:
                    logger.info('Wall upgrade: single wall with elixir at %s', cur_actions.elixir_upgrade)
                    self.input.click(pause = 0.4, *cur_actions.elixir_upgrade)
                    upgraded = True
                elif cur_actions.gold_upgrade and cur_actions.gold_affordable:
                    logger.info('Wall upgrade: single wall with gold at %s', cur_actions.gold_upgrade)
                    self.input.click(pause = 0.4, *cur_actions.gold_upgrade)
                    upgraded = True
                else:
                    logger.info('Wall upgrade: neither elixir nor gold is affordable')

                if upgraded:
                    if self.stop_event.wait(0.35):
                        return None
                    frame = self.window.screenshot()
                    if frame is not None:
                        (ox, oy) = self.vision.find_template(frame, 'okay.png')
                        if ox:
                            self.input.click(ox, oy, pause = 0.3)
                        self._dismiss_gem_prompt_if_open(frame)

        # Clean deselect so the home screen is ready for attack
        self._deselect_wall_ui()
        logger.info('Wall upgrade pass completed (upgraded=%s)', upgraded)
        return upgraded

    
    def _dismiss_gem_prompt_if_open(self, frame = None):
        '''Strict Zero-Gem Policy: Detect and abort any dialog attempting to charge gems.'''
        if frame is None:
            frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        prompt = VisionService.detect_gem_spending_dialog(frame)
        if prompt and prompt.detected:
            logger.warning('SECURITY ALERT: Gem spending dialog detected (%s) — strictly vetoed by Zero-Gem Policy!', prompt.reason)
            cb = getattr(self, '_status_callback', None)
            if cb:
                cb('Gem prompt blocked (Zero-Gem Guard)')
            if prompt.cancel_point:
                self.input.click(pause = 0.3, *prompt.cancel_point)
            self.input.send_escape()
            self.input.click(pause = 0.3, *self.config.get_point('empty'))
            return True
        return False

    def _dismiss_okay_or_exit_on_frame(self, frame):
        '''If a gem dialog is open, veto/dismiss it immediately. If okay.png, exit.png, or known dialog-specific
        controls are visible, click them. If a Supercell update/event uncancelable progression button
        is visible, click it safely.'''
        # 1. Zero-Gem Guard check
        if self._dismiss_gem_prompt_if_open(frame):
            return True

        # 2. Template dismissal checks
        names = ['okay.png', 'exit.png']
        for extra in ('claim_btn.png', 'chestcontinue.png', 'chestclaim.png', 'dailyreward_x.png', 'needgold_x.png'):
            if get_template_path(extra).exists():
                names.append(extra)
        for name in names:
            (x, y) = self.vision.find_template(frame, name)
            if not x:
                continue
            self.input.click(x, y, pause = 0.15)
            return True

        # 3. Supercell uncancelable progression dialogs (Update announcements, Season rewards)
        prog_pt = VisionService.find_uncancelable_progression_button(frame)
        if prog_pt:
            logger.info('Dismissing Supercell update/event modal via progression button at %s', prog_pt)
            self.input.click(prog_pt[0], prog_pt[1], pause = 0.25)
            return True

        return False

    
    def _wait_for_attack_with_nudge(self, timeout = 10, error = True):
        '''Poll bottom-half ``attack.png``; dismiss ``okay`` / ``exit`` popups first; else empty + scroll.'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.25):
                    return (None, None)
                continue
            (sx, sy) = self.vision.find_template(frame, 'surrender.png')
            if sx:
                logger.warning('Attack wait: live battle detected (surrender visible) — leaving it to recovery')
                return (None, None)
            search_region = self._search_region_for_template(frame, 'attack.png', None, None, 200)
            (ax, ay) = self.vision.find_template(frame, 'attack.png', region = search_region)
            if ax:
                return (ax, ay)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.35):
                return (None, None)
        # Timeout reached: run one recovery pass to clear any human interference/overlays and check once more
        self._home_screen_recovery()
        frame = self.window.screenshot()
        if frame is not None:
            self._update_config_size(frame)
            search_region = self._search_region_for_template(frame, 'attack.png', None, None, 200)
            (ax, ay) = self.vision.find_template(frame, 'attack.png', region = search_region)
            if ax:
                return (ax, ay)
        if error:
            logger.warning('Timeout waiting for attack.png')
        return (None, None)

    
    def _run_loop(self, method_id, duration_seconds, star_bonus = False, ranked_fill = False, upgrade_walls = False):
        start_time = time.time()
        if self.stop_event.wait(1):
            return None
        frame = self.window.screenshot()
        self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        delay = random.uniform(0.1, 0.3)
        if self.stop_event.wait(delay):
            return None
        if star_bonus and self._is_star_bonus_claimed():
            logger.info('Star bonus mode: no star bonus template matched on home — nothing to collect. Finishing without attacks.')
            return None
        # duration_seconds == 0 → unlimited ("run until maxed"): only the user's Stop
        # ends the session; full storages park the loop in _maybe_idle instead.
        deadline = start_time + duration_seconds if duration_seconds else None
        # Capture initial pre-attack baseline resources
        self._loot_snapshot_before_attack()
        self._maybe_upgrade_walls(upgrade_walls)
        self._maybe_auto_upgrade()
        self._maybe_idle(deadline)
        cb = getattr(self, '_status_callback', None)
        troop_failures = 0
        while deadline is None or time.time() < deadline:
            self._check_stop()
            if self.antiban.execute_break_if_due(self.stop_event, status_callback = self._status_callback):
                notify_break(self.antiban.config.min_break_mins)
            self._check_stop()
            outcome = self._find_match_and_attack(method_id, ranked_fill)
            self._return_home()
            self._home_screen_recovery()
            if outcome != 'ranked_limit':
                # Allow HUD count-up filling animation to complete before reading raid gains
                self.stop_event.wait(1.5)
                self._record_completed_raid_and_update_loot()
            if outcome == 'ranked_limit':
                return None
            if outcome == 'troop':
                troop_failures += 1
                if troop_failures >= _TROOP_FAILURE_LIMIT:
                    if deadline is None:
                        # Run-until-maxed must never stop on its own: long back-off
                        # instead (a stuck popup / event screen usually clears, and
                        # recovery runs again on the next attempt).
                        msg = f'''Troops not found {troop_failures} times in a row — backing off {_IDLE_RECHECK_SECONDS // 60}m, then retrying (run until maxed).'''
                        logger.warning(msg)
                        if cb:
                            cb(msg)
                        troop_failures = 0
                        if self.stop_event.wait(_IDLE_RECHECK_SECONDS):
                            return None
                        self._home_screen_recovery()
                        continue
                    msg = f'''Troops not found {troop_failures} times in a row — stopping. Check the army / saved recipe.'''
                    logger.warning(msg)
                    if cb:
                        cb(msg)
                    return None
                msg = f'''Troops not found ({troop_failures}/{_TROOP_FAILURE_LIMIT}) — retrying in {_TROOP_RETRY_WAIT_SECONDS}s.'''
                logger.warning(msg)
                if cb:
                    cb(msg)
                # Tap any collect bubbles while we are home — if the failure was really the
                # need-more-gold dialog (entry fee unaffordable), mine gold un-wedges it.
                self._multi_run_collect_home_village_resources()
                if self.stop_event.wait(_TROOP_RETRY_WAIT_SECONDS):
                    return None
            else:
                troop_failures = 0
            self._maybe_upgrade_walls(upgrade_walls)
            self._maybe_auto_upgrade()
            self._maybe_idle(deadline)
            self.input.scroll(*self._scroll_point(), 5)
            if self.stop_event.wait(random.uniform(0.15, 0.25)):
                return None
            if star_bonus and self._is_star_bonus_claimed():
                logger.info('Star bonus claimed (star icons no longer visible). Stopping.')
                self._loot_snapshot_before_attack()
                return None
        self._loot_snapshot_before_attack()
        return None

    
    def _run_builder_base_loop(self, duration_seconds, star_bonus = False, method = 1):
        '''Builder Base farming: Attack → Find Now → Baby Dragon deploy → end battle or surrender → Return Home.'''
        start_time = time.time()
        cb = getattr(self, '_status_callback', None)
        if self.stop_event.wait(1):
            return None
        frame = self.window.screenshot()
        if not frame is None:
            self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        if self.stop_event.wait(random.uniform(0.1, 0.3)):
            return None
        if star_bonus and self._is_bb_star_bonus_finished():
            msg = 'Builder Base star bonus: bstar.png not visible — nothing to collect. Finishing without attacks.'
            logger.info(msg)
            if cb:
                cb(msg)
            return None
        while time.time() - start_time < duration_seconds:
            self._check_stop()
            self.input.scroll(*self._scroll_point(), 20)
            if self.stop_event.wait(random.uniform(0.1, 0.25)):
                return None
            (ax, ay) = self._wait_for_image('attack.png', timeout = 10)
            if not ax:
                logger.warning('Builder Base: attack.png not found')
                continue
            self.input.click(ax, ay, pause = 0.15)
            (fx, fy) = self._wait_for_image('findnow.png', timeout = 10)
            if not fx:
                logger.warning('Builder Base: findnow.png not found')
                continue
            self.input.click(fx, fy, pause = 0.15)
            (bx, by) = self._wait_for_image('babydragon.png', timeout = 30, error = False)
            if not bx:
                msg = 'Builder Base: babydragon.png not found after Find Now'
                logger.warning(msg)
                if cb:
                    cb(msg)
                continue
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            (h, w) = frame.shape[:2]
            cy = h // 2
            cx = w // 2
            self.input.move(cx, cy)
            if self.stop_event.wait(0.05):
                return None
            self.input.scroll(cx, cy, 4)
            if self.stop_event.wait(0.15):
                return None
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            deployed = (
                self._deploy_bb_night_witches(frame)
                if method == 2
                else self._deploy_bb_baby_dragons(frame)
            )
            if not deployed:
                logger.warning('Builder Base: deploy failed')
                continue
            if self._loot_prioritise == 'elixir':
                self._bb_surrender_and_return_home()
            elif self._loot_prioritise == 'gold':
                self._bb_gold_prioritise_end_battle_and_return_home()
            else:
                self._bb_end_battle_and_return_home()
            self._bb_collect_elixir_cart_after_attack()
            if star_bonus and self._is_bb_star_bonus_finished():
                logger.info('Builder Base star bonus finished (bstar.png no longer visible). Stopping.')
                return None
            if self.stop_event.wait(random.uniform(0.35, 0.6)):
                return None
        return None

    
    def _bb_pan_down_left_from_center(self):
        '''Pan BB view down-left from screen center (~500px) to reveal the boat / elixir cart.'''
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self._update_config_size(frame)
        (h, w) = frame.shape[:2]
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
        self.input.human_move(cx, cy, x2, y2, duration = random.uniform(0.35, 0.55))
        self.input.mouse_up(x2, y2)
        if self.stop_event.wait(0.45):
            self._check_stop()
            return None

    
    def _find_bb_full_elixir_cart(self, attempts = 3):
        '''Up to ``attempts`` screenshots; try fullecart templates in order (top-right quadrant).'''
        empty_pt = self.config.get_point('empty')
        for _ in range(attempts):
            self._check_stop()
            frame = self.window.screenshot()
            if not frame is None:  # [recovered: decompiler turned this `if` into a `while` and made the return unconditional]
                self._update_config_size(frame)
                roi = VisionService.top_right_quadrant_region(frame)
                for template in _BB_FULL_ELIXIR_CART_TEMPLATES:
                    (x, y) = self.vision.find_template(frame, template, threshold = 0.8, region = roi)
                    if x:
                        return (x, y)
            self.input.click(pause = 0.15, *empty_pt)
        return (None, None)

    
    def _bb_collect_elixir_cart_after_attack(self):
        '''After a BB raid: dismiss popups, pan to cart, collect full elixir cart if visible.'''
        if self.stop_event.wait(0.35):
            return None
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        if self.stop_event.wait(0.15):
            return None
        self._bb_pan_down_left_from_center()
        (cx, cy) = self._find_bb_full_elixir_cart(attempts = 3)
        if cx:
            self.input.click(cx, cy, pause = 0.2)
            (coll_x, coll_y) = self._wait_for_image(_BB_COLLECT_TEMPLATE, timeout = 8, error = False)
            if coll_x:
                self.input.click(coll_x, coll_y, pause = 0.2)
            else:
                logger.warning('Builder Base: collect.png not found after elixir cart')
        else:
            logger.debug('Builder Base: fullecart not visible — skipping cart collect')
        self.input.click(pause = 0.15, *self.config.get_point('empty'))

    
    def _deploy_bb_baby_dragons(self, frame):
        '''Find all Baby Dragon icons, deploy on diamond edges, wait, then re-click saved icons.'''
        strategy = AttackStrategy(self.input, self.vision, self.config, self.stop_event)
        roi = VisionService.bottom_half_region(frame)
        centers = VisionService.find_all_template_centers(frame, 'babydragon.png', region = roi, max_matches = 12, suppress_pad_frac = _BB_TEMPLATE_SUPPRESS_PAD)
        if not centers:
            return False
        deploy_count = len(centers)
        self.input.click(centers[0][0], centers[0][1], pause = 0.3, rand = False)
        if self.stop_event.wait(0.2):
            return True
        for px, py in strategy._even_diamond_top_perimeter_points(frame, deploy_count, reserve_top_corner_slot = True):
            self._check_stop()
            self.input.click(px, py, pause = _EDRAG_DELAY, rand = False)
        self._deploy_bb_battle_or_flying_machine(strategy)
        if self._loot_prioritise != 'elixir':
            if self.stop_event.wait(_BB_BABY_DRAGON_RECLICK_WAIT):
                return True
            for x, y in centers:
                self._check_stop()
                self.input.click(x, y, pause = 0.15, rand = False)
        return True

    
    def _deploy_bb_battle_or_flying_machine(self, strategy):
        '''One bar lookup: Battle Machine, else Flying Machine; deploy on a random diamond edge.'''
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        roi = VisionService.bottom_half_region(frame)
        (tx, ty) = self.vision.find_template(frame, _BB_BATTLE_MACHINE_TEMPLATE, region = roi)
        if not tx:
            (tx, ty) = self.vision.find_template(frame, _BB_FLYING_MACHINE_TEMPLATE, region = roi)
        if not tx:
            logger.debug('Builder Base: %s / %s not found on troop bar', _BB_BATTLE_MACHINE_TEMPLATE, _BB_FLYING_MACHINE_TEMPLATE)
            return None
        (px, py) = strategy._random_diamond_perimeter_point(frame)
        self.input.click(tx, ty, pause = 0.3, rand = False)
        if self.stop_event.wait(0.2):
            return None
        self.input.click(px, py, pause = _EDRAG_DELAY, rand = False)

    
    def _bb_end_battle_and_return_home(self):
        '''Wait for natural battle end, dismiss Okay, then tap BB Return Home.'''
        (ex, ey) = self._wait_for_image('endbattle.png', timeout = 90, error = False)
        if ex:
            self.input.click(ex, ey, pause = 0.15)
        else:
            logger.warning('Builder Base: endbattle.png not found')
            return None
        self._bb_dismiss_okay_and_return_home()

    
    def _bb_gold_prioritise_end_battle_and_return_home(self):
        '''Gold prioritise: wait for 2+ battle stars, then End Battle → Okay → Return Home.'''
        start = time.time()
        timeout = 90
        end_battle_clicked = False
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return None
                continue
            self._update_config_size(frame)
            bot_roi = VisionService.bottom_half_region(frame)
            stars = VisionService.find_all_template_centers(frame, _BB_BATTLE_STAR_TEMPLATE, threshold = 0.8, region = bot_roi, max_matches = 3, suppress_pad_frac = 0.35)
            if len(stars) >= _BB_GOLD_PRIORITISE_MIN_STARS:
                bot_roi = VisionService.bottom_half_region(frame)
                (ex, ey) = self.vision.find_template(frame, 'endbattle.png', region = bot_roi)
                if ex:
                    logger.info('Builder Base (gold): %d bbstar.png — clicking endbattle', len(stars))
                    self.input.click(ex, ey, pause = 0.15)
                    end_battle_clicked = True
                    break  # [recovered: decompiler dropped this break and misnested the timeout warning inside the loop]
            if self.stop_event.wait(0.5):
                return None
        if not end_battle_clicked:
            logger.warning('Builder Base (gold): timed out waiting for %d+ %s', _BB_GOLD_PRIORITISE_MIN_STARS, _BB_BATTLE_STAR_TEMPLATE)
            return None
        self._bb_dismiss_okay_and_return_home()

    
    def _bb_return_home_template_for_screen(self, width, height):
        '''Return (template name, scale_template) for Builder Base Return Home.'''
        (tw, th) = _BB_1080P_CAPTURE_SIZE
        tol = _BB_1080P_SIZE_TOLERANCE
        if abs(width - tw) <= tol and abs(height - th) <= tol:
            return (_BB_RETURN_HOME_TEMPLATE_1080P, False)
        return (_BB_RETURN_HOME_TEMPLATE, True)

    
    def _wait_for_bb_return_home(self, timeout = 15):
        '''Wait for BB Return Home; picks 1080p-native template when capture is ~1920x1080.'''
        start = time.time()
        template_name = _BB_RETURN_HOME_TEMPLATE
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            (h, w) = frame.shape[:2]
            (template_name, scale_template) = self._bb_return_home_template_for_screen(w, h)
            search_region = self._search_region_for_template(frame, template_name, None, None, 200)
            (x, y) = self.vision.find_template(frame, template_name, threshold = 0.8, region = search_region, scale_template = scale_template)
            if x:
                return (x, y, template_name)
            if self.stop_event.wait(0.5):
                return (None, None, template_name)
        return (None, None, template_name)

    
    def _bb_dismiss_okay_and_return_home(self, *, retry_battle_template = 'endbattle.png', max_retries = _BB_RETURN_HOME_END_BATTLE_RETRIES):
        '''Dismiss Okay, tap Return Home; retry battle-end + Okay if Return Home stays hidden.'''
        return_home_template = _BB_RETURN_HOME_TEMPLATE
        for attempt in range(max_retries + 1):
            self._check_stop()
            if attempt > 0:
                (bx, by) = self._wait_for_image(retry_battle_template, timeout = 3, error = False)
                if bx:
                    self.input.click(bx, by, pause = 0.15)
                else:
                    logger.debug('Builder Base: %s retry %d/%d — control not visible', retry_battle_template, attempt, max_retries)
            okay_timeout = 10 if attempt == 0 else 5
            (ox, oy) = self._wait_for_image('okay.png', timeout = okay_timeout, error = False)
            if ox:
                self.input.click(ox, oy, pause = 0.15)
            (rx, ry, return_home_template) = self._wait_for_bb_return_home(timeout = 15)
            if rx:
                self.input.click(rx, ry, pause = 0.2)
                if attempt > 0:
                    logger.info('Builder Base: return home after %d %s retry(ies)', attempt, retry_battle_template)
                return None
            if not attempt < max_retries:
                continue
            logger.info('Builder Base: %s not found — retrying %s + okay (%d/%d)', return_home_template, retry_battle_template, attempt + 1, max_retries)
        logger.warning('Builder Base: %s not found after %d %s retries', return_home_template, max_retries, retry_battle_template)

    
    def _bb_surrender_and_return_home(self):
        '''Elixir prioritise: surrender right after deploy, then Okay + Return Home.'''
        (sx, sy) = self._wait_for_image('surrender.png', timeout = 10, error = False)
        if sx:
            self.input.click(sx, sy, pause = 0.15)
        else:
            logger.warning('Builder Base (elixir): surrender.png not found')
            return None
        self._bb_dismiss_okay_and_return_home(retry_battle_template = 'surrender.png')

    
    def _find_next_button(self, frame: np.ndarray) -> Tuple[int, int]:
        """Locates the 'Next' match button on the multiplayer scout screen."""
        h, w = frame.shape[:2]
        default_x = int(round(w * 0.91))
        default_y = int(round(h * 0.88))

        next_roi = (
            int(round(w * 0.80)),
            int(round(h * 0.74)),
            int(round(w * 0.20)),
            int(round(h * 0.26)),
        )
        try:
            (nx, ny) = self.vision.find_word_on_screen(
                frame,
                "Next",
                region=next_roi,
                case_sensitive=False,
                fuzzy_min_ratio=0.75,
                white_text=True,
            )
            if nx is not None and ny is not None:
                return (nx, ny)
        except Exception:
            pass

        return (default_x, default_y)

    def _find_match_and_attack(self, method_id, ranked_fill = False):
        """One attack cycle. Returns ``'ranked_limit'`` (stop now), ``'troop'`` (troops missing — retry later), or None."""
        battle_template = 'rankedbattle.png' if ranked_fill else 'farmbattle.png'
        (fx, fy) = self._find_template_once(battle_template)
        if fx:
            # A previous cycle left the battle-selection screen open (stolen tap / derail) —
            # use it directly instead of hunting for the home Attack button it covers.
            logger.info('Attack: battle-selection screen already open — continuing from Find a Match')
        else:
            (ax, ay) = self._wait_for_attack_with_nudge()
            if not ax:
                return None
            # Baseline is established before first attack; post-raid gains are captured upon returning home
            if self._loot_prev_resources is None:
                self._loot_snapshot_before_attack()
            self.input.click(ax, ay, pause = 0.1)
            (fx, fy) = self._wait_for_image(battle_template)
        if not fx:
            if ranked_fill:
                msg = 'Ranked battle button not found — daily limit may be reached. Stopping.'
                logger.info(msg)
                cb = getattr(self, '_status_callback', None)
                if cb:
                    cb(msg)
                return 'ranked_limit'
            return None
        self.input.click(fx, fy, pause = 0.1)
        # A single tap here is unreliable: event popups (Card Hunt etc.) or a still-animating
        # screen can eat it. Verify the army screen (attack2) actually appeared; while the
        # Find a Match button is still on screen, the tap was stolen — tap again (the first
        # stolen tap also closes whatever popup ate it).
        (a2x, a2y) = self._wait_for_image('attack2.png', timeout = 5, error = False)
        for _ in range(3):
            if a2x:
                break
            (rfx, rfy) = self._find_template_once(battle_template)
            if not rfx:
                break
            logger.info('%s still on screen — click was eaten (popup?); re-clicking', battle_template)
            self.input.click(rfx, rfy, pause = 0.1)
            (a2x, a2y) = self._wait_for_image('attack2.png', timeout = 5, error = False)
        if not a2x:
            (a2x, a2y) = self._wait_for_image('attack2.png')
        if method_id == 3 and not self._ensure_valkyrie_army_from_recipes():
            # Attack anyway with whatever is trained — a partial Valkyrie army still loots, and
            # bailing out here would leave the Find a Match screen open with nothing to recover it.
            msg = 'Valkyrie army not confirmed (slow screen or missing saved recipe) — attacking with current army'
            logger.warning(msg)
            cb = getattr(self, '_status_callback', None)
            if cb:
                cb(msg)
        if a2x:
            self.input.click(a2x, a2y, pause = 0.1)
            if ranked_fill:
                (rx, ry) = self._wait_for_image('rankedattackconfirm.png', timeout = 10)
                if not rx:
                    logger.warning('rankedattackconfirm.png not found after attack2.png')
                else:
                    self.input.click(rx, ry, pause = 0.1)
        # Match scouting and loot filtration
        skip_count = 0
        self.loot_filter.reload_config()
        filter_active = self.loot_filter.config.enabled and not ranked_fill
        max_skips = self.loot_filter.config.max_skips if filter_active else 0
        cb = getattr(self, '_status_callback', None)

        while True:
            self._check_stop()
            matched = self._wait_for_any_image(('surrender.png', 'endbattle.png'), timeout = 35)
            if not matched:
                logger.warning('Scouting timeout: neither surrender.png nor endbattle.png appeared.')
                return None

            # Settle wait for clouds to disperse and loot HUD to paint
            if self.stop_event.wait(0.5):
                return None

            frame = self.window.screenshot()
            if frame is None:
                return None
            self._update_config_size(frame)

            # Extract available enemy loot
            (gold, elixir, dark_elixir) = self.vision.extract_enemy_loot(frame)
            self._last_accepted_target_loot = (gold or 0, elixir or 0, dark_elixir or 0)
            logger.info(
                'Scouted Base #%d: Gold=%s, Elixir=%s, DarkElixir=%s',
                skip_count + 1,
                f'{gold:,}' if gold is not None else '?',
                f'{elixir:,}' if elixir is not None else '?',
                f'{dark_elixir:,}' if dark_elixir is not None else '?',
            )

            # In ranked fill or when loot filter is disabled, accept the first base immediately
            if not filter_active:
                if cb:
                    cb('Target accepted (filter inactive/ranked) — Attacking!')
                break

            decision = self.loot_filter.evaluate(gold, elixir, dark_elixir, current_skip_count = skip_count)
            if decision.should_attack:
                logger.info('Loot Filter ACCEPTED base: %s (after %d skips). Commencing attack!', decision.reason, skip_count)
                if cb:
                    cb(f'Target accepted ({decision.reason}) — Attacking!')
                break

            # Filter rejected base — click Next
            logger.info('Loot Filter REJECTED base: %s. Skipping to next base...', decision.reason)
            self.loot_filter.stats.record_skip()
            skip_count += 1
            if cb:
                cb(f'Skipping base ({decision.reason}) [{skip_count}/{max_skips}]')

            (nx, ny) = self._find_next_button(frame)
            self.input.click(nx, ny, pause = 0.2)

            # Wait briefly for cloud transition out before next detection loop
            if self.stop_event.wait(0.75):
                return None

        self._last_raid_skips = skip_count
        (h, w) = frame.shape[:2]
        cy = h // 2
        cx = w // 2
        self.input.move(cx, cy)
        if self.stop_event.wait(0.05):
            return None
        self.input.scroll(cx, cy, 3)
        frame = self.window.screenshot()
        if frame is None:
            return None
        self._update_config_size(frame)
        strategy = self._get_strategy(method_id)
        result = strategy.execute(frame, self.stop_event)
        self._wait_for_battle_end(is_sneaky = method_id == 1)
        self._raid_just_completed = True
        return 'troop' if result is False else None

    
    def _get_strategy(self, method_id):
        cb = getattr(self, '_status_callback', None)
        eq = getattr(self, '_earthquake_method', EARTHQUAKE_METHOD_CURVE)
        if method_id == 1:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'sneaky', 15, status_callback = cb, earthquake_method = eq)
        if method_id == 2:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'superminion', 3.1, status_callback = cb, earthquake_method = eq)
        if method_id == 3:
            return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'valkyrie', 5.5, status_callback = cb, earthquake_method = eq)
        if method_id == 4:
            return EdragStrategy(self.input, self.vision, self.config, self.stop_event, status_callback = cb, earthquake_method = eq)
        return TroopSpamStrategy(self.input, self.vision, self.config, self.stop_event, 'sneaky', 15, status_callback = cb, earthquake_method = eq)

    
    def _wait_for_battle_end(self, is_sneaky):
        if is_sneaky:
            if self.stop_event.wait(3):
                return None
            (sx, sy) = self._wait_for_image('surrender.png', timeout = 2, error = False)
            if sx:
                self.input.click(sx, sy, pause = 0.1)
                return None
            (bx, by) = self._wait_for_image('endbattle.png', timeout = 2, error = False)
            if bx:
                self.input.click(bx, by, pause = 0.1)
                return None
            return None
        (bx, by) = self._wait_for_image('endbattle.png', timeout = 60, error = False)
        if bx:
            self.input.click(bx, by, pause = 0.1)
            return None
        (sx, sy) = self._wait_for_image('surrender.png', timeout = 2, error = False)
        if sx:
            self.input.click(sx, sy, pause = 0.1)
            return None

    
    def _return_home(self):
        '''Dismiss Okay if present, then wait for ``returnhome.png`` (+ ``returnhome2.png`` on 16:10) or ``chestclaim.png`` (mutually exclusive).'''
        (ox, oy) = self._wait_for_image('okay.png', timeout = 10)
        if ox:
            self.input.click(ox, oy, pause = 0.1)
        (kind, hx, hy) = self._wait_for_return_home_or_chest_claim(timeout = 10)
        if kind == 'return' and hx:
            self.input.click(hx, hy, pause = 0.1)
            return ox is not None
        if kind == 'chest' and hx:
            logger.info('Post-battle UI: chestclaim.png (replacing return home); running chest flow')
            self.input.click(hx, hy, pause = 0.2)
            if self.stop_event.wait(0.35):
                return ox is not None
            self._tap_empty_until_chest_continue()
        return ox is not None

    
    def _wait_for_return_home_or_chest_claim(self, timeout = 10):
        '''
Poll one frame for ``returnhome.png`` (+ ``returnhome2.png`` on 16:10 only) then ``chestclaim.png`` (only one should match).
Returns (``"return"`` | ``"chest"``, x, y) or (None, None, None) on timeout.
'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None, None)
                continue
            self._update_config_size(frame)
            (rx, ry) = (None, None)
            returnhome_tpls = ('returnhome.png', 'returnhome2.png') if self.config.aspect_key == ASPECT_16_10 else ('returnhome.png',)
            for tpl in returnhome_tpls:
                (rx, ry) = self.vision.find_template(frame, tpl)
                if rx:
                    break  # [recovered: decompiler dropped this break, letting the last template overwrite a match]
            if rx:
                return ('return', rx, ry)
            (cx, cy) = self.vision.find_template(frame, 'chestclaim.png')
            if cx:
                return ('chest', cx, cy)
            if self.stop_event.wait(0.5):
                return (None, None, None)
            if time.time() - start < timeout:
                continue
        logger.warning('Timeout waiting for returnhome.png / returnhome2.png (16:10) or chestclaim.png')
        return (None, None, None)

    
    def _random_point_chest_tap_through(self):
        '''Random point near center-right of the capture for chest tap-through (±85 px from anchor).'''
        (w, h) = (self.config.width, self.config.height)  # [recovered: pycdc reversed STORE_FAST_STORE_FAST pairs]
        if w <= 1 or h <= 1:
            (w, h) = (self.config.ref_width, self.config.ref_height)
        cx = int(w * 0.75)
        cy = h // 2
        j = 85
        return (max(0, min(w - 1, cx + random.randint(-j, j))), max(0, min(h - 1, cy + random.randint(-j, j))))

    
    def _tap_empty_until_chest_continue(self):
        '''After ``chestclaim`` was clicked: tap center-right (±85px) until ``chestcontinue.png``, then click it (home).'''
        CHEST_TAP_TIMEOUT = 120
        deadline = time.time() + CHEST_TAP_TIMEOUT
        while time.time() < deadline:
            self._check_stop()
            (nx, ny) = self._random_point_chest_tap_through()
            self.input.click_at(nx, ny, rand = False)
            t0 = time.time()
            if self.stop_event.wait(0.15):
                return None
            frame2 = self.window.screenshot()
            if not frame2 is None:
                self._update_config_size(frame2)
                (tx, ty) = self.vision.find_template(frame2, 'chestcontinue.png')
                if tx:
                    logger.info('Chest reward: chestcontinue.png found; clicking (expect home village)')
                    self.input.click(tx, ty, pause = 0.25)
                    return None
            elapsed = time.time() - t0
            to_wait = max(0.05, 0.5 - elapsed)
            if self.stop_event.wait(to_wait):
                return None
        logger.warning(f'''chestcontinue.png not seen within {int(CHEST_TAP_TIMEOUT)}s after chest claim; continuing bot loop''')  # [recovered: decompiler misnested this inside the loop, ending the tap-through after one tap]
        return None

    
    def _is_star_bonus_claimed(self):
        '''True if neither emptystar nor glowstar matches strongly (bonus claimed / not shown).'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        for template in ('emptystar.png', 'glowstar.png'):
            (_, _, confidence) = self.vision.find_template_with_confidence(frame, template, threshold = 0)  # [recovered + verified against original bytecode]
            if confidence >= _STAR_BONUS_THRESHOLD:
                return False
        return True

    
    def _is_bb_star_bonus_finished(self):
        '''True when ``bstar.png`` is not visible in the bottom half (BB star bonus attacks done).'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        bot_roi = VisionService.bottom_half_region(frame)
        (_, _, confidence) = self.vision.find_template_with_confidence(frame, _BB_STAR_BONUS_TEMPLATE, threshold = 0.0, region = bot_roi)  # [recovered + verified against original bytecode]
        return confidence < _STAR_BONUS_THRESHOLD

    
    def _home_screen_recovery(self):
        '''Ensures we are back at Home Village. Escapes popups, stray screens, live battles,
        Builder Base, and human interference (Clan Chat, Profile, Settings, Shop).'''
        for iteration in range(25):
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(1):
                    return None
                continue
            self._update_config_size(frame)

            # 1. Universal Zero-Gem Guard: dismiss any gem purchase dialog immediately
            if self._dismiss_gem_prompt_if_open(frame):
                if self.stop_event.wait(0.35):
                    return None
                continue

            # 2. Live battle detection: surrender/finish to return home
            (sx, sy) = self.vision.find_template(frame, 'surrender.png')
            if sx:
                logger.info('Recovery: live battle detected — surrendering to return home')
                self.input.click(sx, sy, pause = 0.3)
                if self.stop_event.wait(0.5):
                    return None
                continue

            (ebx, eby) = self.vision.find_template(frame, 'endbattle.png')
            if ebx:
                logger.info('Recovery: end battle button detected — ending battle')
                self.input.click(ebx, eby, pause = 0.3)
                if self.stop_event.wait(0.5):
                    return None
                continue

            # 3. Return home button detection (Home and Builder Base)
            for r_tpl in ('returnhome.png', 'returnhome2.png', 'breturnhome.png', 'breturnhome1920.png'):
                if get_template_path(r_tpl).exists():
                    (rx, ry) = self.vision.find_template(frame, r_tpl)
                    if rx:
                        logger.info('Recovery: clicking %s', r_tpl)
                        self.input.click(rx, ry, pause = 0.3)
                        if self.stop_event.wait(0.5):
                            return None
                        break

            # 4. Check if Home Village HUD is fully visible and active
            top_roi = VisionService.top_half_region(frame)
            home_roi = VisionService.bottom_half_region(frame)
            (ax, ay) = self.vision.find_template(frame, 'attack.png', region = home_roi)
            (hx, hy) = self._find_home_village_builder(frame, top_roi)
            if ax or hx:
                self._reload_first_seen = None
                self._deselect_wall_ui()
                return None

            # 5. Stranded in Builder Base check: leave via nboat to return to Home Village
            # (Note: NEVER search for or click 'boat.png' here! 'boat.png' is in Home Village and opens Builder Base!)
            is_bb = False
            (mx, my) = self.vision.find_template(frame, 'mbuilder.png', region = top_roi)
            if mx:
                is_bb = True
            elif get_template_path('nboat.png').exists():
                (nx, ny) = self.vision.find_template(frame, 'nboat.png', threshold = 0.72)
                if nx:
                    is_bb = True
            if is_bb:
                logger.info('Recovery: stranded in Builder Base — leaving via nboat to return to Home Village')
                self._leave_builder_base_with_nboat(settle_before_drag = False)
                if self.stop_event.wait(1.0):
                    return None
                continue

            # 6. Connection reload dialog handling
            if get_template_path('reload.png').exists():
                (lx, ly) = self.vision.find_template(frame, 'reload.png')
                if lx:
                    now = time.monotonic()
                    first = getattr(self, '_reload_first_seen', None)
                    if first is None:
                        self._reload_first_seen = now
                        logger.warning('Recovery: connection-lost dialog detected — waiting %ds before reloading', _RELOAD_GRACE_SECONDS)
                    elif now - first >= _RELOAD_GRACE_SECONDS:
                        logger.warning('Recovery: connection-lost dialog persisted — clicking RELOAD')
                        self.input.click(lx, ly, pause = 1.0)
                        self._reload_first_seen = None
                        if self.stop_event.wait(10):
                            return None
                    if self.stop_event.wait(2):
                        return None
                    continue

            # 7. Standard dialogs & Supercell progression announcements
            if self._dismiss_okay_or_exit_on_frame(frame):
                if self.stop_event.wait(0.35):
                    return None
                continue

            # 8. Human interference fallback: Clan Chat open, Profile, Settings, Shop, or selection overlay
            logger.info('Recovery: Human interference / overlay detected — sending Escape and deselecting')
            self.input.send_escape()
            self.input.click(pause = 0.3, *self.config.get_point('empty'))
            if self.stop_event.wait(0.5):
                return None
        return None

    
    def _switch_account_and_load_home(self, username):
        '''Open Settings → Change user, OCR-click username, wait for home. Raises on failure.'''
        cb = getattr(self, '_status_callback', None)
        msg = f'''Multi-run: switching to {username!r}'''
        logger.info(msg)
        if cb:
            cb(msg)
        (stx, sty) = self._wait_for_image('settings.png')
        if not stx:
            raise RuntimeError('Multi-run: settings button not found')
        self.input.click(stx, sty, pause = 0.25)
        (cux, cuy) = self._wait_for_image('changeuser.png')
        if not cux:
            raise RuntimeError('Multi-run: change user button not found')
        self.input.click(cux, cuy, pause = 1)
        (ucx, ucy) = self._wait_for_player_name(username, timeout = 25, min_confidence = 70, tesseract_config = '--psm 11', match_alnum_only = True, fuzzy_min_ratio = 0.8, white_text = True)
        if not ucx:
            err = f'''Multi-run: could not find username "{username}" on screen (OCR)'''
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self.input.click(ucx, ucy, pause = 0.2)
        if self.stop_event.wait(1):
            self._check_stop()
        (ax, ay) = self._wake_home_and_wait_for_attack(timeout = 30)
        if not ax:
            err = f'''Multi-run: Home Village not ready after loading {username!r} (builder.png|gbuilder.png / attack.png timeout after login / leaving Builder Base)'''
            logger.error(err)
            if cb:
                cb(err)
            raise RuntimeError(err)
        self._loot_prev_resources = None

    
    def _wake_home_and_wait_for_attack(self, timeout = 30):
        '''
After switching accounts: dismiss idle UI, then poll the **top half** for village type
(``mbuilder.png`` = Builder Base; ``builder.png`` or ``gbuilder.png`` = Home Village). If Builder Base,
leave via :meth:`_leave_builder_base_with_nboat`. When Home Village is detected, return
``attack.png`` coordinates from the **bottom half** (battle bar) once visible — same
template as :meth:`_find_match_and_attack` uses to start battles.
Each iteration dismisses ``okay.png`` / ``exit.png`` if present, then village / attack logic; else nudge.
'''
        frame = self.window.screenshot()
        self._update_config_size(frame)
        empty_pt = self.config.get_point('empty')
        self.input.click(pause = 0.2, *empty_pt)
        self.input.scroll(*self._scroll_point(), 20)
        delay = random.uniform(0.1, 0.3)
        if self.stop_event.wait(delay):
            return (None, None)
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if not frame is None:
                self._update_config_size(frame)
                if self._dismiss_okay_or_exit_on_frame(frame):
                    if self.stop_event.wait(0.25):
                        return (None, None)
                    continue
                top_roi = VisionService.top_half_region(frame)
                (mx, my) = self.vision.find_template(frame, 'mbuilder.png', region = top_roi)
                if mx:
                    logger.info('Account loaded in Builder Base (mbuilder.png); leaving to Home Village')
                    cb = getattr(self, '_status_callback', None)
                    if cb:
                        cb('Multi-run: Builder Base on login — leaving (nboat)')
                    self._leave_builder_base_with_nboat(settle_before_drag = False)
                    if self.stop_event.wait(1):
                        return (None, None)
                    continue
                (hx, hy) = self._find_home_village_builder(frame, top_roi)
                if hx:
                    bot_roi = VisionService.bottom_half_region(frame)
                    (ax, ay) = self.vision.find_template(frame, 'attack.png', region = bot_roi)
                    if ax:
                        return (ax, ay)
            self._nudge_view_to_reveal_attack()
            if self.stop_event.wait(0.35):
                return (None, None)
        return (None, None)  # [recovered: decompiler put an unconditional return inside the loop, so only one poll ever ran]

    
    def _detect_village_type(self, frame = None):
        '''Return ``"home"``, ``"builder"``, or ``None`` from top-half builder portraits.'''
        if frame is None:
            frame = self.window.screenshot()
        if frame is None or frame.size == 0:
            return None
        self._update_config_size(frame)
        top_roi = VisionService.top_half_region(frame)
        (mx, my) = self.vision.find_template(frame, 'mbuilder.png', region = top_roi)
        if mx:
            return 'builder'
        (hx, hy) = self._find_home_village_builder(frame, top_roi)
        if hx:
            return 'home'

    
    def _go_to_builder_base_with_boat(self):
        '''Home Village → Builder Base via ``boat.png``.'''
        if not self._builder_base:
            logger.warning('Refusing to navigate to Builder Base: Builder Base is turned off.')
            return False
        self._check_stop()
        (bx, by) = self._wait_for_image('boat.png', timeout = 15, error = False)
        if not bx:
            logger.warning('boat.png not found — cannot switch to Builder Base')
            return False
        self.input.click(bx, by, pause = 0.25)
        if self.stop_event.wait(1):
            return False
        (mx, my) = self._wait_for_image('mbuilder.png', timeout = 15, error = False)
        if not mx:
            logger.warning('mbuilder.png not found after boat — may still be in Home Village')
            return False
        return True

    
    def _ensure_correct_village(self, builder_base):
        '''Before farming: switch villages if the wrong builder portrait is showing.'''
        self._check_stop()
        self.input.click(pause = 0.15, *self.config.get_point('empty'))
        if self.stop_event.wait(0.2):
            return None
        village = self._detect_village_type()
        if builder_base:
            if village == 'builder':
                return None
            if village == 'home':
                logger.info('Startup: in Home Village but Builder Base was selected — taking boat')
                self._go_to_builder_base_with_boat()
                return None
            logger.warning('Startup: could not detect village (expected Builder Base)')
            return None
        if village == 'home':
            return None
        if village == 'builder':
            logger.info('Startup: in Builder Base but Home Village was selected — leaving (nboat)')
            self._leave_builder_base_with_nboat()
            return None
        logger.warning('Startup: could not detect village (expected Home Village)')

    
    def _leave_builder_base_with_nboat(self, settle_before_drag = True):
        '''
Pan down-left from screen center (~500px), then click ``nboat.png`` to return to Home Village.
Does not check ``mbuilder.png`` first — call only when a BB→HV trip is intended.

``settle_before_drag``: small delay after prior UI (e.g. collect clicks) before capturing
dimensions and dragging.
'''
        self._check_stop()
        if settle_before_drag and self.stop_event.wait(0.75):
            self._check_stop()
        logger.info('Leaving Builder Base (drag + nboat)')
        cb = getattr(self, '_status_callback', None)
        if cb:
            cb('Multi-run: leaving Builder Base (nboat)')
        self._bb_pan_down_left_from_center()
        (nx, ny) = self._wait_for_image('nboat.png', timeout = 12, error = False)
        if nx:
            self.input.click(nx, ny, pause = 0.25)
            return None
        logger.warning('nboat.png not found after Builder Base drag — may still be in Builder Base')

    
    def _multi_run_collect_home_village_resources(self):
        '''Multi-run: tap Home Village collect bubbles if visible, before taking the boat to Builder Base.'''
        cb = getattr(self, '_status_callback', None)
        logger.info('Multi-run: Home Village collect (hgold, helixir, hdelixir, collect)')
        if cb:
            cb('Multi-run: Home Village collect')
        for tpl in ('hgold.png', 'helixir.png', 'hdelixir.png', 'collect.png'):
            self._check_stop()
            if not get_template_path(tpl).exists():
                continue
            (rx, ry) = self._find_template_once(tpl, threshold = 0.7)
            if not rx:
                continue
            self.input.click(rx, ry, pause = 0.15)

    
    def _multi_run_builder_base_after_session(self):
        """
Multi-run only: after an account's farming session, collect Home Village resources if icons
appear, open the secondary base via boat, collect builder resources if icons appear,
optionally run the clock boost chain, then leave Builder Base.
"""
        if not self._builder_base:
            return None
        self._multi_run_collect_home_village_resources()
        cb = getattr(self, '_status_callback', None)
        msg = 'Multi-run: Builder Base (boat → collect)'
        logger.info(msg)
        if cb:
            cb(msg)
        (bx, by) = self._wait_for_image('boat.png', timeout = 15, error = False)
        if not bx:
            logger.warning('Multi-run: boat.png not found — skipping Builder Base step')
            return None
        self.input.click(bx, by, pause = 0.2)
        if self.stop_event.wait(1):
            self._check_stop()
        for tpl in ('bgold.png', 'belixir.png', 'bgem.png'):
            self._check_stop()
            (rx, ry) = self._find_template_once(tpl, threshold = 0.7)
            if not rx:
                continue
            self.input.click(rx, ry, pause = 0.15)
        self._check_stop()
        (cx, cy) = self._wait_for_image('bclock.png', timeout = 2, error = False)
        if cx:
            self.input.click(cx, cy, pause = 0.2)
            if self.stop_event.wait(1):
                self._check_stop()
            (cbx, cby) = self._wait_for_image('clockboost.png', timeout = 10, error = False)
            if cbx:
                self.input.click(cbx, cby, pause = 0.2)
            if self.stop_event.wait(1):
                self._check_stop()
            (bux, buy) = self._wait_for_image('boost.png', timeout = 10, error = False)
            if bux:
                self.input.click(bux, buy, pause = 0.15)
        self._leave_builder_base_with_nboat(settle_before_drag = True)

    
    def _frame_shows_supercell_login_prompt(self, frame):
        """True if OCR sees the Supercell ID login line (list scroll won't help)."""
        if frame is None or frame.size == 0:
            return False
        words = self.vision.find_words_ocr(frame, query = None, min_confidence = 20, preprocess = True, tesseract_config = '--psm 11', white_text = True)
        blob = ' '.join([ w.text for w in words ]).lower()
        if 'supercell id' in blob:
            return True
        if 'log in' in blob and 'supercell' in blob:
            return True
        return False

    
    def _scroll_player_list_with_drag(self, frame):
        '''Drag ~200px upward from lower-right (client coords) to scroll the change-user list.'''
        if frame is None or frame.size == 0:
            return None
        (h, w) = frame.shape[:2]
        x1 = int(w * 0.86) + random.randint(-15, 15)
        x1 = max(int(w * 0.72), min(w - 8, x1))
        y1 = int(h * 0.86) + random.randint(-12, 12)
        y1 = max(int(h * 0.55), min(h - 12, y1))
        y2 = max(int(h * 0.12), y1 - 200)
        x2 = x1
        self.input.mouse_down(x1, y1)
        self.input.human_move(x1, y1, x2, y2, duration = random.uniform(0.28, 0.42))
        self.input.mouse_up(x2, y2)

    
    def _wait_for_player_name(self, text, timeout = 25, error = True, region = None, **ocr_kwargs):
        '''
Like :meth:`_wait_for_text`, but after each failed OCR pass drags upward in the lower-right
to scroll the account list before trying again.

OCR is limited to the right half of the window unless ``region`` is passed explicitly.
'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            roi = region if not region is None else VisionService.right_half_region(frame)
            (x, y) = self.vision.find_word_on_screen(frame, text, region = roi, **ocr_kwargs)
            if x:
                return (x, y)
            if self._frame_shows_supercell_login_prompt(frame):
                msg = f'''Multi-run: "Log in to Supercell ID" is showing and {text!r} was not found — log in or dismiss that screen, then retry.'''
                logger.warning(msg)
                cb = getattr(self, '_status_callback', None)
                if cb:
                    cb(msg)
                raise RuntimeError(msg)
            self._scroll_player_list_with_drag(frame)
            if self.stop_event.wait(0.45):
                return (None, None)
            if error:
                logger.warning(f'''Timeout waiting for player name OCR match: {text!r}''')
        return (None, None)

    
    def _wait_for_text(self, text, timeout = 10, error = True, region = None, **ocr_kwargs):
        '''Poll screenshots until OCR finds ``text`` (substring match). Returns click center.'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                if self.stop_event.wait(0.5):
                    return (None, None)
                continue
            self._update_config_size(frame)
            (x, y) = self.vision.find_word_on_screen(frame, text, region = region, **ocr_kwargs)
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f'''Timeout waiting for OCR text containing {text!r}''')
        return (None, None)

    
    def _dismiss_open_popup(self):
        '''Best-effort close of whatever popup is on screen (okay/exit) so the flow underneath is usable again.'''
        frame = self.window.screenshot()
        if frame is None:
            return False
        self._update_config_size(frame)
        return self._dismiss_okay_or_exit_on_frame(frame)


    def _ensure_valkyrie_army_from_recipes(self):
        '''If Valkyrie army template is missing, load it from Saved Recipes. Returns False on failure.'''
        (vx, vy) = self._wait_for_image('valkarmy.png', timeout = 3, error = False)
        if vx:
            return True
        (sx, sy) = self._wait_for_image('savedrecipes.png')
        if not sx:
            logger.warning('Saved Recipes button not found while ensuring Valkyrie army')
            return False
        self.input.click(sx, sy, pause = 0.2)
        (rx, ry) = self._wait_for_image('valkrecipe.png')
        if not rx:
            logger.warning('Valkyrie recipe template not found')
            self._dismiss_open_popup()  # close the recipes popup we opened
            return False
        (ux, uy) = self._wait_for_image('use.png', y_anchor = ry, y_slop = 200)
        if not ux:
            logger.warning('Use button not found near Valkyrie recipe row')
            self._dismiss_open_popup()  # close the recipes popup we opened
            return False
        self.input.click(ux, uy, pause = 0.2)
        if self.stop_event.wait(0.35):
            return False
        (vx2, _) = self._wait_for_image('valkarmy.png', timeout = 5, error = False)
        if not vx2:
            logger.warning('valkarmy.png still not visible after applying saved recipe')
            return False
        return True

    
    def _search_region_for_template(self, frame, template, region = None, y_anchor = None, y_slop = 200):
        if not region is None:
            return region
        if not y_anchor is None:
            (h, w) = frame.shape[:2]
            y0 = max(0, y_anchor - y_slop)
            y1 = min(h, y_anchor + y_slop)
            return (0, y0, w, y1 - y0)
        if template in TOP_HALF_BOT_TEMPLATES:
            return VisionService.top_half_region(frame)
        if template in BOTTOM_HALF_BOT_TEMPLATES:
            return VisionService.bottom_half_region(frame)

    
    def _find_template_once(self, template, region = None, y_anchor = None, y_slop = 200, threshold = 0.8):
        '''One screenshot; match template or return (None, None). No polling.'''
        self._check_stop()
        frame = self.window.screenshot()
        if frame is None:
            return (None, None)
        self._update_config_size(frame)
        search_region = self._search_region_for_template(frame, template, region, y_anchor, y_slop)
        return self.vision.find_template(frame, template, threshold = threshold, region = search_region)

    
    def _wait_for_any_image(self, templates, timeout = 10, error = True, threshold = 0.8, region = None, region_from_frame = None):
        '''First ordered template match wins (checked left-to-right each frame).'''
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            search_region = region
            if search_region is None and region_from_frame is not None:  # [recovered: both conditions were inverted]
                search_region = region_from_frame(frame)
            for template in templates:
                tpl_region = search_region
                if tpl_region is None:
                    tpl_region = self._search_region_for_template(frame, template, None, None, 200)
                (x, y) = self.vision.find_template(frame, template, threshold = threshold, region = tpl_region)
                if x:  # [recovered: was an unconditional `return`, so only the first template was ever checked]
                    return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
            if time.time() - start < timeout:
                continue
        if error:
            logger.warning(f'''Timeout waiting for any of {templates}''')
        return (None, None)

    
    def _wait_for_image(self, template, timeout = 10, error = True, region = None, y_anchor = None, y_slop = 200, threshold = 0.8):
        start = time.time()
        while time.time() - start < timeout:
            self._check_stop()
            frame = self.window.screenshot()
            if frame is None:
                continue
            self._update_config_size(frame)
            search_region = self._search_region_for_template(frame, template, region, y_anchor, y_slop)
            (x, y) = self.vision.find_template(frame, template, threshold = threshold, region = search_region)
            if x:
                return (x, y)
            if self.stop_event.wait(0.5):
                return (None, None)
        if error:
            logger.warning(f'''Timeout waiting for {template}''')
        return (None, None)



    def _deploy_bb_night_witches(self, frame):
        strategy = AttackStrategy(self.input, self.vision, self.config, self.stop_event)
        roi = VisionService.bottom_half_region(frame)
        centers = VisionService.find_all_template_centers(frame, 'nightwitch.png', region = roi, max_matches = 12, suppress_pad_frac = _BB_TEMPLATE_SUPPRESS_PAD)
        if not centers:
            return False
        self.input.click(centers[0][0], centers[0][1], pause = 0.3, rand = False)
        if self.stop_event.wait(0.2):
            return True
        for (px, py) in strategy._even_diamond_top_perimeter_points(frame, len(centers), reserve_top_corner_slot = True):
            self._check_stop()
            self.input.click(px, py, pause = _EDRAG_DELAY, rand = False)
        self._deploy_bb_battle_or_flying_machine(strategy)
        return True

    def _collect_home_village_resources(self):
        self._multi_run_collect_home_village_resources()

    def _collect_builder_base_resources(self):
        cb = getattr(self, '_status_callback', None)
        logger.info('Collect: Builder Base (bgold, belixir, bgem, clock boost)')
        if cb:
            cb('Collecting Builder Base resources')
        for tpl in ('bgold.png', 'belixir.png', 'bgem.png'):
            self._check_stop()
            (rx, ry) = self._find_template_once(tpl, threshold = 0.7)
            if rx:
                self.input.click(rx, ry, pause = 0.15)
        self._check_stop()
        (cx, cy) = self._wait_for_image('bclock.png', timeout = 2, error = False)
        if cx:
            self.input.click(cx, cy, pause = 0.2)
            if self.stop_event.wait(1.0):
                self._check_stop()
            (cbx, cby) = self._wait_for_image('clockboost.png', timeout = 2.5, error = False)
            if cbx:
                self.input.click(cbx, cby, pause = 0.2)
