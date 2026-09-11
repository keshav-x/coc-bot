"""Players page — multi-run account list."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.qt.theme import SPACING, TOKENS
from app.ui.qt.widgets import (
    PageTitle,
    chip_button,
    danger_button,
    neutral_button,
    primary_button,
)
from app.utils.player_list_store import PlayerEntry, load_players, save_players


class _PlayerRow(QWidget):
    def __init__(
        self,
        entry: PlayerEntry,
        on_change,
        on_move_up,
        on_move_down,
        on_remove,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_change = on_change
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._name = QLineEdit(entry.name)
        self._name.setPlaceholderText("Supercell ID name")
        self._name.setMinimumWidth(240)
        self._name.editingFinished.connect(on_change)
        layout.addWidget(self._name, stretch=1)

        self._enabled = entry.enabled
        if entry.enabled:
            self._mode_btn = primary_button("Run", parent=self)
        else:
            self._mode_btn = danger_button("Skip", parent=self)
        self._mode_btn.clicked.connect(self._toggle_mode)
        layout.addWidget(self._mode_btn)

        up = chip_button("▲", parent=self)
        up.clicked.connect(on_move_up)
        layout.addWidget(up)

        down = chip_button("▼", parent=self)
        down.clicked.connect(on_move_down)
        layout.addWidget(down)

        remove = danger_button("Remove", parent=self)
        remove.clicked.connect(on_remove)
        layout.addWidget(remove)

    def _toggle_mode(self) -> None:
        self._enabled = not self._enabled
        self._refresh_mode_button()
        self._on_change()

    def _refresh_mode_button(self) -> None:
        old = self._mode_btn
        layout = self.layout()
        idx = layout.indexOf(old)
        layout.removeWidget(old)
        old.deleteLater()
        if self._enabled:
            self._mode_btn = primary_button("Run", parent=self)
        else:
            self._mode_btn = danger_button("Skip", parent=self)
        self._mode_btn.clicked.connect(self._toggle_mode)
        layout.insertWidget(idx, self._mode_btn)

    def to_entry(self) -> Optional[PlayerEntry]:
        name = self._name.text().strip()
        if not name:
            return None
        return PlayerEntry(name=name, enabled=self._enabled)


class PlayersPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[_PlayerRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["lg"]
        )
        outer.setSpacing(SPACING["md"])
        outer.addWidget(PageTitle("Player list"))

        hint = QWidget()
        hint_layout = QVBoxLayout(hint)
        hint_layout.setContentsMargins(0, 0, 0, 0)
        from PySide6.QtWidgets import QLabel

        hint_label = QLabel(
            "Order is rotation order (↑↓). Run (green) = farm this account; Skip (red) = ignore."
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet(f"color: {TOKENS['text_muted']};")
        hint_layout.addWidget(hint_label)
        outer.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setSpacing(SPACING["sm"])
        self._list_layout.addStretch()
        scroll.setWidget(self._list_host)
        outer.addWidget(scroll, stretch=1)

        add_btn = neutral_button("Add player")
        add_btn.clicked.connect(lambda: self._add_row(PlayerEntry(name="", enabled=True)))
        outer.addWidget(add_btn)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reload()

    def _reload(self) -> None:
        while self._rows:
            row = self._rows.pop()
            self._list_layout.removeWidget(row)
            row.deleteLater()
        stretch_idx = self._list_layout.count() - 1
        for entry in load_players():
            self._insert_row(entry, stretch_idx)
            stretch_idx += 1

    def _insert_row(self, entry: PlayerEntry, before_stretch: int) -> None:
        row_holder = [None]

        def move_up() -> None:
            if row_holder[0] is not None:
                self._move_row(row_holder[0], -1)

        def move_down() -> None:
            if row_holder[0] is not None:
                self._move_row(row_holder[0], 1)

        def remove() -> None:
            if row_holder[0] is not None:
                self._remove_row(row_holder[0])

        row = _PlayerRow(
            entry,
            on_change=self._save,
            on_move_up=move_up,
            on_move_down=move_down,
            on_remove=remove,
        )
        row_holder[0] = row
        self._rows.append(row)
        self._list_layout.insertWidget(before_stretch, row)

    def _add_row(self, entry: PlayerEntry) -> None:
        stretch_idx = max(0, self._list_layout.count() - 1)
        self._insert_row(entry, stretch_idx)
        self._save()

    def _row_index(self, row: _PlayerRow) -> int:
        return self._rows.index(row)

    def _move_row(self, row: _PlayerRow, delta: int) -> None:
        idx = self._row_index(row)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self._rows):
            return
        self._rows[new_idx], self._rows[idx] = self._rows[idx], self._rows[new_idx]
        self._list_layout.removeWidget(row)
        self._list_layout.insertWidget(new_idx, row)
        self._save()

    def _remove_row(self, row: _PlayerRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self._list_layout.removeWidget(row)
        row.deleteLater()
        self._save()

    def _save(self) -> None:
        players = []
        for row in self._rows:
            entry = row.to_entry()
            if entry is not None:
                players.append(entry)
        save_players(players)
