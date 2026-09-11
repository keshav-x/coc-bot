"""PySide6 GUI entry point."""

from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from app.ui.qt.branding import apply_app_icon
from app.ui.qt.main_window import MainWindow
from app.ui.qt.theme import apply_theme


def run_gui() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Clash AutoLoot")
    apply_app_icon(app)
    apply_theme(app)
    window = MainWindow()
    apply_app_icon(window)
    window.show()
    sys.exit(app.exec())
