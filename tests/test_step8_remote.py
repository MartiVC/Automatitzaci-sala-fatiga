"""Tests del pas 8: API web FastAPI.

Si FastAPI no esta instal.lat en l'entorn local, aquests tests es salten. Les
dependencies ja estan declarades a requirements.txt.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from fastapi.testclient import TestClient

from salafatiga.config import load_config
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, EventType, Origin, Reading, Severity
from salafatiga.remote.api import create_app
from salafatiga.storage import StorageRepository, initialize_database

ROOT = Path(__file__).resolve().parents[1]


def _client() -> TestClient:
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    initialize_database(conn, equips=cfg.variador.equips)
    repo = StorageRepository(conn)
    app = create_app(cfg, repository=repo)
    return TestClient(app)


def test_remote_health_and_catalog():
    client = _client()

    health = client.get("/api/health")
    catalog = client.get("/api/variables")

    assert health.status_code == 200
    payload = health.json()
    assert payload["ok"] is True
    assert isinstance(payload["equips"], list)
    assert {"GRUP1_B1", "GRUP2_B1"}.issubset({e["id"] for e in payload["equips"]})
    assert catalog.status_code == 200
    assert any(row["id"] == variables.V_T_MOTOR for row in catalog.json())


def test_remote_serves_dashboard_shell_and_assets():
    client = _client()

    index = client.get("/")
    app_js = client.get("/static/app.js")
    styles = client.get("/static/styles.css")

    assert index.status_code == 200
    assert 'id="metric-grid"' in index.text
    assert 'id="chart"' in index.text
    # Navegació per pestanyes (Resum + una pestanya per bomba).
    assert 'id="tabs"' in index.text
    assert 'id="page-overview"' in index.text
    assert 'id="page-equip"' in index.text
    assert 'id="pump-grid"' in index.text
    assert app_js.status_code == 200
    assert "refreshAll" in app_js.text
    assert "drawChart" in app_js.text
    assert "renderOverview" in app_js.text
    assert "setActiveTab" in app_js.text
    assert styles.status_code == 200
    assert ".kpi-row" in styles.text
    assert ".pump-grid" in styles.text
    assert ".tabs" in styles.text


def test_remote_latest_and_measurements():
    client = _client()
    repo = client.app.state.repository
    repo.add_readings(
        [
            Reading(100.0, "WEB_TEST", Origin.PLC, variables.V_T_MOTOR, 50.0, "°C"),
            Reading(101.0, "WEB_TEST", Origin.PLC, variables.V_T_MOTOR, 55.0, "°C"),
        ]
    )

    latest = client.get("/api/latest", params={"equip_id": "WEB_TEST"})
    measurements = client.get(
        "/api/measurements",
        params={"equip_id": "WEB_TEST", "variable_id": variables.V_T_MOTOR},
    )

    assert latest.status_code == 200
    assert latest.json()[0]["value"] == 55.0
    assert measurements.status_code == 200
    assert len(measurements.json()) == 2


def test_remote_events():
    client = _client()
    repo = client.app.state.repository
    repo.add_event(
        Event(
            100.0,
            "WEB_TEST",
            Origin.PLC,
            EventType.ALARM_SET,
            Severity.ALARM,
            "ALARM_WEB_TEST",
            "Alarma test web",
            variable_id=variables.V_T_MOTOR,
            value=111.0,
        )
    )

    response = client.get("/api/events", params={"equip_id": "WEB_TEST"})

    assert response.status_code == 200
    assert response.json()[0]["code"] == "ALARM_WEB_TEST"
