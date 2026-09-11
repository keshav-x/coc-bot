"""Logs page — tail autoloot.log in the UI."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt.theme import SPACING
from app.ui.qt.widgets import PageTitle, neutral_button
from app.utils.common import get_autoloot_log_path


class LogsPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pos = 0
        self._tail_timer = QTimer(self)
        self._tail_timer.setInterval(1000)
        self._tail_timer.timeout.connect(self._tail_log)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        layout.setSpacing(SPACING["md"])
        layout.addWidget(PageTitle("Logs"))

        btn_row = QHBoxLayout()
        open_btn = neutral_button("Open in Explorer")
        open_btn.clicked.connect(self._open_in_explorer)
        btn_row.addWidget(open_btn)

        clear_btn = neutral_button("Clear view")
        clear_btn.clicked.connect(self._clear_view)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(5000)
        mono = QFont("Courier New", 9)
        self._log_view.setFont(mono)
        layout.addWidget(self._log_view, stretch=1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._pos = 0
        self._tail_log()
        self._tail_timer.start()

    def hideEvent(self, event) -> None:
        self._tail_timer.stop()
        super().hideEvent(event)

    def _tail_log(self) -> None:
        path = get_autoloot_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                path.touch()
            with path.open("rb") as fh:
                fh.seek(self._pos)
                chunk = fh.read()
                self._pos = fh.tell()
            if chunk:
                text = chunk.decode("utf-8", errors="replace")
                self._log_view.moveCursor(QTextCursor.MoveOperation.End)
                self._log_view.insertPlainText(text)
                self._log_view.moveCursor(QTextCursor.MoveOperation.End)
        except OSError:
            pass

    def _clear_view(self) -> None:
        self._log_view.clear()

    def _open_in_explorer(self) -> None:
        path = get_autoloot_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                path.touch()
            if sys.platform == "win32":
                os.startfile(path.parent)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path.parent)], check=False)
            else:
                subprocess.run(["xdg-open", str(path.parent)], check=False)
        except OSError:
            pass
