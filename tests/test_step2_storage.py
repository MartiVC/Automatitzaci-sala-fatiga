"""Tests del pas 2: emmagatzematge SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from salafatiga.config import load_config
from salafatiga.core import datamodel as dm
from salafatiga.core import variables as cat
from salafatiga.storage import Database, MeasurementFilter, StorageRepository, initialize_database

ROOT = Path(__file__).resolve().parents[1]


def _connection() -> sqlite3.Connection:
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_database(conn, equips=cfg.variador.equips)
    return conn


def _repo() -> StorageRepository:
    return StorageRepository(_connection())


def test_initialize_database_seeds_catalogs():
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    conn = _connection()

    device_count = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    variable_count = conn.execute("SELECT COUNT(*) FROM variables").fetchone()[0]

    assert device_count == len(cfg.variador.equips)
    assert variable_count == len(cat.all_defs())
    conn.close()


def test_insert_and_query_readings():
    repo = _repo()
    readings = [
        dm.Reading(10.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_INTENSITAT, 4.2, "A", raw=42),
        dm.Reading(11.0, "GRUP1_B1", dm.Origin.PLC, cat.V_T_MOTOR, 56.0, "degC"),
        dm.Reading(12.0, "GRUP2_B1", dm.Origin.VARIADOR, cat.V_PRESSIO, None, "bar", dm.Quality.BAD),
    ]

    assert repo.add_readings(readings) == 3
    result = repo.query_measurements(
        MeasurementFilter(equip_id="GRUP1_B1", ts_from=10.5, ts_to=12.0)
    )

    assert len(result) == 1
    assert result[0].variable_id == cat.V_T_MOTOR
    assert result[0].origin is dm.Origin.PLC


def test_latest_measurements():
    repo = _repo()
    repo.add_readings(
        [
            dm.Reading(10.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_PRESSIO, 1.0, "bar"),
            dm.Reading(20.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_PRESSIO, 2.0, "bar"),
            dm.Reading(15.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_INTENSITAT, 5.0, "A"),
        ]
    )

    latest = repo.latest_measurements(equip_id="GRUP1_B1")

    assert latest[("GRUP1_B1", cat.V_PRESSIO)].value == 2.0
    assert latest[("GRUP1_B1", cat.V_INTENSITAT)].value == 5.0


def test_insert_and_query_events():
    repo = _repo()
    event = dm.Event(
        100.0,
        "GRUP1_B1",
        dm.Origin.VARIADOR,
        dm.EventType.ALARM_SET,
        dm.Severity.ALARM,
        "VFD_33",
        "Treball en sec",
        variable_id=cat.V_ALARMA_CODI,
        value=33,
    )

    assert repo.add_event(event) == 1
    events = repo.query_events(equip_id="GRUP1_B1", code="VFD_33")

    assert len(events) == 1
    assert events[0].type is dm.EventType.ALARM_SET
    assert events[0].severity is dm.Severity.ALARM


def test_purge_older_than():
    repo = _repo()
    repo.add_readings(
        [
            dm.Reading(1.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_PRESSIO, 1.0, "bar"),
            dm.Reading(100.0, "GRUP1_B1", dm.Origin.VARIADOR, cat.V_PRESSIO, 2.0, "bar"),
        ]
    )
    repo.add_event(
        dm.Event(1.0, dm.SISTEMA_EQUIP_ID, dm.Origin.SISTEMA, dm.EventType.SYSTEM,
                 dm.Severity.INFO, "OLD", "antic")
    )

    deleted_measurements, deleted_events = repo.purge_older_than(50.0)

    assert (deleted_measurements, deleted_events) == (1, 1)
    assert len(repo.query_measurements()) == 1
    assert repo.query_events() == []
