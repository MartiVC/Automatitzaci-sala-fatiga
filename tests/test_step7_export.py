"""Tests del pas 7: exportacio CSV."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from salafatiga.config import load_config
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, EventType, Origin, Quality, Reading, Severity
from salafatiga.export import DataExporter
from salafatiga.storage import MeasurementFilter, StorageRepository, initialize_database

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "exports" / "tests"


def _repo() -> StorageRepository:
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_database(conn, equips=cfg.variador.equips)
    return StorageRepository(conn)


def _read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def test_export_measurements_csv():
    repo = _repo()
    repo.add_readings(
        [
            Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 55.5, "°C"),
            Reading(101.0, "GRUP2_B1", Origin.PLC, variables.V_T_MOTOR, 50.0, "°C"),
        ]
    )
    output = OUT_DIR / "measurements.csv"

    result = DataExporter(repo, OUT_DIR).export_measurements_csv(
        MeasurementFilter(equip_id="GRUP1_B1"),
        path=output,
    )
    rows = _read_csv(output)

    assert result.row_count == 1
    assert rows[0][:4] == ["ts_iso", "ts_unix", "equip_id", "origin"]
    assert rows[1][2] == "GRUP1_B1"
    assert rows[1][4] == variables.V_T_MOTOR
    assert rows[1][5] == variables.get(variables.V_T_MOTOR).nom


def test_export_events_csv():
    repo = _repo()
    repo.add_event(
        Event(
            100.0,
            "GRUP1_B1",
            Origin.PLC,
            EventType.ALARM_SET,
            Severity.ALARM,
            "ALARM_T_MOTOR",
            "Temp. motor alta",
            variable_id=variables.V_T_MOTOR,
            value=111.0,
        )
    )
    output = OUT_DIR / "events.csv"

    result = DataExporter(repo, OUT_DIR).export_events_csv(path=output)
    rows = _read_csv(output)

    assert result.row_count == 1
    assert rows[1][2] == "GRUP1_B1"
    assert rows[1][4] == EventType.ALARM_SET.value
    assert rows[1][6] == "ALARM_T_MOTOR"


def test_export_rejects_unknown_format():
    exporter = DataExporter(_repo(), OUT_DIR)

    with pytest.raises(ValueError):
        exporter.export_measurements(format="parquet")
