"""Vista de consulta d'historic."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from salafatiga.core import variables
from salafatiga.export import DataExporter
from salafatiga.storage import MeasurementFilter, StorageRepository


class HistoryView(QWidget):
    """Consulta rapida de mesures guardades a SQLite."""

    HEADERS = ("Hora", "Equip", "Variable", "Valor", "Unitat", "Qualitat")

    def __init__(
        self,
        repository: StorageRepository,
        equip_ids: list[str],
        export_dir: str | Path = "data/exports",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.exporter = DataExporter(repository, export_dir)

        self.equip_combo = QComboBox()
        self.equip_combo.addItem("Tots", None)
        for equip_id in equip_ids:
            self.equip_combo.addItem(equip_id, equip_id)

        self.var_combo = QComboBox()
        self.var_combo.addItem("Totes", None)
        for var_def in variables.all_defs():
            self.var_combo.addItem(var_def.nom, var_def.id)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 5000)
        self.limit_spin.setValue(500)

        self.refresh_button = QPushButton("Actualitza")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("Exporta CSV")
        self.export_button.clicked.connect(self.export_current_csv)

        form = QFormLayout()
        form.addRow("Equip", self.equip_combo)
        form.addRow("Variable", self.var_combo)
        form.addRow("Mostres", self.limit_spin)
        form.addRow("", self.refresh_button)
        form.addRow("", self.export_button)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        readings = self.repository.query_measurements(self.current_filter())
        self.table.setRowCount(0)
        for reading in readings:
            row = self.table.rowCount()
            self.table.insertRow(row)
            var_name = variables.get(reading.variable_id).nom
            value = "" if reading.value is None else f"{reading.value:g}"
            values = (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(reading.ts)),
                reading.equip_id,
                var_name,
                value,
                reading.unit,
                reading.quality.value,
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

    def export_current_csv(self) -> None:
        try:
            result = self.exporter.export_measurements_csv(self.current_filter())
        except Exception as exc:
            QMessageBox.critical(self, "Exportacio", f"No s'ha pogut exportar: {exc}")
            return
        QMessageBox.information(
            self,
            "Exportacio",
            f"S'han exportat {result.row_count} mesures a:\n{result.path}",
        )

    def current_filter(self) -> MeasurementFilter:
        return MeasurementFilter(
            equip_id=self.equip_combo.currentData(),
            variable_id=self.var_combo.currentData(),
            limit=self.limit_spin.value(),
            newest_first=True,
        )
