"""Settings page — profile preferences and manual game-window selection."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config import resolve_aspect_key
from app.services.webhook import (
    WebhookConfig,
    load_webhook_config,
    save_webhook_config,
    notify_bot_started,
)
from app.services.window import DescendantInfo, WindowCandidate, WindowService
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import (
    Card,
    PageTitle,
    SectionTitle,
    ToggleSwitch,
    neutral_button,
    primary_button,
)
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import (
    EARTHQUAKE_METHOD_OPTIONS,
    ProfileSettings,
    load_profile_settings,
    save_profile_settings,
)
from app.utils.window_settings_store import (
    clear_window_selection,
    load_window_selection,
    save_window_selection,
)

logger = setup_logger("SettingsPage")


class WindowInfoDialog(QDialog):
    """Inspect all child hwnds of a top-level window to diagnose capture targets."""

    def __init__(
        self,
        parent: Optional[QWidget],
        candidate: WindowCandidate,
        descendants: List[DescendantInfo],
    ):
        super().__init__(parent)
        self.setWindowTitle("Window info")
        self.setModal(True)
        self.resize(640, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["sm"])

        header = QLabel(
            f"Top-level: {candidate.title or '(no title)'}\nClass: {candidate.top_class}    hwnd={candidate.top_hwnd}"
        )
        header.setWordWrap(True)
        header.setStyleSheet(f"color: {TOKENS['text']};")
        layout.addWidget(header)

        count = len(descendants)
        surfaces = sum(1 for d in descendants if d.is_surface)
        summary = QLabel(
            f"{count} child window(s), {surfaces} game surface(s). Surfaces are marked [surface]."
        )
        summary.setStyleSheet(f"color: {TOKENS['text_muted']};")
        layout.addWidget(summary)

        listing = QListWidget()
        listing.setObjectName("WindowInfoList")
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        listing.setFont(mono)
        if descendants:
            for d in descendants:
                item = QListWidgetItem(d.display_label())
                if d.is_surface:
                    item.setForeground(QColor(TOKENS["primary"]))
                listing.addItem(item)
        else:
            listing.addItem(QListWidgetItem("No child windows found under this window."))
        layout.addWidget(listing, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = neutral_button("Close", parent=self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class SettingsPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._candidates: List[WindowCandidate] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])
        layout.addWidget(PageTitle("Settings"))

        layout.addWidget(self._build_earthquake_card())
        layout.addWidget(self._build_webhook_card())
        layout.addWidget(self._build_window_card())
        layout.addStretch()

    def _build_webhook_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Discord Webhook Alerts"))

        hint = QLabel("Receive instant notifications on Discord for completed raids, anti-ban breaks, and bot events.")
        hint.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 12px;")
        card.card_layout.addWidget(hint)

        cfg = load_webhook_config()

        top_row = QHBoxLayout()
        self._webhook_switch = ToggleSwitch(parent=card)
        self._webhook_switch.setChecked(cfg.enabled)
        top_row.addWidget(QLabel("Enable Discord Notifications"))
        top_row.addStretch()
        top_row.addWidget(self._webhook_switch)
        card.card_layout.addLayout(top_row)

        self._webhook_url = QLineEdit(cfg.url)
        self._webhook_url.setPlaceholderText("https://discord.com/api/webhooks/...")
        card.card_layout.addWidget(self._webhook_url)

        opts_row = QHBoxLayout()
        self._cb_raid = QCheckBox("Raid summaries")
        self._cb_raid.setChecked(cfg.notify_on_raid)
        self._cb_break = QCheckBox("Anti-Ban breaks")
        self._cb_break.setChecked(cfg.notify_on_break)
        self._cb_stop = QCheckBox("Bot stops / errors")
        self._cb_stop.setChecked(cfg.notify_on_stop)
        opts_row.addWidget(self._cb_raid)
        opts_row.addWidget(self._cb_break)
        opts_row.addWidget(self._cb_stop)
        opts_row.addStretch()
        card.card_layout.addLayout(opts_row)

        btn_row = QHBoxLayout()
        self._btn_save_webhook = primary_button("Save Webhook", parent=card)
        self._btn_save_webhook.clicked.connect(self._on_save_webhook)
        btn_row.addWidget(self._btn_save_webhook)

        self._btn_test_webhook = neutral_button("Send Test Ping", parent=card)
        self._btn_test_webhook.clicked.connect(self._on_test_webhook)
        btn_row.addWidget(self._btn_test_webhook)
        btn_row.addStretch()
        card.card_layout.addLayout(btn_row)

        return card

    def _on_save_webhook(self) -> None:
        cfg = WebhookConfig(
            enabled=self._webhook_switch.isChecked(),
            url=self._webhook_url.text().strip(),
            notify_on_raid=self._cb_raid.isChecked(),
            notify_on_break=self._cb_break.isChecked(),
            notify_on_stop=self._cb_stop.isChecked(),
        )
        save_webhook_config(cfg)
        self._flash_status_bar("Webhook Settings Saved")

    def _on_test_webhook(self) -> None:
        url = self._webhook_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a Discord webhook URL first.")
            return
        cfg = WebhookConfig(
            enabled=True,
            url=url,
            notify_on_raid=True,
            notify_on_break=True,
            notify_on_stop=True,
        )
        save_webhook_config(cfg)
        notify_bot_started("Test Ping from ApexClash Pro Settings")
        QMessageBox.information(
            self,
            "Ping Sent",
            "A test notification embed was dispatched to your Discord channel. Check Discord!",
        )

    def _build_earthquake_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Earthquake placement"))
        self._earthquake = QComboBox()
        self._earthquake.addItems(list(EARTHQUAKE_METHOD_OPTIONS))
        card.card_layout.addWidget(self._earthquake)

        btn_row = QHBoxLayout()
        self._btn_save = primary_button("Save", parent=card)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_reset = neutral_button("Reset", parent=card)
        self._btn_reset.clicked.connect(self._reload_earthquake)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        card.card_layout.addLayout(btn_row)
        return card

    def _build_window_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Game window"))

        hint = QLabel(
            "If the bot can't find Clash of Clans, pick the Google Play Games window below and "
            "press Test. Windows with a game surface are listed first."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TOKENS['text_muted']};")
        card.card_layout.addWidget(hint)

        self._window_list = QListWidget()
        self._window_list.setObjectName("WindowList")
        self._window_list.setMinimumHeight(140)
        self._window_list.currentRowChanged.connect(lambda _: self._update_window_buttons())
        card.card_layout.addWidget(self._window_list)

        self._window_status = QLabel("")
        self._window_status.setWordWrap(True)
        self._window_status.setStyleSheet(f"color: {TOKENS['text_muted']};")
        card.card_layout.addWidget(self._window_status)

        row = QHBoxLayout()
        self._btn_refresh = neutral_button("Refresh", parent=card)
        self._btn_refresh.clicked.connect(self._refresh_windows)
        row.addWidget(self._btn_refresh)

        self._btn_test = neutral_button("Test", parent=card)
        self._btn_test.clicked.connect(self._on_test_window)
        row.addWidget(self._btn_test)

        self._btn_info = neutral_button("Info", parent=card)
        self._btn_info.clicked.connect(self._on_window_info)
        row.addWidget(self._btn_info)

        self._btn_use = primary_button("Use this window", parent=card)
        self._btn_use.clicked.connect(self._on_use_window)
        row.addWidget(self._btn_use)

        row.addStretch()

        self._btn_auto = neutral_button("Auto-detect", parent=card)
        self._btn_auto.clicked.connect(self._on_auto_detect)
        row.addWidget(self._btn_auto)

        card.card_layout.addLayout(row)
        return card

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_earthquake()
        self._refresh_windows()

    def _reload_earthquake(self) -> None:
        settings = load_profile_settings()
        idx = self._earthquake.findText(settings.earthquake_method)
        if idx >= 0:
            self._earthquake.setCurrentIndex(idx)

    def _on_save(self) -> None:
        save_profile_settings(
            ProfileSettings(earthquake_method=self._earthquake.currentText())
        )
        self._flash_status_bar("Saved")

    def _selected_candidate(self) -> Optional[WindowCandidate]:
        row = self._window_list.currentRow()
        if 0 <= row < len(self._candidates):
            return self._candidates[row]
        return None

    def _update_window_buttons(self) -> None:
        has_sel = self._selected_candidate() is not None
        self._btn_test.setEnabled(has_sel)
        self._btn_use.setEnabled(has_sel)
        self._btn_info.setEnabled(has_sel)

    def _refresh_windows(self) -> None:
        try:
            self._candidates = WindowService().enumerate_windows()
        except Exception as exc:
            logger.warning(f"Could not enumerate windows: {exc}")
            self._candidates = []

        saved = load_window_selection()
        self._window_list.clear()
        selected_row = -1

        for i, cand in enumerate(self._candidates):
            item = QListWidgetItem(cand.display_label())
            if not cand.is_game:
                item.setForeground(self._muted_brush())
            self._window_list.addItem(item)
            if saved.is_set():
                if cand.title.strip().lower() == saved.title.strip().lower():
                    if not saved.top_class or cand.top_class == saved.top_class:
                        selected_row = i

        if selected_row >= 0:
            self._window_list.setCurrentRow(selected_row)

        if not self._candidates:
            self._window_status.setText("No visible windows found. Open the game, then Refresh.")
        elif saved.is_set():
            self._window_status.setText(f"Pinned window: {saved.title or '(saved)'}")
        else:
            self._window_status.setText("Using auto-detect.")

        self._update_window_buttons()

    def _muted_brush(self) -> QColor:
        return QColor(TOKENS["text_muted"])

    @staticmethod
    def _aspect_label(w: int, h: int) -> str:
        if not w or not h:
            return "size unavailable"
        aspect = resolve_aspect_key(w, h)
        if aspect is None:
            return f"{w}x{h} (not ~16:9/16:10)"
        pretty = "16:9" if aspect == "16_9" else "16:10"
        return f"{w}x{h} ({pretty})"

    def _on_test_window(self) -> None:
        cand = self._selected_candidate()
        if cand is None:
            return
        if not cand.is_game:
            self._window_status.setText(
                "No Google Play Games surface (CROSVM) under this window — pick the game window."
            )
            return
        ws = WindowService()
        surface_size = ws.window_pixel_size(cand.child_hwnd)
        if surface_size is None:
            self._window_status.setText(
                "Could not read the window size. Is the game minimized?"
            )
            return

        sub_size = None
        try:
            for d in ws.enumerate_descendants(cand.top_hwnd):
                if d.cls.lower() == "subwin":
                    sub_size = (d.width, d.height)
                    break
        except Exception as exc:
            logger.warning(f"Could not inspect subWin: {exc}")

        sw, sh = surface_size
        lines = [f"Capture target {cand.child_class}: {self._aspect_label(sw, sh)}"]
        if sub_size is not None:
            lines.append(f"Inner subWin: {self._aspect_label(*sub_size)}")
        if resolve_aspect_key(sw, sh) is None:
            lines.append("Surface aspect unsupported — try resizing the game window.")
        else:
            lines.append("Surface OK to use.")
        self._window_status.setText("\n".join(lines))

    def _on_window_info(self) -> None:
        cand = self._selected_candidate()
        if cand is None:
            return
        try:
            descendants = WindowService().enumerate_descendants(cand.top_hwnd)
        except Exception as exc:
            logger.warning(f"Could not enumerate descendants: {exc}")
            descendants = []
        WindowInfoDialog(self.window(), cand, descendants).exec()

    def _on_use_window(self) -> None:
        cand = self._selected_candidate()
        if cand is None:
            return
        save_window_selection(cand.to_selection())
        self._window_status.setText(f"Pinned: {cand.title or '(no title)'}. Press Test to verify.")
        self._flash_status_bar("Window saved")

    def _on_auto_detect(self) -> None:
        clear_window_selection()
        self._window_status.setText("Cleared — using auto-detect.")
        self._flash_status_bar("Auto-detect")
        self._refresh_windows()

    def _flash_status_bar(self, msg: str) -> None:
        win = self.window()
        if isinstance(win, QMainWindow) and win.statusBar() is not None:
            win.statusBar().showMessage(msg, 1500)
