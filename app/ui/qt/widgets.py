"""Reusable Qt widgets for the AutoLoot UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QSize, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.license import LicenseState
from app.ui.qt.theme import SPACING, TOKENS


DOT_COLORS = {
    LicenseState.VALID: TOKENS["success"],
    LicenseState.VALIDATING: TOKENS["warning"],
    LicenseState.RETRYING: TOKENS["warning"],
    LicenseState.INVALID: TOKENS["danger"],
    LicenseState.EMPTY: TOKENS["danger"],
    LicenseState.STALE: TOKENS["danger"],
    LicenseState.UNREACHABLE: TOKENS["danger"],
}


def format_license_expires_on_line(sub: str) -> str:
    s = sub.strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith("expires on:"):
        rest = s.split(":", 1)[1].strip()
        return f"Expires on: {rest}"
    return f"Expires on: {s}"


def format_trial_expires_in_minutes(remaining_seconds: int) -> str:
    mins = max(1, (int(remaining_seconds) + 59) // 60)
    unit = "minute" if mins == 1 else "minutes"
    return f"Expires in: {mins} {unit}"


class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            SPACING["md"], SPACING["md"], SPACING["md"], SPACING["md"]
        )
        self._layout.setSpacing(SPACING["sm"])

    @property
    def card_layout(self) -> QVBoxLayout:
        return self._layout

    def layout(self) -> QVBoxLayout:
        return self._layout


class StatCard(QFrame):
    """Modern dashboard stat card showing a metric title, bold value, and sub-label."""

    def __init__(
        self,
        title: str,
        initial_value: str = "0",
        sub_text: str = "",
        color_hex: str = TOKENS["text"],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(130)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SPACING["sm"] + 2, SPACING["sm"] + 2, SPACING["sm"] + 2, SPACING["sm"] + 2)
        lay.setSpacing(2)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        lay.addWidget(self._title_lbl)

        self._val_lbl = QLabel(initial_value)
        self._val_lbl.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: bold;")
        lay.addWidget(self._val_lbl)

        self._sub_lbl = QLabel(sub_text)
        self._sub_lbl.setStyleSheet(f"color: {TOKENS['text_muted']}; font-size: 11px;")
        lay.addWidget(self._sub_lbl)

    def set_value(self, val: str, sub_text: Optional[str] = None) -> None:
        self._val_lbl.setText(val)
        if sub_text is not None:
            self._sub_lbl.setText(sub_text)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionTitle")
        self.setAutoFillBackground(False)


class PageTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


class StatusDot(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(TOKENS["danger"])
        self.setFixedSize(14, 14)

    def set_color(self, hex_or_name: str) -> None:
        self._color = QColor(hex_or_name)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(QRectF(2, 2, 10, 10))


class ToggleSwitch(QCheckBox):
    def __init__(
        self,
        text: str = "",
        *,
        parent: Optional[QWidget] = None,
        danger: bool = False,
        under_development: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("ToggleSwitch")
        self._danger = danger
        self._under_development = under_development
        self.setFixedHeight(24)
        if under_development:
            self.setChecked(False)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track_w, track_h = (40, 22)
        x0 = 0
        y0 = (self.height() - track_h) // 2
        if self._under_development:
            on_color = QColor("#3f3f46")
            off_color = QColor("#2d2d33")
            text_color = QColor("#4a5568")
        else:
            on_color = QColor(TOKENS["danger"] if self._danger else TOKENS["primary"])
            off_color = QColor("#3f3f46")
            text_color = QColor(TOKENS["danger"] if self._danger else TOKENS["text"])

        if self.isChecked() and not self._under_development:
            track_color = on_color
        else:
            track_color = off_color

        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(x0, y0, track_w, track_h, track_h / 2, track_h / 2)
        knob_d = 18
        if self.isChecked() and not self._under_development:
            knob_x = x0 + track_w - knob_d - 2
        else:
            knob_x = x0 + 2
        knob_y = y0 + (track_h - knob_d) // 2
        painter.setBrush(QColor("#a0a0a8" if self._under_development else "#ffffff"))
        painter.drawEllipse(knob_x, knob_y, knob_d, knob_d)

        if self.text():
            painter.setPen(text_color)
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            text_rect = QRectF(track_w + 10, 0, self.width() - track_w - 10, self.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

    def mousePressEvent(self, event) -> None:
        if self._under_development:
            from app.ui.qt.dialogs import show_under_development
            show_under_development(self.window())
            return
        super().mousePressEvent(event)

    def sizeHint(self) -> QSize:
        if self.text():
            text_w = self.fontMetrics().horizontalAdvance(self.text()) + 8
        else:
            text_w = 0
        return QSize(40 + text_w + 10, 24)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)


def _styled_button(text: str, role: str, parent: Optional[QWidget] = None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setProperty("role", role)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


def primary_button(text: str, *, parent: Optional[QWidget] = None) -> QPushButton:
    return _styled_button(text, "primary", parent)


def danger_button(text: str, *, parent: Optional[QWidget] = None) -> QPushButton:
    return _styled_button(text, "danger", parent)


def neutral_button(text: str, *, parent: Optional[QWidget] = None) -> QPushButton:
    return _styled_button(text, "neutral", parent)


def chip_button(text: str, *, parent: Optional[QWidget] = None) -> QPushButton:
    return _styled_button(text, "chip", parent)


def segment_button(
    text: str,
    *,
    parent: Optional[QWidget] = None,
    under_development: bool = False,
) -> QPushButton:
    btn = _styled_button(text, "segment", parent)
    if under_development:
        btn.setCheckable(False)
        btn.setProperty("underDevelopment", True)
    else:
        btn.setCheckable(True)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    btn.setMinimumWidth(int(btn.sizeHint().width() * 1.1))
    return btn


class StepperButton(QPushButton):
    """Compact up/down arrow for numeric steppers."""

    def __init__(self, up: bool, *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._up = up
        self.setProperty("role", "stepper")
        self.setFixedSize(22, 13)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style().unpolish(self)
        self.style().polish(self)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.isEnabled():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TOKENS["text"]))
        cx = self.width() / 2
        cy = self.height() / 2
        if self._up:
            points = [
                QPointF(cx, cy - 3),
                QPointF(cx - 4, cy + 2),
                QPointF(cx + 4, cy + 2),
            ]
        else:
            points = [
                QPointF(cx, cy + 3),
                QPointF(cx - 4, cy - 2),
                QPointF(cx + 4, cy - 2),
            ]
        painter.drawPolygon(QPolygonF(points))


class HelpButton(QPushButton):
    """Compact ? button that opens a help popup when clicked."""

    def __init__(self, on_click: Callable[[], None], *, parent: Optional[QWidget] = None) -> None:
        super().__init__("?", parent)
        self.setProperty("role", "help")
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("What does each option do?")
        self.style().unpolish(self)
        self.style().polish(self)
        self.clicked.connect(on_click)


class VisibilityToggleButton(QPushButton):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "icon")
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setToolTip("Show password")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.connect(lambda: self.update())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(TOKENS["text"])
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = self.width() / 2
        cy = self.height() / 2
        painter.drawEllipse(QRectF(cx - 9, cy - 6, 18, 12))

        if self.isChecked():
            painter.drawLine(int(cx - 8), int(cy + 6), int(cx + 8), int(cy - 6))
            return

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - 2.5, cy - 2.5, 5, 5))


class TrialBannerWidget(QFrame):
    """Sidebar widget displaying real-time trial progress and Pro upgrade action."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("TrialBanner")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._title_lbl = QLabel("TRIAL STATUS")
        self._title_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {TOKENS['text_muted']};")
        layout.addWidget(self._title_lbl)

        self._status_lbl = QLabel("⏳ Initializing trial...")
        self._status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
        layout.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._progress)

        self._btn = QPushButton("⚡ Upgrade ($5/mo)")
        self._btn.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {TOKENS['primary']}, stop:1 {TOKENS['success']});"
            "color: #ffffff; font-weight: bold; border-radius: 6px; padding: 6px 10px; font-size: 12px;"
        )
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self._on_upgrade_clicked)
        layout.addWidget(self._btn)

    def _on_upgrade_clicked(self) -> None:
        import webbrowser
        from app.ui.qt._constants import SUBSCRIBE_CHECKOUT_URL
        webbrowser.open(SUBSCRIBE_CHECKOUT_URL)

    def update_status(self, lic_state: LicenseState, remaining_seconds: Optional[int]) -> None:
        if lic_state == LicenseState.VALID:
            self._title_lbl.setText("LICENSE")
            self._status_lbl.setText("🛡️ Pro Active")
            self._status_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TOKENS['success']};")
            self._progress.setValue(100)
            self._btn.setText("Manage Subscription")
            self._btn.setStyleSheet(f"background-color: {TOKENS['neutral_dark']}; color: {TOKENS['text']}; border-radius: 6px; padding: 5px 10px; font-size: 11px;")
        elif remaining_seconds is not None and remaining_seconds > 0:
            self._title_lbl.setText("FREE TRIAL")
            hrs = remaining_seconds // 3600
            mins = (remaining_seconds % 3600) // 60
            if hrs > 0:
                self._status_lbl.setText(f"⏳ {hrs}h {mins:02d}m left")
            else:
                self._status_lbl.setText(f"⏳ {mins}m left")
            self._status_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #38bdf8;")
            pct = max(0, min(100, int((remaining_seconds / 7200.0) * 100)))
            self._progress.setValue(pct)
            self._btn.setText("⚡ Upgrade ($5/mo)")
            self._btn.setStyleSheet(
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {TOKENS['primary']}, stop:1 {TOKENS['success']});"
                "color: #ffffff; font-weight: bold; border-radius: 6px; padding: 6px 10px; font-size: 12px;"
            )
        else:
            self._title_lbl.setText("TRIAL EXPIRED")
            self._status_lbl.setText("🔒 0m remaining")
            self._status_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {TOKENS['danger']};")
            self._progress.setValue(0)
            self._btn.setText("⚡ Activate Pro ($5/mo)")


