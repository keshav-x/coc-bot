"""Native Windows Desktop Notifications for Clash AutoLoot.

Provides native Windows tray notifications for:
- Huge raid completions (e.g. >500k Gold/Elixir)
- Anti-Ban fatigue break starts & resumes
- License / Free Trial expiration alerts
- Autonomous Watchdog recoveries
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger("Notifications")

_tray_instance = None


def set_system_tray(tray_icon) -> None:
    """Registers the PySide6 QSystemTrayIcon from the main window."""
    global _tray_instance
    _tray_instance = tray_icon


class NotificationService:
    @staticmethod
    def send_notification(title: str, message: str, msecs: int = 5000) -> None:
        """Sends a desktop balloon/toast notification asynchronously."""
        def worker():
            try:
                global _tray_instance
                if _tray_instance is not None:
                    # PySide6 QSystemTrayIcon.showMessage
                    from PySide6.QtWidgets import QSystemTrayIcon
                    _tray_instance.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msecs)
                    return

                # PowerShell fallback if tray icon is not attached
                import subprocess
                clean_title = title.replace('"', '\\"')
                clean_msg = message.replace('"', '\\"')
                ps_script = (
                    f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); '
                    f'$notify = new-object system.windows.forms.notifyicon; '
                    f'$notify.icon = [system.drawing.systemicons]::information; '
                    f'$notify.visible = $true; '
                    f'$notify.showballoontip(5000, "{clean_title}", "{clean_msg}", [system.windows.forms.tooltipicon]::info);'
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
            except Exception as e:
                logger.debug(f"Could not send native desktop notification: {e}")

        threading.Thread(target=worker, daemon=True, name="NotificationWorker").start()

    @classmethod
    def notify_mega_raid(cls, gold: int, elixir: int, dark_elixir: int) -> None:
        if gold >= 500000 or elixir >= 500000:
            cls.send_notification(
                "💰 Massive Raid Completed!",
                f"Looted {gold:,} Gold | {elixir:,} Elixir | {dark_elixir:,} Dark Elixir!",
            )

    @classmethod
    def notify_break_started(cls, duration_mins: int) -> None:
        cls.send_notification(
            "☕ Anti-Ban Break Active",
            f"Bot is resting for {duration_mins} minutes to simulate realistic player behavior.",
        )

    @classmethod
    def notify_trial_warning(cls, remaining_mins: int) -> None:
        cls.send_notification(
            "⏳ Free Trial Ending Soon",
            f"You have {remaining_mins} minutes remaining in your free trial. Upgrade to Pro for $5/mo!",
        )
