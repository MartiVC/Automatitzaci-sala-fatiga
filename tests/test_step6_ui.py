"""Tests del pas 6: UI Qt."""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from salafatiga.config import load_config
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, EventType, Origin, Reading, Severity
from salafatiga.storage import StorageRepository, initialize_database
from salafatiga.ui import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _repository() -> StorageRepository:
    cfg = load_config("config/config.example.yaml")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_database(conn, equips=cfg.variador.equips)
    return StorageRepository(conn)


def test_main_window_instantiates_without_service():
    _app()
    cfg = load_config("config/config.example.yaml")
    repo = _repository()

    window = MainWindow(cfg, repo, acquisition_service=None)

    assert window.windowTitle() == cfg.app.nom_installacio
    assert window.start_action.isEnabled() is False
    window.close()


def test_main_window_updates_from_reading_and_event():
    _app()
    cfg = load_config("config/config.example.yaml")
    repo = _repository()
    window = MainWindow(cfg, repo, acquisition_service=None)

    reading = Reading.now("GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 55.0, unit="°C")
    event = Event.now(
        "GRUP1_B1",
        Origin.PLC,
        EventType.WARNING_SET,
        Severity.WARNING,
        "WARNING_T_MOTOR",
        "Temp. motor alta",
        variable_id=variables.V_T_MOTOR,
        value=55.0,
    )

    window._on_reading(reading)
    window._on_event(event)

    latest = repo.latest_measurements(equip_id="GRUP1_B1", variable_ids=[variables.V_T_MOTOR])
    assert latest[("GRUP1_B1", variables.V_T_MOTOR)].value == 55.0
    assert repo.query_events(limit=1)[0].code == "WARNING_T_MOTOR"
    window.close()
