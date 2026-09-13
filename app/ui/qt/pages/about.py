"""About page — ApexClash Pro features, Anti-Ban technology, and developer contacts."""
from __future__ import annotations

import platform
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.ui.qt.branding import APP_NAME, APP_SUBTITLE, logo_pixmap
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import Card, PageTitle, SectionTitle


class AboutPage(QWidget):
    """About ApexClash Pro, highlighting Anti-Ban safety, features, and support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"])
        layout.setSpacing(SPACING["md"])

        # Page Header
        layout.addWidget(PageTitle("About ApexClash Pro"))

        # Brand Hero Card
        hero_card = Card()
        hero_layout = QHBoxLayout()
        hero_layout.setSpacing(SPACING["lg"])

        logo_lbl = QLabel()
        pix = logo_pixmap(72)
        if not pix.isNull():
            logo_lbl.setPixmap(pix)
        hero_layout.addWidget(logo_lbl)

        hero_text_col = QVBoxLayout()
        hero_text_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_lbl = QLabel(APP_NAME)
        title_lbl.setStyleSheet(f"color: {TOKENS['accent_cyan']}; font-size: 22px; font-weight: bold;")
        title_row.addWidget(title_lbl)

        ver_badge = QLabel(f"v{__version__} PRO")
        ver_badge.setStyleSheet(
            f"background-color: {TOKENS['surface_hi']}; color: {TOKENS['accent_gold']}; "
            f"border: 1px solid {TOKENS['border_hi']}; padding: 3px 8px; border-radius: 4px; "
            f"font-size: 11px; font-weight: bold;"
        )
        title_row.addWidget(ver_badge)
        title_row.addStretch()
        hero_text_col.addLayout(title_row)

        subtitle_lbl = QLabel(APP_SUBTITLE)
        subtitle_lbl.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        hero_text_col.addWidget(subtitle_lbl)

        desc_lbl = QLabel(
            "ApexClash Pro is an elite autonomous farming and base-stripping suite engineered specifically "
            "for Clash of Clans. Built with state-of-the-art computer vision and humanized behavioral physics, "
            "it delivers unstoppable 24/7 farming velocity with maximum account safety."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {TOKENS['text']}; font-size: 13px; line-height: 1.5; margin-top: 4px;")
        hero_text_col.addWidget(desc_lbl)

        hero_layout.addLayout(hero_text_col, stretch=1)
        hero_card.card_layout.addLayout(hero_layout)
        layout.addWidget(hero_card)

        # Anti-Ban Engine 3.0 Card (Featured Pillar)
        antiban_card = Card()
        antiban_card.card_layout.addWidget(SectionTitle("🛡️ Humanized Anti-Ban Engine 3.0"))
        
        antiban_desc = QLabel(
            "<b>100% External Vision (Zero Memory Injection):</b><br>"
            "Unlike unsafe bots that inject into game processes or modify files, ApexClash Pro operates completely "
            "externally using computer vision (OpenCV) and optical character recognition (Tesseract). It never reads, "
            "hooks, or modifies game memory, making it completely undetectable to internal client integrity checks.<br><br>"
            "<b>Key Anti-Ban Protections:</b><br>"
            "• <b>Bézier Curve Mouse Physics:</b> Every swipe, tap, and drag follows organic, non-linear acceleration curves with micro-jitter.<br>"
            "• <b>Gaussian Coordinate Scatter:</b> Randomized tap offsets guarantee no two clicks land on the same pixel.<br>"
            "• <b>Circadian Rest Cycles:</b> Automated human fatigue breaks simulate real player rest and sleep intervals.<br>"
            "• <b>Erratic Timing Delays:</b> Randomized variable delays between base scans prevent robotic timing signatures."
        )
        antiban_desc.setTextFormat(Qt.TextFormat.RichText)
        antiban_desc.setWordWrap(True)
        antiban_desc.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.6;")
        antiban_card.card_layout.addWidget(antiban_desc)
        layout.addWidget(antiban_card)

        # Core Features Card
        features_card = Card()
        features_card.card_layout.addWidget(SectionTitle("⚡ Feature Highlights"))
        features_text = QLabel(
            "• <b>Surgical Sneaky Goblin Farming:</b> High-efficiency funneling that strips collectors and mines with minimal troop cost.<br>"
            "• <b>Smart OCR Loot Filtration:</b> Real-time base scan filters for gold, elixir, and dark elixir thresholds with instant skips.<br>"
            "• <b>Autonomous Wall Upgrader:</b> Prevents resource waste by automatically sinking excess gold & elixir into wall upgrades.<br>"
            "• <b>Tactical Hero Ability Timing:</b> Deploys King, Queen, Warden, and Champion with delayed ability activation.<br>"
            "• <b>Discord Webhooks:</b> Live raid reports, loot summaries, and status alerts sent straight to your phone.<br>"
            "• <b>Multi-Platform Support:</b> 1-Click native execution on Windows, Linux, and macOS."
        )
        features_text.setTextFormat(Qt.TextFormat.RichText)
        features_text.setWordWrap(True)
        features_text.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.6;")
        features_card.card_layout.addWidget(features_text)
        layout.addWidget(features_card)

        # Pricing & Access Passes Card
        pricing_card = Card()
        pricing_card.card_layout.addWidget(SectionTitle("🔑 Access Passes & Pricing"))
        pricing_text = QLabel(
            "• <b>2-Hour Free Trial:</b> Automatically active on first launch — test everything risk-free.<br>"
            "• <b>Weekly Pass:</b> <b>$1.00</b> (7 Days) — Quick trial & weekend farming.<br>"
            "• <b>Monthly Pass:</b> <b>$3.00</b> (30 Days) — Continuous regular farming.<br>"
            "• <b>Annual Pass:</b> <b>$10.00</b> (365 Days) — High value & all updates included.<br>"
            "• <b>Lifetime Pass:</b> <b>$15.00</b> (Permanent) — Permanent VIP Access with priority support."
        )
        pricing_text.setTextFormat(Qt.TextFormat.RichText)
        pricing_text.setWordWrap(True)
        pricing_text.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.6;")
        pricing_card.card_layout.addWidget(pricing_text)
        layout.addWidget(pricing_card)

        # Developer & Purchase Support Card
        contact_card = Card()
        contact_card.card_layout.addWidget(SectionTitle("💬 Contact & Support"))
        contact_text = QLabel(
            "Reach out directly for purchase activations, questions, or custom setups:<br>"
            "• 📧 <b>Email:</b> <a style='color: #38bdf8;' href='mailto:cockingkeshav@gmail.com'>cockingkeshav@gmail.com</a><br>"
            "• 💬 <b>Discord:</b> <span style='color: #22c55e;'>matrix0456</span><br>"
            "• 🌐 <b>Reddit:</b> <span style='color: #f59e0b;'>u/post_matrix</span><br>"
            "<i>Accepted Payment Methods: PayPal, Crypto (USDT / BTC / LTC), UPI, Cards.</i>"
        )
        contact_text.setTextFormat(Qt.TextFormat.RichText)
        contact_text.setOpenExternalLinks(True)
        contact_text.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.6;")
        contact_card.card_layout.addWidget(contact_text)
        layout.addWidget(contact_card)

        # Environment Details Card
        env_card = Card()
        env_card.card_layout.addWidget(SectionTitle("⚙️ System Environment"))
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        env_text = QLabel(
            f"• <b>OS:</b> {platform.system()} {platform.release()} ({platform.machine()})<br>"
            f"• <b>Python:</b> {py_ver}<br>"
            f"• <b>GUI Framework:</b> PySide6 (Qt6 Modern Aurora Cyber)<br>"
            f"• <b>Status:</b> All subsystems operational"
        )
        env_text.setTextFormat(Qt.TextFormat.RichText)
        env_text.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 11px; line-height: 1.5;")
        env_card.card_layout.addWidget(env_text)
        layout.addWidget(env_card)

        layout.addStretch()
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)
