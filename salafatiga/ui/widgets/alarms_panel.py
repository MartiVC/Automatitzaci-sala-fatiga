"""Panell d'esdeveniments i alarmes."""
from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from salafatiga.core.datamodel import Event


class AlarmsPanel(QWidget):
    """Registre d'esdeveniments generats pel sistema."""

    HEADERS = ("Hora", "Equip", "Severitat", "Tipus", "Codi", "Missatge")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def add_event(self, event: Event) -> None:
        self.table.insertRow(0)
        values = (
            dt.datetime.fromtimestamp(event.ts).strftime("%H:%M:%S"),
            event.equip_id,
            event.severity.name,
            event.type.value,
            event.code,
            event.message,
        )
        for col, text in enumerate(values):
            self.table.setItem(0, col, QTableWidgetItem(str(text)))
        if self.table.rowCount() > 500:
            self.table.removeRow(self.table.rowCount() - 1)

    def set_events(self, events: list[Event]) -> None:
        self.table.setRowCount(0)
        for event in reversed(events):
            self.add_event(event)
