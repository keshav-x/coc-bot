"""License page — key entry, validation, checkout links."""

from __future__ import annotations

import urllib.parse
import webbrowser
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt.branding import logo_pixmap

from app.services.crypto_license import CryptoLicenseEngine
from app.services.license import LicenseState, load_saved_key
from app.ui.qt._constants import (
    PORTAL_USER_ERRORS,
    STRIPE_LIFETIME_URL,
    SUBSCRIBE_CHECKOUT_URL,
)
from app.ui.qt.bot_controller import BotController
from app.ui.qt.dialogs import UnpairConfirmDialog, show_error
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import (
    Card,
    DOT_COLORS,
    PageTitle,
    SectionTitle,
    StatusDot,
    VisibilityToggleButton,
    primary_button,
    neutral_button,
)


class PurchaseOptionsDialog(QDialog):
    """Rich interactive dialog with live pack selection and branded logo."""

    def __init__(self, parent: Optional[QWidget], machine_id: str, default_tier: str = "Monthly ($3/mo)") -> None:
        super().__init__(parent)
        self.setWindowTitle("ApexClash Pro — Official Store")
        self.setFixedWidth(560)
        self.setStyleSheet(f"background-color: {TOKENS['surface_lo']}; color: {TOKENS['text']};")

        self._machine_id = machine_id
        if "life" in default_tier.lower():
            self._selected_key = "lifetime"
        elif "week" in default_tier.lower():
            self._selected_key = "weekly"
        elif "annu" in default_tier.lower() or "year" in default_tier.lower():
            self._selected_key = "annual"
        else:
            self._selected_key = "monthly"

        self._packs = {
            "weekly": ("Weekly Pass", "$1.00", "7 Days Access", "⚡ Trial"),
            "monthly": ("Monthly Pass", "$3.00", "30 Days Access", "🔥 Popular"),
            "annual": ("Annual Pass", "$10.00", "365 Days Access", "⭐ Best Value"),
            "lifetime": ("Lifetime VIP Pass", "$15.00", "Permanent Access", "👑 VIP Choice"),
        }

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        # Header with Logo
        head_row = QHBoxLayout()
        head_row.setSpacing(14)
        logo_lbl = QLabel()
        pix = logo_pixmap(54)
        if not pix.isNull():
            logo_lbl.setPixmap(pix)
            logo_lbl.setStyleSheet("border-radius: 10px;")
        head_row.addWidget(logo_lbl)

        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        title = QLabel("ApexClash Pro — Official Store")
        title.setStyleSheet("font-size: 17px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;")
        head_text.addWidget(title)
        subtitle = QLabel("SELECT YOUR ACCESS PASS • INSTANT KEY ACTIVATION")
        subtitle.setStyleSheet(f"font-size: 10px; font-weight: 800; color: {TOKENS['primary']}; letter-spacing: 0.5px;")
        head_text.addWidget(subtitle)
        head_row.addLayout(head_text)
        head_row.addStretch()

        badge_live = QLabel("● STORE LIVE")
        badge_live.setStyleSheet(
            f"color: {TOKENS['success']}; background: rgba(16, 185, 129, 0.15); "
            f"border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 12px; "
            f"padding: 4px 10px; font-size: 10px; font-weight: bold;"
        )
        head_row.addWidget(badge_live)
        layout.addLayout(head_row)

        # Interactive Pack Selection Grid
        grid_lbl = QLabel("<b>Choose your pack (click to select):</b>")
        grid_lbl.setTextFormat(Qt.TextFormat.RichText)
        grid_lbl.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px;")
        layout.addWidget(grid_lbl)

        self._pack_buttons: dict[str, QPushButton] = {}
        grid = QGridLayout()
        grid.setSpacing(8)

        keys = ["weekly", "monthly", "annual", "lifetime"]
        for idx, k in enumerate(keys):
            name, price, dur, tag = self._packs[k]
            btn = QPushButton(f"{name}\n{price}  ({dur})\n[{tag}]")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(68)
            btn.clicked.connect(lambda checked=False, key=k: self._on_pack_selected(key))
            self._pack_buttons[k] = btn
            r = idx // 2
            c = idx % 2
            grid.addWidget(btn, r, c)
        layout.addLayout(grid)

        # Selected Pack Summary Card
        self._summary_frame = QFrame()
        self._summary_frame.setStyleSheet(
            f"background-color: {TOKENS['surface_hi']}; border: 1px solid {TOKENS['border_hi']}; "
            f"border-radius: 8px; padding: 10px 14px;"
        )
        sum_layout = QHBoxLayout(self._summary_frame)
        sum_layout.setContentsMargins(10, 8, 10, 8)
        self._sum_lbl_left = QLabel("")
        self._sum_lbl_left.setTextFormat(Qt.TextFormat.RichText)
        self._sum_lbl_left.setStyleSheet("font-size: 12px;")
        sum_layout.addWidget(self._sum_lbl_left, stretch=1)
        self._sum_lbl_price = QLabel("")
        self._sum_lbl_price.setStyleSheet("font-size: 20px; font-weight: 800; color: #38bdf8;")
        sum_layout.addWidget(self._sum_lbl_price)
        layout.addWidget(self._summary_frame)

        # Hardware ID Box
        hw_box = QVBoxLayout()
        hw_box.setSpacing(4)
        hw_lbl = QLabel("<b>Your Device ID</b> (automatically copied to clipboard):")
        hw_lbl.setTextFormat(Qt.TextFormat.RichText)
        hw_lbl.setStyleSheet(f"color: {TOKENS['text']}; font-size: 11px;")
        hw_box.addWidget(hw_lbl)

        hw_row = QHBoxLayout()
        self._hw_input = QLineEdit(machine_id)
        self._hw_input.setReadOnly(True)
        self._hw_input.setFont(QFont("Courier New", 10))
        self._hw_input.setStyleSheet(f"background-color: {TOKENS['neutral_dark']}; color: #38bdf8; padding: 5px 8px; border-radius: 6px;")
        hw_row.addWidget(self._hw_input, stretch=1)

        self._btn_copy_hw = neutral_button("📋 Copy ID", parent=self)
        self._btn_copy_hw.clicked.connect(self._copy_id)
        hw_row.addWidget(self._btn_copy_hw)
        hw_box.addLayout(hw_row)
        layout.addLayout(hw_box)

        # Payment methods note
        pay_note = QLabel(
            "<b>Payment Methods:</b> PayPal, UPI, Crypto (USDT/BTC/LTC), Cards • <b>Instant Key Delivery</b>"
        )
        pay_note.setTextFormat(Qt.TextFormat.RichText)
        pay_note.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 11px;")
        layout.addWidget(pay_note)

        # Copy Device ID right away when dialog opens
        QGuiApplication.clipboard().setText(machine_id)

        # Action Buttons
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        row_actions = QHBoxLayout()
        row_actions.setSpacing(8)

        self._btn_portal = primary_button("🌐 Open Web Store (Interactive)", parent=self)
        self._btn_portal.clicked.connect(self._open_portal)
        row_actions.addWidget(self._btn_portal)

        self._btn_gmail = primary_button("📧 Open in Gmail", parent=self)
        self._btn_gmail.clicked.connect(self._open_gmail)
        row_actions.addWidget(self._btn_gmail)
        btn_box.addLayout(row_actions)

        row_secondary = QHBoxLayout()
        row_secondary.setSpacing(8)

        self._btn_reddit = neutral_button("💬 Message on Reddit", parent=self)
        self._btn_reddit.clicked.connect(self._open_reddit)
        row_secondary.addWidget(self._btn_reddit)

        self._btn_copy_template = neutral_button("📋 Copy Order Message", parent=self)
        self._btn_copy_template.clicked.connect(self._copy_template)
        row_secondary.addWidget(self._btn_copy_template)

        btn_close = neutral_button("Close", parent=self)
        btn_close.clicked.connect(self.accept)
        row_secondary.addWidget(btn_close)
        btn_box.addLayout(row_secondary)

        layout.addLayout(btn_box)

        # Initial UI refresh
        self._refresh_pack_ui()

    def _on_pack_selected(self, key: str) -> None:
        self._selected_key = key
        self._refresh_pack_ui()

    def _refresh_pack_ui(self) -> None:
        for k, btn in self._pack_buttons.items():
            name, price, dur, tag = self._packs[k]
            if k == self._selected_key:
                accent = TOKENS["accent_gold"] if k == "lifetime" else TOKENS["success"]
                btn.setStyleSheet(
                    f"background-color: rgba(16, 185, 129, 0.16); border: 2px solid {accent}; "
                    f"border-radius: 8px; font-weight: bold; color: #ffffff; padding: 4px; font-size: 11px;"
                )
            else:
                btn.setStyleSheet(
                    f"background-color: {TOKENS['surface_hi']}; border: 1px solid {TOKENS['border_lo']}; "
                    f"border-radius: 8px; color: {TOKENS['text_muted']}; padding: 4px; font-size: 11px;"
                )
        name, price, dur, tag = self._packs[self._selected_key]
        self._sum_lbl_left.setText(
            f"<b>Selected:</b> <span style='color: #ffffff;'>{name}</span> "
            f"<span style='color: {TOKENS['accent_gold']};'>({tag})</span><br>"
            f"<span style='color: {TOKENS['text_muted']};'>{dur} • Instant Cryptographic Delivery</span>"
        )
        self._sum_lbl_price.setText(price)

    def _copy_id(self) -> None:
        QGuiApplication.clipboard().setText(self._hw_input.text())
        self._btn_copy_hw.setText("✓ Copied!")
        QTimer.singleShot(2000, lambda: self._btn_copy_hw.setText("📋 Copy ID"))

    def _open_portal(self) -> None:
        from app.ui.qt.purchase_portal import open_purchase_portal
        name, price, dur, tag = self._packs[self._selected_key]
        open_purchase_portal(self._machine_id, f"{name} ({price})")

    def _open_gmail(self) -> None:
        name, price, dur, tag = self._packs[self._selected_key]
        subject = urllib.parse.quote(f"ApexClash Pro Purchase Request - {name}")
        body = urllib.parse.quote(
            f"Hi Keshav,\n\n"
            f"I would like to purchase an ApexClash Pro license key.\n\n"
            f"Selected Pass: {name} ({price})\n"
            f"My Device ID: {self._machine_id}\n"
            f"Preferred Payment Method: PayPal / UPI / Crypto / Card\n\n"
            f"Thank you!"
        )
        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to=cockingkeshav@gmail.com&su={subject}&body={body}"
        webbrowser.open(gmail_url)

    def _open_reddit(self) -> None:
        name, price, dur, tag = self._packs[self._selected_key]
        reddit_url = (
            f"https://www.reddit.com/message/compose/?to=post_matrix"
            f"&subject={urllib.parse.quote('ApexClash Pro Purchase')}"
            f"&message={urllib.parse.quote(f'Hi, I would like to buy ApexClash Pro ({name} - {price}). My Device ID is: {self._machine_id}')}"
        )
        webbrowser.open(reddit_url)

    def _copy_template(self) -> None:
        name, price, dur, tag = self._packs[self._selected_key]
        msg = (
            f"Hi Keshav, I'd like to buy an ApexClash Pro activation key.\n"
            f"Plan: {name} ({price})\n"
            f"Device ID: {self._machine_id}\n"
            f"Preferred Payment: PayPal / Crypto / UPI / Card"
        )
        QGuiApplication.clipboard().setText(msg)
        self._btn_copy_template.setText("✓ Copied to Clipboard!")
        QTimer.singleShot(2500, lambda: self._btn_copy_template.setText("📋 Copy Order Message"))


