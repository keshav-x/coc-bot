"""Intelligent Anti-Ban Suite Settings Page for the Qt UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.services.antiban import (
    PROFILE_BALANCED,
    PROFILE_FAST,
    PROFILE_OPTIONS,
    PROFILE_STEALTH,
    AntiBanConfig,
    AntiBanService,
    load_antiban_config,
    save_antiban_config,
)
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import (
    Card,
    PageTitle,
    SectionTitle,
    ToggleSwitch,
    neutral_button,
    primary_button,
)


class AntiBanPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._antiban = AntiBanService()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])
        layout.addWidget(PageTitle("Intelligent Anti-Ban Suite"))

        intro = QLabel(
            "Multi-layered behavioral humanization designed to disguise bot interactions as natural player habits. "
            "Simulates physiological hand jitter, Bezier wrist curves, natural click hold dwell times, and periodic fatigue breaks."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TOKENS['text_muted']};")
        layout.addWidget(intro)

        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_breaks_card())
        layout.addWidget(self._build_kinematics_card())
        layout.addStretch()

    def _build_profile_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Humanization Profile"))

        row = QHBoxLayout()
        row.addWidget(QLabel("Protection Mode:"))
        self._combo_profile = QComboBox()
        self._combo_profile.addItems(list(PROFILE_OPTIONS))
        self._combo_profile.currentTextChanged.connect(self._on_profile_changed)
        row.addWidget(self._combo_profile, stretch=1)
        card.card_layout.addLayout(row)

        self._profile_desc = QLabel("")
        self._profile_desc.setWordWrap(True)
        self._profile_desc.setStyleSheet(f"color: {TOKENS['text_muted']}; font-style: italic;")
        card.card_layout.addWidget(self._profile_desc)
        self._update_profile_desc(PROFILE_BALANCED)

        return card

    def _build_breaks_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Fatigue & Human Breaks"))

        self._sw_breaks = ToggleSwitch("Enable Periodic Human Breaks (breaks 24/7 robotic patterns)", parent=card)
        card.card_layout.addWidget(self._sw_breaks)

        row = QHBoxLayout()
        row.addWidget(QLabel("Farm interval before break:"))
        self._spin_session_min = QSpinBox()
        self._spin_session_min.setRange(15, 120)
        self._spin_session_min.setSuffix(" min")
        row.addWidget(self._spin_session_min)

        row.addWidget(QLabel("to"))
        self._spin_session_max = QSpinBox()
        self._spin_session_max.setRange(20, 180)
        self._spin_session_max.setSuffix(" min")
        row.addWidget(self._spin_session_max)
        row.addStretch()
        card.card_layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Break rest duration:"))
        self._spin_break_min = QSpinBox()
        self._spin_break_min.setRange(1, 30)
        self._spin_break_min.setSuffix(" min")
        row2.addWidget(self._spin_break_min)

        row2.addWidget(QLabel("to"))
        self._spin_break_max = QSpinBox()
        self._spin_break_max.setRange(2, 60)
        self._spin_break_max.setSuffix(" min")
        row2.addWidget(self._spin_break_max)
        row2.addStretch()
        card.card_layout.addLayout(row2)

        return card

    def _build_kinematics_card(self) -> Card:
        card = Card()
        card.card_layout.addWidget(SectionTitle("Kinematics & Rate Limiting"))

        self._sw_curves = ToggleSwitch("Natural Cubic Bezier curves with micro-tremors (hand jitter)", parent=card)
        card.card_layout.addWidget(self._sw_curves)

        self._sw_idle = ToggleSwitch("Simulate occasional human base inspection (nudge camera/village)", parent=card)
        card.card_layout.addWidget(self._sw_idle)

        self._sw_random_clicks = ToggleSwitch("Random Click Offsets (randomized coordinate scatter / jitter)", parent=card)
        card.card_layout.addWidget(self._sw_random_clicks)

        apm_row = QHBoxLayout()
        apm_row.addWidget(QLabel("Max Actions Per Minute (APM limit):"))
        self._spin_apm = QSpinBox()
        self._spin_apm.setRange(60, 300)
        self._spin_apm.setSuffix(" APM")
        apm_row.addWidget(self._spin_apm)
        apm_row.addStretch()
        card.card_layout.addLayout(apm_row)

        # Save / Reset buttons
        btn_row = QHBoxLayout()
        self._btn_save = primary_button("Save Anti-Ban Settings", parent=card)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_reset = neutral_button("Reset Recommended", parent=card)
        self._btn_reset.clicked.connect(self._on_reset)
        btn_row.addWidget(self._btn_reset)
        btn_row.addStretch()
        card.card_layout.addLayout(btn_row)

        return card

    def _on_profile_changed(self, profile: str) -> None:
        self._update_profile_desc(profile)
        if profile == PROFILE_STEALTH:
            self._spin_session_min.setValue(20)
            self._spin_session_max.setValue(35)
            self._spin_break_min.setValue(3)
            self._spin_break_max.setValue(6)
            self._spin_apm.setValue(120)
            self._sw_curves.setChecked(True)
            self._sw_idle.setChecked(True)
        elif profile == PROFILE_BALANCED:
            self._spin_session_min.setValue(25)
            self._spin_session_max.setValue(45)
            self._spin_break_min.setValue(2)
            self._spin_break_max.setValue(5)
            self._spin_apm.setValue(160)
            self._sw_curves.setChecked(True)
            self._sw_idle.setChecked(True)
        elif profile == PROFILE_FAST:
            self._spin_session_min.setValue(45)
            self._spin_session_max.setValue(75)
            self._spin_break_min.setValue(1)
            self._spin_break_max.setValue(3)
            self._spin_apm.setValue(220)

    def _update_profile_desc(self, profile: str) -> None:
        if profile == PROFILE_STEALTH:
            self._profile_desc.setText("Stealth: Maximum human imitation. High curvature, frequent rest pauses, low APM. Ideal for valuable accounts.")
        elif profile == PROFILE_BALANCED:
            self._profile_desc.setText("Balanced: Optimal balance between farming efficiency and human randomness. Recommended for daily use.")
        else:
            self._profile_desc.setText("Fast: Higher throughput with minimal pauses. Prioritizes speed over stealth.")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload_settings()

    def _reload_settings(self) -> None:
        cfg = load_antiban_config()
        idx = self._combo_profile.findText(cfg.profile)
        if idx >= 0:
            self._combo_profile.setCurrentIndex(idx)
        self._sw_breaks.setChecked(cfg.breaks_enabled)
        self._spin_session_min.setValue(cfg.min_session_mins)
        self._spin_session_max.setValue(cfg.max_session_mins)
        self._spin_break_min.setValue(cfg.min_break_mins)
        self._spin_break_max.setValue(cfg.max_break_mins)
        self._sw_curves.setChecked(cfg.human_curves_enabled)
        self._sw_idle.setChecked(cfg.idle_inspection_enabled)
        self._sw_random_clicks.setChecked(cfg.random_clicks_enabled)
        self._spin_apm.setValue(cfg.max_apm)
        self._update_profile_desc(cfg.profile)

    def _on_save(self) -> None:
        cfg = AntiBanConfig(
            profile=self._combo_profile.currentText(),
            breaks_enabled=self._sw_breaks.isChecked(),
            min_session_mins=self._spin_session_min.value(),
            max_session_mins=self._spin_session_max.value(),
            min_break_mins=self._spin_break_min.value(),
            max_break_mins=self._spin_break_max.value(),
            human_curves_enabled=self._sw_curves.isChecked(),
            idle_inspection_enabled=self._sw_idle.isChecked(),
            random_clicks_enabled=self._sw_random_clicks.isChecked(),
            max_apm=self._spin_apm.value(),
        )
        save_antiban_config(cfg)
        self._antiban.reload_config()
        QMessageBox.information(self.window(), "Settings Saved", "Anti-Ban protection settings updated successfully.")

    def _on_reset(self) -> None:
        default_cfg = AntiBanConfig()
        save_antiban_config(default_cfg)
        self._reload_settings()
