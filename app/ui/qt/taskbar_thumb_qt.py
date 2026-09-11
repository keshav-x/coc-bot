"""Qt adapter for Windows taskbar thumbnail buttons."""

from __future__ import annotations

import platform
from typing import Optional

from PySide6.QtCore import QTimer, QObject
from PySide6.QtWidgets import QMainWindow

from app.ui.qt.bot_controller import BotController
from app.ui.qt.pages.run import RunPage
from app.utils.logger import setup_logger

logger = setup_logger("QtTaskbarThumb")


class QtTaskbarThumb(QObject):
    def __init__(
        self,
        controller: BotController,
        run_page: RunPage,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._run_page = run_page
        self._impl = None
        self._poll_timer = None
        self._setup_attempts = 0

    def setup(self, window: QMainWindow) -> bool:
        if platform.system() != "Windows":
            return False
        handle = window.windowHandle()
        if handle is None:
            self._setup_attempts += 1
            if self._setup_attempts < 5:
                QTimer.singleShot(100, lambda: self.setup(window))
            return False
        hwnd = int(handle.winId())
        if hwnd == 0:
            self._setup_attempts += 1
            if self._setup_attempts < 5:
                QTimer.singleShot(100, lambda: self.setup(window))
            return False
        try:
            from app.services.taskbar_thumb import TaskbarThumb

            self._impl = TaskbarThumb(
                on_start=self._run_page.request_start_from_taskbar,
                on_stop=self._run_page.request_stop_from_taskbar,
            )
            ok = self._impl.setup(hwnd, window.windowTitle())
            if not ok:
                self._impl = None
                return False
            self._poll_timer = QTimer(self)
            self._poll_timer.setInterval(50)
            self._poll_timer.timeout.connect(self._poll_once)
            self._poll_timer.start()
            return True
        except Exception as exc:
            logger.warning("Taskbar thumb setup failed: %s", exc, exc_info=True)
            self._impl = None
            return False

    def _poll_once(self) -> None:
        if self._impl is not None:
            self._impl.poll_once()

    def set_running(self, running: bool) -> None:
        if self._impl is not None:
            self._impl.update_buttons(running)

    def teardown(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._impl is not None:
            self._impl.teardown()
            self._impl = None