class ManageLicenseDialog(QDialog):
    """Dialog for reviewing active license details and support."""

    def __init__(self, parent: Optional[QWidget], machine_id: str, current_key: str, status_desc: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("ApexClash Pro — License Management & Support")
        self.setFixedWidth(500)
        self.setStyleSheet(f"background-color: {TOKENS['surface_lo']}; color: {TOKENS['text']};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        head_row = QHBoxLayout()
        head_row.setSpacing(12)
        logo_lbl = QLabel()
        pix = logo_pixmap(42)
        if not pix.isNull():
            logo_lbl.setPixmap(pix)
            logo_lbl.setStyleSheet("border-radius: 8px;")
        head_row.addWidget(logo_lbl)

        head_col = QVBoxLayout()
        head_col.setSpacing(2)
        lbl_title = QLabel("ApexClash Pro — License & Support")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")
        head_col.addWidget(lbl_title)
        lbl_sub = QLabel("MANAGEMENT & RENEWAL")
        lbl_sub.setStyleSheet(f"font-size: 9px; font-weight: 800; color: {TOKENS['primary']}; letter-spacing: 0.5px;")
        head_col.addWidget(lbl_sub)
        head_row.addLayout(head_col)
        head_row.addStretch()
        layout.addLayout(head_row)

        info = QLabel(
            f"<b>Active Key:</b> {current_key if current_key else '(No key entered)'}<br>"
            f"<b>Status:</b> {status_desc}<br>"
            f"<b>Device ID:</b> {machine_id}<br><br>"
            "To renew your subscription pass, upgrade to Lifetime VIP ($15), or transfer your license to a new PC, please contact the developer directly:<br>"
            "• <b>Email:</b> <a style='color: #38bdf8;' href='mailto:cockingkeshav@gmail.com'>cockingkeshav@gmail.com</a><br>"
            "• <b>Discord:</b> <span style='color: #22c55e; font-weight: bold;'>matrix0456</span><br>"
            "• <b>Reddit:</b> <span style='color: #f59e0b; font-weight: bold;'>u/post_matrix</span>"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setOpenExternalLinks(True)
        info.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.5;")
        layout.addWidget(info)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        btn_email = primary_button("📧 Email Developer", parent=self)
        btn_email.clicked.connect(lambda: self._open_support_email(current_key, machine_id))
        btn_box.addWidget(btn_email)

        btn_copy = neutral_button("📋 Copy Info", parent=self)
        btn_copy.clicked.connect(lambda: self._copy_info(current_key, machine_id, status_desc))
        btn_box.addWidget(btn_copy)

        btn_close = neutral_button("Close", parent=self)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)

    def _open_support_email(self, key: str, machine_id: str) -> None:
        subject = urllib.parse.quote("ApexClash Pro License Support / Renewal")
        body = urllib.parse.quote(
            f"Hi Keshav,\n\n"
            f"I need support with my ApexClash Pro license.\n\n"
            f"Current Key: {key}\n"
            f"Device ID: {machine_id}\n"
            f"Request: (Renewal / Lifetime Upgrade / Device Transfer)\n\n"
            f"Thank you!"
        )
        gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to=cockingkeshav@gmail.com&su={subject}&body={body}"
        webbrowser.open(gmail_url)

    def _copy_info(self, key: str, machine_id: str, status_desc: str) -> None:
        text = (
            f"ApexClash Pro Support Details\n"
            f"Key: {key}\n"
            f"Device ID: {machine_id}\n"
            f"Status: {status_desc}\n"
        )
        QGuiApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", "Support details copied to clipboard!")



class LicensePage(QWidget):
    _DEBOUNCE_MS = 200

    def __init__(
        self,
        controller: BotController,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._show_plain = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self._DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._refresh_status_caption)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        layout.setSpacing(SPACING["md"])
        layout.addWidget(PageTitle("License & Hardware Activation"))

        intro = QLabel(
            "Enter your activation key below or enjoy your included 2-hour free trial."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {TOKENS['text_muted']};")
        layout.addWidget(intro)

        # Pricing Banner Card
        plan_card = Card()
        plan_card.card_layout.addWidget(SectionTitle("Official Access Passes & Pricing"))
        plan_header = QHBoxLayout()
        plan_title = QLabel("Weekly: $1.00  |  Monthly: $3.00  |  Annual: $10.00  |  Lifetime: $15.00")
        plan_title.setStyleSheet(f"color: {TOKENS['accent_gold']}; font-size: 15px; font-weight: bold;")
        plan_header.addWidget(plan_title)
        plan_header.addStretch()
        trial_badge = QLabel("⚡ 2-HOUR FREE TRIAL INCLUDED")
        trial_badge.setStyleSheet(f"background-color: {TOKENS['surface_hi']}; color: {TOKENS['accent_gold']}; border: 1px solid {TOKENS['border_hi']}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;")
        plan_header.addWidget(trial_badge)
        plan_card.card_layout.addLayout(plan_header)

        plan_desc = QLabel(
            "• Weekly: $1.00 (7D)  •  Monthly: $3.00 (30D)  •  Annual: $10.00 (365D)  •  Lifetime: $15.00 (Permanent VIP)\n"
            "• Instant key delivery with 24/7 customer support\n"
            "• Full Access: Autonomous Combat, Smart Loot Filtration, Advanced Anti-Ban Suite\n"
            "• 2 Hours of free trial automatically active on first launch — test everything risk-free"
        )
        plan_desc.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.4;")
        plan_card.card_layout.addWidget(plan_desc)
        layout.addWidget(plan_card)

        # Device ID Card
        hw_card = Card()
        hw_card.card_layout.addWidget(SectionTitle("Device ID"))
        hw_row = QHBoxLayout()
        self._machine_id = CryptoLicenseEngine.get_machine_id()
        self._hw_entry = QLineEdit(self._machine_id)
        self._hw_entry.setReadOnly(True)
        self._hw_entry.setFont(QFont("Courier New", 10))
        self._hw_entry.setStyleSheet(f"background-color: {TOKENS['surface_hi']}; color: {TOKENS['text']};")
        hw_row.addWidget(self._hw_entry, stretch=1)
        self._btn_copy_hw = neutral_button("📋 Copy Device ID", parent=self)
        self._btn_copy_hw.clicked.connect(self._copy_hardware_id)
        hw_row.addWidget(self._btn_copy_hw)
        hw_card.card_layout.addLayout(hw_row)
        layout.addWidget(hw_card)

        # Official Purchase Channels Card
        contact_card = Card()
        contact_card.card_layout.addWidget(SectionTitle("Buy an Activation Key (Instant Delivery)"))
        contact_desc = QLabel(
            "Copy your <b>Device ID</b> above and message the developer to receive your key:<br>"
            "• <b>Email:</b> <a style='color: #38bdf8;' href='mailto:cockingkeshav@gmail.com'>cockingkeshav@gmail.com</a><br>"
            "• <b>Discord:</b> <span style='color: #22c55e;'>matrix0456</span><br>"
            "• <b>Reddit:</b> <span style='color: #f59e0b;'>u/post_matrix</span><br>"
            "Accepted payments: PayPal, Crypto, UPI, Cards. Fast instant delivery!"
        )
        contact_desc.setTextFormat(Qt.TextFormat.RichText)
        contact_desc.setOpenExternalLinks(True)
        contact_desc.setStyleSheet(f"color: {TOKENS['text']}; font-size: 12px; line-height: 1.5;")
        contact_card.card_layout.addWidget(contact_desc)
        layout.addWidget(contact_card)

        self._status_text = QTextEdit()
        self._status_text.setReadOnly(True)
        self._status_text.setFixedHeight(85)
        layout.addWidget(self._status_text)

        key_row = QHBoxLayout()
        self._entry = QLineEdit()
        self._entry.setPlaceholderText("CAL-M30-YYYYMMDD-UNIV-XXXXXXXX")
        self._entry.setEchoMode(QLineEdit.Password)
        mono = QFont("Courier New", 10)
        self._entry.setFont(mono)
        self._entry.textEdited.connect(self._on_key_typed)
        key_row.addWidget(self._entry, stretch=1)

        self._eye_btn = VisibilityToggleButton(parent=self)
        self._eye_btn.toggled.connect(self._on_visibility_toggled)
        key_row.addWidget(self._eye_btn)

        self._dot = StatusDot()
        key_row.addWidget(self._dot)

        self._btn_check = primary_button("Check Key", parent=self)
        self._btn_check.clicked.connect(self._on_check_key)
        key_row.addWidget(self._btn_check)

        layout.addLayout(key_row)

        footer = QHBoxLayout()
        self._btn_subscribe = primary_button("Buy Subscription ($1/wk, $3/mo)", parent=self)
        self._btn_subscribe.setToolTip("View pricing options and purchase a Weekly, Monthly, or Annual Pass.")
        self._btn_subscribe.clicked.connect(self._open_subscribe_checkout)
        footer.addWidget(self._btn_subscribe)

        self._btn_lifetime = neutral_button("Buy Lifetime ($15 VIP)", parent=self)
        self._btn_lifetime.setToolTip("Get a permanent Lifetime VIP pass with unlimited updates.")
        self._btn_lifetime.clicked.connect(self._open_lifetime_checkout)
        footer.addWidget(self._btn_lifetime)

        self._btn_portal = neutral_button("Manage License", parent=self)
        self._btn_portal.setToolTip(
            "View license details, renewal options, or request developer assistance."
        )
        self._btn_portal.clicked.connect(self._open_billing_portal)
        footer.addWidget(self._btn_portal)

        self._btn_unpair = neutral_button("Unpair…", parent=self)
        self._btn_unpair.clicked.connect(self._open_unpair)
        footer.addWidget(self._btn_unpair)

        footer.addStretch()
        layout.addLayout(footer)
        layout.addStretch()

        self._controller.licenseChanged.connect(self._on_license_changed)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        saved = load_saved_key()
        self._entry.setText(saved)
        self._show_plain = False
        self._eye_btn.setChecked(False)
        self._entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._debounce_timer.stop()
        self._sync_from_controller()

    def hideEvent(self, event) -> None:
        saved = load_saved_key().strip()
        typed = self._entry.text().strip()
        if self._controller.license_state() == LicenseState.STALE or typed != saved:
            self._controller.recheck_license(new_key=saved)
            self._entry.setText(saved)
        super().hideEvent(event)

    def _on_license_changed(self, state: LicenseState, reason: str) -> None:
        self._sync_activate_buttons(state)
        if reason != "stale":
            self._sync_from_controller()
        self._paint_dot(state)

    def _sync_from_controller(self) -> None:
        state = self._controller.license_state()
        self._paint_dot(state)
        self._refresh_status_caption()
        self._sync_activate_buttons(state)

    def _sync_activate_buttons(self, state: LicenseState) -> None:
        self._btn_check.setEnabled(True)
        self._btn_check.setText("Check Key")
        if state in (LicenseState.VALIDATING, LicenseState.RETRYING):
            self._btn_check.setEnabled(False)

    def _paint_dot(self, state: LicenseState) -> None:
        self._dot.set_color(DOT_COLORS.get(state, TOKENS["danger"]))

    def _status_caption(self, state: LicenseState) -> Tuple[str, str]:
        if state == LicenseState.VALID:
            sub = self._controller.license_expiry_subcaption()
            if sub:
                return (f"Licensed. ({sub})", TOKENS["success"])
            return ("Licensed.", TOKENS["success"])
        if state == LicenseState.VALIDATING:
            return ("Checking license…", TOKENS["warning"])
        if state == LicenseState.RETRYING:
            return ("Reconnecting to license server…", TOKENS["warning"])
        if state == LicenseState.STALE:
            return (
                "You edited the key since it was last validated. Click Check Key below to verify.",
                TOKENS["text_muted"],
            )
        if state == LicenseState.EMPTY:
            return (
                "No license yet. Paste your key below, then Check Key.",
                TOKENS["text_muted"],
            )
        if state in (LicenseState.INVALID, LicenseState.UNREACHABLE):
            return (self._controller.license_user_message(), TOKENS["danger"])
        return ("Unknown license status.", TOKENS["text_muted"])

    def _refresh_status_caption(self) -> None:
        text, color = self._status_caption(self._controller.license_state())
        self._status_text.setPlainText(text.rstrip() or " ")
        self._status_text.setStyleSheet(f"color: {color};")

    def _on_key_typed(self, _text: str) -> None:
        if self._controller.license_state() == LicenseState.VALID:
            self._controller.mark_license_stale()
        self._debounce_timer.stop()
        self._debounce_timer.start()

    def _on_check_key(self) -> None:
        self._debounce_timer.stop()
        key = self._entry.text().strip()
        self._btn_check.setEnabled(False)
        self._refresh_status_caption_for_state(LicenseState.VALIDATING)
        self._controller.recheck_license(new_key=key)

    def _refresh_status_caption_for_state(self, state: LicenseState) -> None:
        text, color = self._status_caption(state)
        self._status_text.setPlainText(text.rstrip() or " ")
        self._status_text.setStyleSheet(f"color: {color};")
        self._paint_dot(state)

    def _on_visibility_toggled(self, visible: bool) -> None:
        self._show_plain = visible
        self._entry.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self._eye_btn.setToolTip("Hide password" if visible else "Show password")

    def _copy_hardware_id(self) -> None:
        QGuiApplication.clipboard().setText(self._machine_id)
        self._btn_copy_hw.setText("✓ Copied!")
        QTimer.singleShot(2000, lambda: self._btn_copy_hw.setText("📋 Copy Device ID"))

    def _open_subscribe_checkout(self) -> None:
        from app.ui.qt.purchase_portal import open_purchase_portal
        try:
            open_purchase_portal(self._machine_id, "Monthly ($3/mo)")
        except Exception:
            pass
        PurchaseOptionsDialog(self.window(), self._machine_id, "Monthly ($3/mo)").exec()

    def _open_lifetime_checkout(self) -> None:
        from app.ui.qt.purchase_portal import open_purchase_portal
        try:
            open_purchase_portal(self._machine_id, "Lifetime VIP ($15)")
        except Exception:
            pass
        PurchaseOptionsDialog(self.window(), self._machine_id, "Lifetime VIP ($15)").exec()

    def _open_billing_portal(self) -> None:
        key = self._entry.text().strip()
        state = self._controller.license_state()
        sub = self._controller.license_expiry_subcaption()
        status_str = f"Active Pro ({sub})" if state == LicenseState.VALID and sub else ("Active Pro" if state == LicenseState.VALID else "Inactive")
        ManageLicenseDialog(self.window(), self._machine_id, key, status_str).exec()

    def _open_unpair(self) -> None:
        key = self._entry.text().strip()
        if not key:
            show_error(
                self.window(),
                "Unpair",
                "Enter your license key in the field above first.",
            )
            return
        dlg = UnpairConfirmDialog(self.window(), self._controller, key)
        if dlg.exec():
            self._entry.clear()
            self._sync_from_controller()
