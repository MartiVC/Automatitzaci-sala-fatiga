"""Finestra principal Qt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from salafatiga.config.models import Config
from salafatiga.core.datamodel import Event, Reading
from salafatiga.services.acquisition_service import AcquisitionService
from salafatiga.services.oracle_sync import OracleSyncService
from salafatiga.storage import StorageRepository
from salafatiga.ui.widgets.alarms_panel import AlarmsPanel
from salafatiga.ui.widgets.comm_status import CommStatusWidget
from salafatiga.ui.widgets.config_dialog import ConfigDialog
from salafatiga.ui.widgets.history_view import HistoryView
from salafatiga.ui.widgets.live_charts import LiveChartsWidget
from salafatiga.ui.widgets.live_values import LiveValuesWidget


class MainWindow(QMainWindow):
    """Aplicacio local de supervisio del PC LAB."""

    def __init__(
        self,
        cfg: Config,
        repository: StorageRepository,
        acquisition_service: AcquisitionService | None = None,
        sync_service: OracleSyncService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.repository = repository
        self.acquisition_service = acquisition_service
        self.sync_service = sync_service
        self._running = False

        self.setWindowTitle(cfg.app.nom_installacio)
        self.resize(1180, 760)

        self.equip_ids = [equip.id for equip in cfg.variador.equips] or ["PLC"]
        self.current_equip = cfg.ui.equip_per_defecte or self.equip_ids[0]

        self.live_values = LiveValuesWidget()
        self.comm_status = CommStatusWidget()
        self.live_charts = LiveChartsWidget(cfg.ui.chart_window_s)
        self.alarms_panel = AlarmsPanel()
        self.history_view = HistoryView(repository, self.equip_ids, cfg.export.dir)

        self.live_values.set_equip(self.current_equip)
        self.live_charts.set_equip(self.current_equip)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_once)
        self._timer.setInterval(max(int(cfg.app.poll_period_s * 1000), 250))

        self._build_toolbar()
        self._build_tabs()
        self._load_initial_history()
        self._connect_bus()
        self._load_stylesheet()

        self._oracle_timer = QTimer(self)
        self._oracle_timer.timeout.connect(self._refresh_oracle_badge)
        self._oracle_timer.setInterval(5000)
        self._refresh_oracle_badge()
        self._oracle_timer.start()

        self.statusBar().showMessage("Preparat")

    def start_acquisition(self) -> None:
        if self.acquisition_service is None or self._running:
            return
        self._running = True
        self._timer.start()
        self.start_action.setEnabled(False)
        self.stop_action.setEnabled(True)
        self.statusBar().showMessage("Adquisicio en marxa")

    def stop_acquisition(self) -> None:
        self._timer.stop()
        self._running = False
        self.start_action.setEnabled(self.acquisition_service is not None)
        self.stop_action.setEnabled(False)
        self.statusBar().showMessage("Adquisicio aturada")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.stop_acquisition()
        self._oracle_timer.stop()
        if self.acquisition_service is not None:
            self.acquisition_service.close()
        super().closeEvent(event)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Principal")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        style = self.style()
        self.start_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Inicia", self)
        self.start_action.triggered.connect(self.start_acquisition)
        self.start_action.setEnabled(self.acquisition_service is not None)
        toolbar.addAction(self.start_action)

        self.stop_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop), "Atura", self)
        self.stop_action.triggered.connect(self.stop_acquisition)
        self.stop_action.setEnabled(False)
        toolbar.addAction(self.stop_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Equip "))
        self.equip_combo = QComboBox()
        for equip_id in self.equip_ids:
            self.equip_combo.addItem(equip_id)
        idx = max(self.equip_combo.findText(self.current_equip), 0)
        self.equip_combo.setCurrentIndex(idx)
        self.equip_combo.currentTextChanged.connect(self._set_equip)
        toolbar.addWidget(self.equip_combo)

        toolbar.addSeparator()
        config_action = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "Config", self)
        config_action.triggered.connect(self._show_config_dialog)
        toolbar.addAction(config_action)

    def _build_tabs(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._synoptic_tab(), "Sinoptic")
        tabs.addTab(self.live_charts, "Grafiques")
        tabs.addTab(self.alarms_panel, "Alarmes")
        tabs.addTab(self.history_view, "Historic")
        tabs.addTab(self._config_tab(), "Config")
        self.setCentralWidget(tabs)

    def _synoptic_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self.comm_status)
        layout.addWidget(self.live_values, 1)
        return page

    def _config_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("Instal·lacio", QLabel(self.cfg.app.nom_installacio))
        form.addRow("Mostreig general", QLabel(f"{self.cfg.app.poll_period_s:g} s"))
        form.addRow("Variador", QLabel(f"{self.cfg.variador.port} · {self.cfg.variador.baudrate} {self.cfg.variador.bytesize}{self.cfg.variador.parity}{self.cfg.variador.stopbits}"))
        form.addRow("PLC", QLabel(f"{self.cfg.plc.host}:{self.cfg.plc.port} · mode={self.cfg.plc.mode}"))
        form.addRow("SQLite", QLabel(str(self.cfg.storage.db_path)))
        layout.addLayout(form)
        button = QPushButton("Obre dialeg")
        button.clicked.connect(self._show_config_dialog)
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _connect_bus(self) -> None:
        if self.acquisition_service is None:
            return
        bus = self.acquisition_service.bus
        bus.on_reading(self._on_reading)
        bus.on_event(self._on_event)
        bus.on_status(self.comm_status.update_status)

    def _poll_once(self) -> None:
        if self.acquisition_service is None:
            return
        try:
            result = self.acquisition_service.poll_once()
        except Exception as exc:
            self.statusBar().showMessage(f"Error d'adquisicio: {exc}")
            return
        self.statusBar().showMessage(
            f"{len(result.readings)} lectures · {len(result.events)} esdeveniments"
        )

    def _on_reading(self, reading: Reading) -> None:
        self.live_values.update_reading(reading)
        self.live_charts.update_reading(reading)
        try:
            self.repository.add_reading(reading)
        except Exception as exc:
            self.statusBar().showMessage(f"No s'ha pogut guardar lectura: {exc}")

    def _on_event(self, event: Event) -> None:
        self.alarms_panel.add_event(event)
        try:
            self.repository.add_event(event)
        except Exception as exc:
            self.statusBar().showMessage(f"No s'ha pogut guardar esdeveniment: {exc}")

    def _set_equip(self, equip_id: str) -> None:
        self.current_equip = equip_id
        self.live_values.set_equip(equip_id)
        self.live_charts.set_equip(equip_id)

    def _show_config_dialog(self) -> None:
        dialog = ConfigDialog(self.cfg, self)
        dialog.exec()

    def _load_initial_history(self) -> None:
        try:
            self.alarms_panel.set_events(self.repository.query_events(limit=200))
        except Exception:
            pass

    def _refresh_oracle_badge(self) -> None:
        """Reflecteix l'estat del sync Oracle al badge del sinòptic.

        - sync_service is None i oracle.enabled=False → OFF (gris)
        - sync_service is None i oracle.enabled=True  → INACCESSIBLE (vermell)
        - last_push_ok=True                            → OK (verd)
        - last_push_ok=False                           → DEGRADAT (vermell) + tooltip amb error
        """
        if self.sync_service is None:
            if self.cfg.oracle.enabled:
                self.comm_status.update_oracle_state(
                    "lost",
                    "INACCESSIBLE",
                    "Oracle activat a la config però no s'ha pogut obrir a l'arrencada. "
                    "Revisa logs i xarxa.",
                )
            else:
                self.comm_status.update_oracle_state(
                    "disabled",
                    "OFF",
                    "Oracle desactivat. Només s'escriu al buffer SQLite local.",
                )
            return

        if self.sync_service.last_push_ok:
            tooltip_bits = [
                f"Mesures sincronitzades: {self.sync_service.measurements_synced_total}",
                f"Esdeveniments sincronitzats: {self.sync_service.events_synced_total}",
            ]
            self.comm_status.update_oracle_state(
                "ok", "OK", "\n".join(tooltip_bits),
            )
        else:
            self.comm_status.update_oracle_state(
                "error",
                "DEGRADAT",
                f"Últim push ha fallat: {self.sync_service.last_error or 'sense detall'}",
            )

    def _load_stylesheet(self) -> None:
        qss = Path(__file__).with_name("resources") / "style.qss"
        try:
            self.setStyleSheet(qss.read_text(encoding="utf-8"))
        except OSError:
            pass


def show_startup_error(message: str) -> None:
    QMessageBox.critical(None, "Sala de fatiga", message)
