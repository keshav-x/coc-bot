"""Modal dialogs for the Qt UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.services.license import clear_saved_key
from app.ui.qt.branding import apply_app_icon
from app.ui.qt._constants import UNPAIR_USER_ERRORS
from app.ui.qt.bot_controller import BotController
from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import danger_button, neutral_button


def show_error(parent: Optional[QWidget], title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_under_development(parent: Optional[QWidget]) -> None:
    QMessageBox.information(
        parent,
        "Under development",
        "This feature is under development.",
    )


def show_bb_prioritise_help(parent: Optional[QWidget]) -> None:
    QMessageBox.information(
        parent,
        "Prioritise loot",
        "Choose what the bot optimises for after each attack:\n\n"
        "• Gold — waits until 2 stars, then ends the battle.\n"
        "• Both — waits until 1 star, then ends the battle.\n"
        "• Elixir — surrenders immediately after deploying troops.",
    )


class RankedAttackConfirmDialog(QDialog):
    def __init__(self, parent: Optional[QWidget], minutes: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ranked attack fill")
        self.setModal(True)
        self._remaining = 5
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_countdown)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )

        msg = (
            f"The bot will use up your ranked attacks up to {minutes} "
            "minutes, are you sure you want to continue?"
        )
        label = QLabel(msg)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {TOKENS['text']};")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.addStretch()
        self._btn_no = neutral_button("No", parent=self)
        self._btn_no.clicked.connect(self.reject)
        row.addWidget(self._btn_no)

        self._btn_yes = danger_button("Yes (5)", parent=self)
        self._btn_yes.setEnabled(False)
        self._btn_yes.clicked.connect(self.accept)
        row.addWidget(self._btn_yes)

        layout.addLayout(row)

        self._tick_countdown()
        self._timer.start()

    def _tick_countdown(self) -> None:
        if self._remaining > 0:
            self._btn_yes.setText(f"Yes ({self._remaining})")
            self._btn_yes.setEnabled(False)
            self._remaining -= 1
        else:
            self._timer.stop()
            self._btn_yes.setText("Yes")
            self._btn_yes.setEnabled(True)

    @classmethod
    def ask(cls, parent: Optional[QWidget], minutes: int) -> bool:
        dlg = cls(parent, minutes)
        return dlg.exec() == QDialog.Accepted


class UnpairConfirmDialog(QDialog):
    UNPAIR_W = 440
    UNPAIR_H = 420

    def __init__(self, parent: QWidget, controller: BotController, key: str) -> None:
        super().__init__(parent)
        self._controller = controller
        self._key = key.strip()
        self.setWindowTitle("Unpair this PC")
        apply_app_icon(self)
        self.setModal(True)
        self.resize(self.UNPAIR_W, self.UNPAIR_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )

        body = QLabel(
            "This will permanently remove THIS computer from your license binding on our server, and delete the license file saved under your Windows user folder.\n\n"
            "• You will need Check Key again later to reuse the same key.\n\n"
            "Copy your license key below if you need it for another PC or reinstall."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {TOKENS['text_muted']};")
        layout.addWidget(body)

        layout.addWidget(QLabel("Your license key"))
        key_row = QHBoxLayout()
        self._key_disp = QLineEdit(self._key)
        self._key_disp.setReadOnly(True)
        mono = self._key_disp.font()
        mono.setFamily("Courier New")
        self._key_disp.setFont(mono)
        key_row.addWidget(self._key_disp, stretch=1)

        copy_btn = neutral_button("Copy", parent=self)
        copy_btn.clicked.connect(self._copy_key)
        key_row.addWidget(copy_btn)
        layout.addLayout(key_row)

        btn_row = QHBoxLayout()
        cancel = neutral_button("Cancel", parent=self)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        btn_row.addStretch()

        self._btn_unpair = danger_button("Unpair this PC", parent=self)
        self._btn_unpair.clicked.connect(self._on_confirm_unpair)
        btn_row.addWidget(self._btn_unpair)
        layout.addLayout(btn_row)

    def _copy_key(self) -> None:
        QGuiApplication.clipboard().setText(self._key)

    def _on_confirm_unpair(self) -> None:
        self._btn_unpair.setEnabled(False)
        self._btn_unpair.setText("Working…")

        def on_done(ok: bool, reason: str) -> None:
            self._btn_unpair.setEnabled(True)
            self._btn_unpair.setText("Unpair this PC")
            if ok:
                QMessageBox.information(
                    self.window(),
                    "Unpaired",
                    "This PC was unpaired from the license and your saved key file was removed.",
                )
                self.accept()
            else:
                msg = UNPAIR_USER_ERRORS.get(reason, reason.replace("_", " ").title())
                QMessageBox.critical(self.window(), "Could not unpair", msg)

        self._controller.try_unpair_async(self._key, on_done)
