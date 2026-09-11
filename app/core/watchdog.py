"""Autonomous Watchdog and Error Auto-Recovery Engine for Clash AutoLoot.

Detects, monitors, and automatically recovers from:
- Game desynchronization ("Client and server are out of sync")
- Connection loss ("Connection lost. Try again.")
- Personal break forced rest ("Take a Break! Your villagers need to rest.")
- Multi-device login conflict ("Another device is connecting to this village")
- Raid summary popup on login ("Your village was raided while you were away")
- Unresponsive or minimized emulator window
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.utils.logger import setup_logger

logger = setup_logger("Watchdog")


@dataclass
class WatchdogEvent:
    event_type: str
    action_taken: str
    timestamp: float
    success: bool


class AutoRecoveryWatchdog:
    """Monitors game frames and automatically resolves modal interruptions."""

    def __init__(
        self,
        vision_service,
        input_service,
        window_service,
        status_callback: Optional[Callable[[str], None]] = None,
        notification_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.vision = vision_service
        self.input = input_service
        self.window = window_service
        self.status_cb = status_callback
        self.notify_cb = notification_callback
        self.consecutive_recoveries = 0
        self.last_recovery_time = 0.0
        self.max_consecutive_recoveries = 5

    def check_and_recover(self, frame) -> bool:
        """Inspects current frame for modal popups, errors, or reload prompts.

        Returns True if a recovery action was executed, False if state is normal.
        """
        if frame is None:
            return self._handle_blank_frame()

        # 1. Check for standard Supercell "Okay" / "Try Again" dialogs
        okay_match = self.vision.find_image_in_frame(frame, "okay")
        if okay_match:
            logger.info("Watchdog: Detected Supercell modal prompt ('okay.png'). Initiating auto-recovery.")
            if self.status_cb:
                self.status_cb("Watchdog: Auto-recovering from game popup...")
            
            # Natural human reaction pause before clicking
            time.sleep(random.uniform(1.8, 3.2))
            self.input.click(okay_match, pause=1.5)
            self._record_recovery("Modal Dismissed ('Okay')")
            time.sleep(random.uniform(4.0, 7.0))
            return True

        # 2. Check for "Return Home" if left in battle or spectator screen
        return_match = self.vision.find_image_in_frame(frame, "returnhome")
        if return_match:
            logger.info("Watchdog: Detected orphaned battle screen ('returnhome.png'). Returning to village.")
            if self.status_cb:
                self.status_cb("Watchdog: Returning home from stranded screen...")
            time.sleep(random.uniform(1.0, 2.0))
            self.input.click(return_match, pause=1.5)
            self._record_recovery("Return Home Executed")
            time.sleep(random.uniform(3.0, 5.0))
            return True

        # 3. Check for Builder Base return home
        breturn_match = self.vision.find_image_in_frame(frame, "breturnhome")
        if breturn_match:
            logger.info("Watchdog: Detected orphaned Builder Base screen ('breturnhome.png'). Returning.")
            time.sleep(random.uniform(1.0, 2.0))
            self.input.click(breturn_match, pause=1.5)
            self._record_recovery("Builder Return Home Executed")
            time.sleep(random.uniform(3.0, 5.0))
            return True

        # 4. Check for End Battle or Surrender if stuck
        surrender_match = self.vision.find_image_in_frame(frame, "surrender")
        if surrender_match:
            logger.info("Watchdog: Detected orphaned surrender prompt. Confirming surrender.")
            time.sleep(random.uniform(1.0, 1.8))
            self.input.click(surrender_match, pause=1.2)
            time.sleep(random.uniform(1.0, 1.5))
            # Confirm okay if popped up
            conf_frame = self.window.screenshot()
            if conf_frame is not None:
                conf_okay = self.vision.find_image_in_frame(conf_frame, "okay")
                if conf_okay:
                    self.input.click(conf_okay, pause=1.5)
            self._record_recovery("Surrender Confirmed")
            return True

        # Reset consecutive counter on clean frames if enough time has passed
        if time.time() - self.last_recovery_time > 30.0:
            self.consecutive_recoveries = 0

        return False

    def _handle_blank_frame(self) -> bool:
        """Handles missing window capture frames (emulator minimized or obscured)."""
        logger.warning("Watchdog: Captured empty frame. Checking window state...")
        hwnd = self.window.hwnd
        if not hwnd:
            return False

        # Attempt to bring emulator window to foreground
        try:
            from app.services.window import is_window_valid
            if is_window_valid(hwnd):
                import ctypes
                user32 = ctypes.windll.user32
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
                time.sleep(1.0)
                logger.info("Watchdog: Restored emulator window to foreground.")
                return True
        except Exception as e:
            logger.debug(f"Watchdog window restore error: {e}")
        return False

    def _record_recovery(self, action: str) -> None:
        self.consecutive_recoveries += 1
        self.last_recovery_time = time.time()
        logger.info(f"Watchdog: Recovery #{self.consecutive_recoveries} completed: {action}")
        if self.notify_cb:
            self.notify_cb("Watchdog Auto-Recovery", f"Recovered from disruption: {action}")
