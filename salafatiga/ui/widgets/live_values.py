"""Taula de valors actuals."""
from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from salafatiga.core import variables
from salafatiga.core.datamodel import Reading


class LiveValuesWidget(QWidget):
    """Mostra les ultimes lectures per equip."""

    HEADERS = ("Variable", "Valor", "Unitat", "Qualitat", "Hora", "Nota")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._equip_id: str | None = None
        self._rows: dict[str, int] = {}
        self._readings: dict[tuple[str, str], Reading] = {}

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        self._build_rows()

    def set_equip(self, equip_id: str) -> None:
        self._equip_id = equip_id
        self.refresh()

    def update_reading(self, reading: Reading) -> None:
        self._readings[(reading.equip_id, reading.variable_id)] = reading
        if self._equip_id is None or reading.equip_id == self._equip_id:
            self._write_reading(reading)

    def refresh(self) -> None:
        for row in range(self.table.rowCount()):
            for col in range(1, len(self.HEADERS)):
                self.table.setItem(row, col, QTableWidgetItem(""))
        if self._equip_id is None:
            return
        for (equip_id, _variable_id), reading in self._readings.items():
            if equip_id == self._equip_id:
                self._write_reading(reading)

    def _build_rows(self) -> None:
        for var_def in variables.all_defs():
            if not var_def.per_equip:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._rows[var_def.id] = row
            self.table.setItem(row, 0, QTableWidgetItem(var_def.nom))
            for col in range(1, len(self.HEADERS)):
                self.table.setItem(row, col, QTableWidgetItem(""))

    def _write_reading(self, reading: Reading) -> None:
        row = self._rows.get(reading.variable_id)
        if row is None:
            return
        value = "" if reading.value is None else f"{reading.value:.2f}".rstrip("0").rstrip(".")
        values = (
            value,
            reading.unit,
            reading.quality.value,
            _format_ts(reading.ts),
            reading.note,
        )
        for col, text in enumerate(values, start=1):
            item = QTableWidgetItem(text)
            if col in (1, 2, 3, 4):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, col, item)


def _format_ts(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
