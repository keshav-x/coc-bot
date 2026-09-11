"""Loot Filter and Search Settings Page for the Qt UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.loot_filter import (
    FILTER_MODES,
    LootFilterConfig,
    LootFilterEngine,
    load_loot_filter_config,
    save_loot_filter_config,
)
from app.services.webhook import (
    WebhookConfig,
    load_webhook_config,
    notify_raid_complete,
    save_webhook_config,
)
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import (
    Card,
    PageTitle,
    SectionTitle,
    ToggleSwitch,
    chip_button,
    neutral_button,
    primary_button,
)


class LootFilterPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._filter_engine = LootFilterEngine()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])
        layout.addWidget(PageTitle("Smart Loot Filter"))

        intro = QLabel(
            "Automatically inspects enemy bases during matchmaking via computer vision and OCR. "
            "Skips bases below your resource criteria until a profitable target is found."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TOKENS['text_muted']};")
        layout.addWidget(intro)

        layout.addWidget(self._build_rules_card())
        layout.addWidget(self._build_thresholds_card())
        layout.addWidget(self._build_webhook_card())
        layout.addStretch()

    def _build_rules_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Match Rules & Budget"))

        self._sw_enabled = ToggleSwitch("Enable Loot Filtration during multiplayer attack search", parent=card)
        card.card_layout.addWidget(self._sw_enabled)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Match condition:"))
        self._combo_mode = QComboBox()
        self._combo_mode.addItems(list(FILTER_MODES))
        mode_row.addWidget(self._combo_mode, stretch=1)
        card.card_layout.addLayout(mode_row)

        skips_row = QHBoxLayout()
        skips_row.addWidget(QLabel("Max skips per search:"))
        self._spin_skips = QSpinBox()
        self._spin_skips.setRange(5, 200)
        self._spin_skips.setValue(40)
        self._spin_skips.setSuffix(" skips")
        skips_row.addWidget(self._spin_skips)
        skips_row.addStretch()
        card.card_layout.addLayout(skips_row)

        return card

    def _build_thresholds_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Minimum Loot Targets"))

        # Gold
        gold_row = QHBoxLayout()
        gold_row.addWidget(QLabel("Min Gold:"), stretch=0)
        self._spin_gold = QSpinBox()
        self._spin_gold.setRange(0, 3000000)
        self._spin_gold.setSingleStep(50000)
        self._spin_gold.setMinimumWidth(120)
        gold_row.addWidget(self._spin_gold)
        for preset in (300000, 500000, 800000, 1000000):
            btn = chip_button(f"{preset // 1000}k", parent=card)
            btn.clicked.connect(lambda _, p=preset: self._spin_gold.setValue(p))
            gold_row.addWidget(btn)
        gold_row.addStretch()
        card.card_layout.addLayout(gold_row)

        # Elixir
        elixir_row = QHBoxLayout()
        elixir_row.addWidget(QLabel("Min Elixir:"), stretch=0)
        self._spin_elixir = QSpinBox()
        self._spin_elixir.setRange(0, 3000000)
        self._spin_elixir.setSingleStep(50000)
        self._spin_elixir.setMinimumWidth(120)
        elixir_row.addWidget(self._spin_elixir)
        for preset in (300000, 500000, 800000, 1000000):
            btn = chip_button(f"{preset // 1000}k", parent=card)
            btn.clicked.connect(lambda _, p=preset: self._spin_elixir.setValue(p))
            elixir_row.addWidget(btn)
        elixir_row.addStretch()
        card.card_layout.addLayout(elixir_row)

        # Dark Elixir
        de_row = QHBoxLayout()
        de_row.addWidget(QLabel("Min Dark Elixir:"), stretch=0)
        self._spin_de = QSpinBox()
        self._spin_de.setRange(0, 30000)
        self._spin_de.setSingleStep(500)
        self._spin_de.setMinimumWidth(120)
        de_row.addWidget(self._spin_de)
        for preset in (2000, 4000, 6000, 10000):
            btn = chip_button(f"{preset // 1000}k", parent=card)
            btn.clicked.connect(lambda _, p=preset: self._spin_de.setValue(p))
            de_row.addWidget(btn)
        de_row.addStretch()
        card.card_layout.addLayout(de_row)

        # Save actions
        btn_row = QHBoxLayout()
        self._btn_save = primary_button("Save Loot Filter", parent=card)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_reset = neutral_button("Reset Defaults", parent=card)
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        card.card_layout.addLayout(btn_row)

        return card

    def _build_webhook_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Discord Mobile Alerts"))

        self._sw_webhook = ToggleSwitch("Enable Discord Webhook push notifications", parent=card)
        card.card_layout.addWidget(self._sw_webhook)

        row = QHBoxLayout()
        row.addWidget(QLabel("Webhook URL:"))
        self._edit_webhook = QLineEdit()
        self._edit_webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        row.addWidget(self._edit_webhook, stretch=1)

        test_btn = neutral_button("Send Test", parent=card)
        test_btn.clicked.connect(self._send_test_webhook)
        row.addWidget(test_btn)
        card.card_layout.addLayout(row)

        return card

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_settings()

    def _reload_settings(self) -> None:
        cfg = load_loot_filter_config()
        self._sw_enabled.setChecked(cfg.enabled)
        idx = self._combo_mode.findText(cfg.filter_mode)
        if idx >= 0:
            self._combo_mode.setCurrentIndex(idx)
        self._spin_skips.setValue(cfg.max_skips)
        self._spin_gold.setValue(cfg.min_gold)
        self._spin_elixir.setValue(cfg.min_elixir)
        self._spin_de.setValue(cfg.min_dark_elixir)

        wh = load_webhook_config()
        self._sw_webhook.setChecked(wh.enabled)
        self._edit_webhook.setText(wh.url)

    def _on_save(self) -> None:
        cfg = LootFilterConfig(
            enabled=self._sw_enabled.isChecked(),
            min_gold=self._spin_gold.value(),
            min_elixir=self._spin_elixir.value(),
            min_dark_elixir=self._spin_de.value(),
            filter_mode=self._combo_mode.currentText(),
            max_skips=self._spin_skips.value(),
        )
        save_loot_filter_config(cfg)
        self._filter_engine.reload_config()

        wh = WebhookConfig(
            enabled=self._sw_webhook.isChecked(),
            url=self._edit_webhook.text().strip(),
            notify_on_raid=True,
            notify_on_break=True,
            notify_on_stop=True,
        )
        save_webhook_config(wh)

        QMessageBox.information(self.window(), "Settings Saved", "Loot filter and Discord webhook settings saved successfully.")

    def _on_reset(self) -> None:
        default_cfg = LootFilterConfig()
        save_loot_filter_config(default_cfg)
        self._reload_settings()

    def _send_test_webhook(self) -> None:
        wh = WebhookConfig(
            enabled=True,
            url=self._edit_webhook.text().strip(),
        )
        save_webhook_config(wh)
        if not wh.url:
            QMessageBox.warning(self.window(), "Missing URL", "Please enter a valid Discord webhook URL.")
            return
        notify_raid_complete(750000, 680000, 4200, 12)
        QMessageBox.information(self.window(), "Test Sent", "A test notification was dispatched to your Discord channel.")
