"""Bot, license, and trial orchestration for the Qt UI."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.bot import Bot
from app.core.run_plan import RunPlan
from app.services.license import (
    LicenseManager,
    LicenseState,
    clear_saved_key,
    load_saved_key,
)
from app.services.trial import (
    TRIAL_HEARTBEAT_INTERVAL_MS,
    TrialResult,
    fetch_trial_status,
    send_trial_heartbeat,
)
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import load_profile_settings

logger = setup_logger("BotController")


class BotController(QObject):
    statusChanged = Signal(str, bool)
    botStarted = Signal()
    botFinished = Signal(object)
    licenseChanged = Signal(object, str)
    trialUpdated = Signal(object)
    licenseRevoked = Signal(str)
    trialExpired = Signal()
    runningChanged = Signal(bool)

    def __init__(self, bot_version: str) -> None:
        super().__init__()
        self._bot_version = bot_version
        self._bot = Bot()
        self._bot_thread: Optional[threading.Thread] = None
        self._lic = LicenseManager(bot_version=bot_version)
        self._lic.set_on_state_change(self._on_license_state_change_bg)
        self._last_license_state = LicenseState.EMPTY
        self._last_license_reason = "empty"
        self._trial_remaining_seconds: Optional[int] = None
        self._trial_last_mono = 0.0
        self._trial_session = 0
        self._trial_probe_pending = False
        self._trial_timer: Optional[QTimer] = None
        self._trial_tick_session = 0

    def prime(self) -> None:
        saved = load_saved_key()
        self._lic.start(saved)
        self.licenseChanged.emit(self._lic.state, "")
        QTimer.singleShot(1000, self.request_trial_probe)

    def license_state(self) -> LicenseState:
        return self._lic.state

    def license_user_message(self) -> str:
        return self._lic.user_message

    def license_expiry_subcaption(self) -> str:
        return self._lic.license_expiry_subcaption()

    def trial_remaining_seconds(self) -> Optional[int]:
        return self._trial_remaining_seconds

    def is_running(self) -> bool:
        return self._bot_thread is not None and self._bot_thread.is_alive()

    def recheck_license(self, new_key: Optional[str] = None) -> None:
        self._lic.recheck(new_key=new_key)

    def mark_license_stale(self) -> None:
        self._lic.mark_stale()

    def try_unpair_async(self, key: str, on_done: Callable[[bool, str], None]) -> None:
        def worker() -> None:
            ok, reason = self._lic.try_unpair(key)
            if ok:
                clear_saved_key()
                self._lic.recheck(new_key="")

            def ui_done() -> None:
                on_done(ok, reason)

            QTimer.singleShot(0, self, ui_done)

        threading.Thread(target=worker, daemon=True, name="UnpairWorker").start()

    def request_portal_url_async(
        self, key: str, on_done: Callable[[str, str], None]
    ) -> None:
        """Fetch a Stripe customer-portal link off the GUI thread; on_done(url, reason)."""

        def worker() -> None:
            url, reason = self._lic.try_portal_url(key)

            def ui_done() -> None:
                on_done(url, reason)

            QTimer.singleShot(0, self, ui_done)

        threading.Thread(target=worker, daemon=True, name="PortalWorker").start()

    def request_trial_probe(self) -> None:
        if self._lic.state == LicenseState.VALID:
            return
        if self._trial_probe_pending:
            return
        self._trial_probe_pending = True

        def worker() -> None:
            result = fetch_trial_status(bot_version=self._bot_version)

            def done() -> None:
                self._on_trial_probe_done(result)

            QTimer.singleShot(0, done)

        threading.Thread(target=worker, daemon=True, name="TrialProbe").start()

    def _on_trial_probe_done(self, result: TrialResult) -> None:
        self._trial_probe_pending = False
        if self._lic.state == LicenseState.VALID:
            return
        if not result.ok and result.reason in ("network_error", "error"):
            self.trialUpdated.emit(None)
            return
        self._trial_remaining_seconds = result.remaining_seconds if result.ok else 0
        self.trialUpdated.emit(result)

    def apply_trial_balance_for_start(self, result: TrialResult) -> None:
        self._trial_remaining_seconds = result.remaining_seconds
        self.trialUpdated.emit(result)

    def start(self, plan: RunPlan) -> None:
        if self.is_running():
            return

        def worker() -> None:
            error_msg = None

            def on_status(msg: str) -> None:
                self.statusChanged.emit(msg, "not found" in msg.lower())

            try:
                self._bot.start(
                    plan,
                    status_callback=on_status,
                    earthquake_method=load_profile_settings().earthquake_method,
                )
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}" if str(exc) else f"{type(exc).__name__}"
                logger.exception("Bot thread failed")
            finally:
                self.botFinished.emit(error_msg)

        self._bot_thread = threading.Thread(
            target=worker, daemon=True, name="BotThread"
        )
        self.runningChanged.emit(True)
        self.botStarted.emit()
        self._bot_thread.start()

        if self._lic.state != LicenseState.VALID:
            self.begin_trial_heartbeat()

    def stop(self) -> None:
        self.flush_trial_heartbeat()
        self._bot.stop()
        self.statusChanged.emit("Stopping...", False)

    def begin_trial_heartbeat(self) -> None:
        self._trial_session += 1
        self._trial_tick_session = self._trial_session
        self._trial_last_mono = time.monotonic()
        if self._trial_timer is None:
            self._trial_timer = QTimer(self)
            self._trial_timer.setInterval(TRIAL_HEARTBEAT_INTERVAL_MS)
            self._trial_timer.timeout.connect(self._on_trial_timer)
        self._trial_timer.stop()
        self._trial_timer.start()

    def flush_trial_heartbeat(self) -> None:
        if self._trial_timer is not None:
            self._trial_timer.stop()
        session_snap = self._trial_session
        self._trial_session += 1

        if self._lic.state == LicenseState.VALID:
            return

        elapsed = int(time.monotonic() - self._trial_last_mono)
        if elapsed <= 0:
            return

        def flush_worker() -> None:
            send_trial_heartbeat(elapsed, bot_version=self._bot_version)

        threading.Thread(target=flush_worker, daemon=True, name="TrialFlush").start()
        del session_snap

    def _on_trial_timer(self) -> None:
        session = self._trial_tick_session
        if session != self._trial_session:
            return
        if self._lic.state == LicenseState.VALID:
            if self._trial_timer:
                self._trial_timer.stop()
            return

        now = time.monotonic()
        elapsed = int(now - self._trial_last_mono)
        self._trial_last_mono = now

        def worker() -> None:
            result = send_trial_heartbeat(elapsed, bot_version=self._bot_version)

            def apply() -> None:
                self._apply_trial_result(result, session)

            QTimer.singleShot(0, apply)

        threading.Thread(target=worker, daemon=True, name="TrialHeartbeat").start()

    def _apply_trial_result(self, result: TrialResult, session: int) -> None:
        if session != self._trial_tick_session or session != self._trial_session:
            return
        if not result.ok or result.remaining_seconds <= 0:
            self._trial_remaining_seconds = 0
            self._trial_session += 1
            if self._trial_timer:
                self._trial_timer.stop()
            self.trialUpdated.emit(result)
            if self.is_running():
                self.stop()
                self.trialExpired.emit()
            return
        self._trial_remaining_seconds = result.remaining_seconds
        self.trialUpdated.emit(result)

    def _on_license_state_change_bg(self, state: LicenseState, reason: str) -> None:
        self._last_license_state = state
        self._last_license_reason = reason
        self.licenseChanged.emit(state, reason)

    def handle_license_state_on_main_thread(
        self, state: LicenseState, reason: str
    ) -> None:
        """Must run on the GUI thread (connected to licenseChanged)."""
        if state == LicenseState.VALID:
            self._trial_remaining_seconds = None
            self.flush_trial_heartbeat()
        elif reason != "stale":
            self.request_trial_probe()

        if state in (LicenseState.INVALID, LicenseState.UNREACHABLE):
            if self.is_running():
                self.stop()
                self.licenseRevoked.emit(self._lic.user_message)

    def on_bot_finished(self) -> None:
        self.runningChanged.emit(False)
        self.flush_trial_heartbeat()
        if self._lic.state != LicenseState.VALID:
            self.request_trial_probe()