class RaidHistoryTable(QTableWidget):
    """Live interactive table displaying recent raids telemetry."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(0, 7, parent)
        self.setHorizontalHeaderLabels([
            "#", "Time", "Gold Looted", "Elixir Looted", "Dark Elixir", "Skips", "Outcome"
        ])
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setMinimumHeight(170)

    def add_raid_row(self, rec) -> None:
        self.insertRow(0)

        item_num = QTableWidgetItem(f"#{rec.raid_num}")
        item_time = QTableWidgetItem(rec.timestamp_str)
        item_gold = QTableWidgetItem(f"+{rec.gold:,}")
        item_gold.setForeground(QColor("#f59e0b"))
        item_elixir = QTableWidgetItem(f"+{rec.elixir:,}")
        item_elixir.setForeground(QColor("#ec4899"))
        item_dark = QTableWidgetItem(f"+{rec.dark_elixir:,}")
        item_dark.setForeground(QColor("#38bdf8"))
        item_skips = QTableWidgetItem(str(rec.skips))
        item_status = QTableWidgetItem(rec.status)
        item_status.setForeground(QColor(TOKENS["success"] if "Victory" in rec.status else TOKENS["warning"]))

        for col, item in enumerate([item_num, item_time, item_gold, item_elixir, item_dark, item_skips, item_status]):
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(0, col, item)

        if self.rowCount() > 30:
            self.removeRow(self.rowCount() - 1)

