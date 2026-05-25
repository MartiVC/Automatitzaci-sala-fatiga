"""Dialeg de configuracio visible."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from salafatiga.config.models import Config


class ConfigDialog(QDialog):
    """Mostra la configuracio carregada."""

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuracio")
        form = QFormLayout()
        form.addRow("Fitxer", QLabel(str(cfg.source_path or "")))
        form.addRow("Instal·lacio", QLabel(cfg.app.nom_installacio))
        form.addRow("Port variador", QLabel(cfg.variador.port))
        form.addRow("Velocitat serie", QLabel(f"{cfg.variador.baudrate} {cfg.variador.bytesize}{cfg.variador.parity}{cfg.variador.stopbits}"))
        form.addRow("PLC", QLabel(f"{cfg.plc.host}:{cfg.plc.port} unit={cfg.plc.unit_id} mode={cfg.plc.mode}"))
        form.addRow("Historic", QLabel(str(cfg.storage.db_path)))
        form.addRow("Exports", QLabel(str(cfg.export.dir)))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
