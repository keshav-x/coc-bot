"""Main application window — sidebar shell."""
from __future__ import annotations

import platform
import sys

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.services.license import LicenseState
from app.services.notifications import set_system_tray
from app.ui.qt.branding import apply_app_icon, logo_pixmap
from app.ui.qt.bot_controller import BotController
from app.ui.qt.dialogs import show_error
from app.ui.qt.pages.antiban_page import AntiBanPage
from app.ui.qt.pages.license import LicensePage
from app.ui.qt.pages.logs import LogsPage
from app.ui.qt.pages.loot_filter_page import LootFilterPage
from app.ui.qt.pages.players import PlayersPage
from app.ui.qt.pages.run import RunPage
from app.ui.qt.pages.settings import SettingsPage
from app.ui.qt.taskbar_thumb_qt import QtTaskbarThumb
from app.ui.qt.theme import SIDEBAR_WIDTH, TOKENS, WINDOW_DEFAULT, WINDOW_MIN
from app.ui.qt.widgets import (
    DOT_COLORS,
    StatusDot,
    TrialBannerWidget,
    format_license_expires_on_line,
    format_trial_expires_in_minutes,
)

PAGE_KEYS = ["run", "loot_filter", "antiban", "settings", "players", "license", "logs"]
PAGE_LABELS = ["Cockpit", "Loot Filter", "Anti-Ban", "Settings", "Players", "License", "Logs"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clash AutoLoot Bot")
        self.resize(*WINDOW_DEFAULT)
        self.setMinimumSize(*WINDOW_MIN)

        self._settings = QSettings("ClashAutoLoot", "UI")
        self._controller = BotController(bot_version=__version__)
        self._taskbar = None
        self._taskbar_setup_attempts = 0
        self._taskbar_setup_done = False

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar_panel = QWidget()
        sidebar_panel.setFixedWidth(SIDEBAR_WIDTH)
        sidebar_col = QVBoxLayout(sidebar_panel)
        sidebar_col.setContentsMargins(12, 16, 12, 8)
        sidebar_col.setSpacing(8)

        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(logo_pixmap(48))
        sidebar_col.addWidget(logo)

        brand = QLabel("Clash AutoLoot")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(f"font-weight: bold; color: {TOKENS['text']};")
        sidebar_col.addWidget(brand)

        self._sidebar = QListWidget()
        self._sidebar.setObjectName("Sidebar")
        for label in PAGE_LABELS:
            QListWidgetItem(label, self._sidebar)
        self._sidebar.setCurrentRow(0)
        sidebar_col.addWidget(self._sidebar, stretch=1)

        self._trial_banner = TrialBannerWidget()
        sidebar_col.addWidget(self._trial_banner)
        root.addWidget(sidebar_panel)

        self._stack = QStackedWidget()
        self._run_page = RunPage(self._controller, self.navigate_to)
        self._loot_filter_page = LootFilterPage()
        self._antiban_page = AntiBanPage()
        self._settings_page = SettingsPage()
        self._players_page = PlayersPage()
        self._license_page = LicensePage(self._controller)
        self._logs_page = LogsPage()

        for page in (
            self._run_page,
            self._loot_filter_page,
            self._antiban_page,
            self._settings_page,
            self._players_page,
            self._license_page,
            self._logs_page,
        ):
            self._stack.addWidget(page)
        root.addWidget(self._stack, stretch=1)

        self._build_status_bar()
        self._wire_signals()
        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._restore_geometry()
        self._controller.prime()

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)

        status_host = QWidget()
        status_layout = QHBoxLayout(status_host)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self._lic_dot = StatusDot()
        status_layout.addWidget(self._lic_dot)

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet(f"color: {TOKENS['text_muted']};")
        status_layout.addWidget(self._status_label)

        bar.addWidget(status_host, stretch=1)

        self._expiry_label = QLabel("")
        self._expiry_label.setStyleSheet(f"color: {TOKENS['text_muted']};")
        bar.addPermanentWidget(self._expiry_label)

        version_lbl = QLabel(f"v{__version__}")
        version_lbl.setStyleSheet(f"color: {TOKENS['text_muted']};")
        bar.addPermanentWidget(version_lbl)

    def _wire_signals(self) -> None:
        self._controller.statusChanged.connect(self._on_status)
        self._controller.botStarted.connect(self._on_bot_started_status)
        self._controller.botFinished.connect(self._on_bot_finished)
        self._controller.licenseChanged.connect(self._on_license_changed)
        self._controller.trialUpdated.connect(self._on_trial_updated)
        self._controller.licenseRevoked.connect(self._on_license_revoked)
        self._controller.trialExpired.connect(self._on_trial_expired)
        self._controller.runningChanged.connect(self._on_running_changed)

    def navigate_to(self, page_key: str) -> None:
        if page_key in PAGE_KEYS:
            self._sidebar.setCurrentRow(PAGE_KEYS.index(page_key))

    def _restore_geometry(self) -> None:
        geo = self._settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = self._settings.value("windowState")
        if state is not None:
            self.restoreState(state)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._taskbar_setup_done:
            QTimer.singleShot(500, self._setup_taskbar_thumb)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._controller.is_running():
            self._controller.stop()
        self._controller.flush_trial_heartbeat()
        if self._taskbar is not None:
            self._taskbar.teardown()
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        event.accept()

    def _setup_taskbar_thumb(self) -> None:
        if self._taskbar_setup_done or platform.system() != "Windows":
            return
        try:
            self._taskbar = QtTaskbarThumb(self._controller, self._run_page, parent=self)
            if self._taskbar.setup(self):
                self._taskbar.set_running(self._controller.is_running())
                self._taskbar_setup_done = True
            else:
                self._taskbar = None
        except Exception:
            self._taskbar = None

    def _on_status(self, msg: str, warning: bool) -> None:
        color = TOKENS["danger"] if warning else TOKENS["text_muted"]
        self._status_label.setText(msg)
        self._status_label.setStyleSheet(f"color: {color};")

    def _on_bot_started_status(self) -> None:
        if self._run_page.is_star_bonus_enabled():
            self._status_label.setText("Star Bonus...")
        else:
            self._status_label.setText("Running...")
        self._status_label.setStyleSheet(f"color: {TOKENS['text_muted']};")

    def _on_bot_finished(self, error_msg: Optional[str] = None) -> None:
        self._controller.on_bot_finished()
        if self._taskbar is not None:
            self._taskbar.set_running(False)
        if error_msg:
            preview = error_msg[:50] + "..." if len(error_msg) > 50 else error_msg
            self._status_label.setText(f"Error: {preview}")
            self._status_label.setStyleSheet(f"color: {TOKENS['danger']};")
            show_error(self, "Error", str(error_msg))
            return
        self._status_label.setText("Stopped")
        self._status_label.setStyleSheet(f"color: {TOKENS['text_muted']};")
        if sys.platform == "win32":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass

    def _on_running_changed(self, running: bool) -> None:
        if self._taskbar is not None:
            self._taskbar.set_running(running)

    def _on_license_changed(self, state: LicenseState, reason: str) -> None:
        self._controller.handle_license_state_on_main_thread(state, reason)
        self._lic_dot.set_color(DOT_COLORS.get(state, TOKENS["danger"]))
        self._update_expiry_strip()

    def _on_trial_updated(self, result) -> None:
        if self._controller.license_state() == LicenseState.VALID:
            return
        self._update_expiry_strip()

    def _update_expiry_strip(self) -> None:
        state = self._controller.license_state()
        rs = self._controller.trial_remaining_seconds()
        self._trial_banner.update_status(state, rs)
        if state == LicenseState.VALID:
            sub_raw = self._controller.license_expiry_subcaption()
            line = format_license_expires_on_line(sub_raw) if sub_raw else ""
            self._expiry_label.setText(line)
            self._expiry_label.setVisible(bool(line))
            return
        if rs is not None and rs > 0:
            self._expiry_label.setText(format_trial_expires_in_minutes(rs))
            self._expiry_label.setVisible(True)
            return
        self._expiry_label.setText("")
        self._expiry_label.setVisible(False)

    def _on_license_revoked(self, msg: str) -> None:
        show_error(self, "License Revoked", f"The bot has been stopped.\n\n{msg}")

    def _on_trial_expired(self) -> None:
        QMessageBox.warning(
            self,
            "Trial expired",
            "Your free trial time has run out. The bot has been stopped.\n\nPurchase a license key to continue using the bot.",
        )
