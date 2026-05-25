"""Tests del pas 9: integració Oracle + sync SQLite -> Oracle.

No requereixen una instància real d'Oracle: usen un repositori remot fake en
memòria que reprodueix la mateixa interfície que OracleRepository.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from salafatiga.config import ConfigError, load_config
from salafatiga.config.loader import _build
from salafatiga.config.models import SyncConfig
from salafatiga.core import datamodel as dm
from salafatiga.core import variables as cat
from salafatiga.services.oracle_sync import OracleSyncService
from salafatiga.storage import Database, ReadFacade, StorageRepository, initialize_database
from salafatiga.storage.oracle_database import OracleUnavailable

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _new_conn() -> sqlite3.Connection:
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_database(conn, equips=cfg.variador.equips)
    return conn


def _sample_readings(n: int, *, base_ts: float = 1000.0) -> list[dm.Reading]:
    return [
        dm.Reading(
            base_ts + i, "GRUP1_B1", dm.Origin.PLC, cat.V_T_MOTOR, 50.0 + i, "degC"
        )
        for i in range(n)
    ]


def _sample_events(n: int, *, base_ts: float = 1000.0) -> list[dm.Event]:
    return [
        dm.Event(
            base_ts + i, "GRUP1_B1", dm.Origin.VARIADOR,
            dm.EventType.ALARM_SET, dm.Severity.ALARM,
            f"VFD_{i}", f"alarma {i}",
        )
        for i in range(n)
    ]


class FakeOracleRepo:
    """Fake amb la mateixa firma pública que OracleRepository."""

    def __init__(self, *, fail_n: int = 0) -> None:
        self.readings: list[dm.Reading] = []
        self.events: list[dm.Event] = []
        self.fail_n = fail_n            # nombre de pushs que ha de fallar abans de tenir èxit
        self.add_readings_calls = 0
        self.add_events_calls = 0
        self.add_readings_batches: list[int] = []

    def add_readings(self, readings):
        self.add_readings_calls += 1
        lst = list(readings)
        if self.fail_n > 0:
            self.fail_n -= 1
            raise OracleUnavailable("simulated outage")
        self.readings.extend(lst)
        self.add_readings_batches.append(len(lst))
        return len(lst)

    def add_events(self, events):
        self.add_events_calls += 1
        lst = list(events)
        # Reaprofitem la mateixa simulació de fallada per simplicitat.
        if self.fail_n > 0:
            self.fail_n -= 1
            raise OracleUnavailable("simulated outage")
        self.events.extend(lst)
        return len(lst)


# --------------------------------------------------------------------------- #
#  Migració SQLite (synced_at)
# --------------------------------------------------------------------------- #
def test_migration_adds_synced_at_to_legacy_database(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, equip_id TEXT NOT NULL, origin TEXT NOT NULL,
            variable_id TEXT NOT NULL, value REAL,
            unit TEXT NOT NULL DEFAULT '', quality TEXT NOT NULL,
            raw INTEGER, status_code INTEGER, note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, equip_id TEXT NOT NULL, origin TEXT NOT NULL,
            type TEXT NOT NULL, severity INTEGER NOT NULL,
            code TEXT NOT NULL, message TEXT NOT NULL,
            variable_id TEXT, value REAL
        );
        """
    )
    legacy.commit()
    legacy.close()

    db = Database(db_path)
    db.open()
    cols_m = {r[1] for r in db.conn.execute("PRAGMA table_info(measurements)")}
    cols_e = {r[1] for r in db.conn.execute("PRAGMA table_info(events)")}
    indexes = {r[0] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )}
    db.close()

    assert "synced_at" in cols_m
    assert "synced_at" in cols_e
    assert "idx_meas_sync" in indexes
    assert "idx_evt_sync" in indexes


# --------------------------------------------------------------------------- #
#  Mètodes nous del StorageRepository (sync API)
# --------------------------------------------------------------------------- #
def test_pending_and_mark_synced_round_trip():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(5))
    repo.add_events(_sample_events(3))

    pending_m = repo.pending_measurements(limit=10)
    pending_e = repo.pending_events(limit=10)
    assert len(pending_m) == 5
    assert len(pending_e) == 3
    assert all(isinstance(pid, int) for pid, _ in pending_m)

    repo.mark_measurements_synced([pid for pid, _ in pending_m[:3]], ts=999.0)
    still_pending = repo.pending_measurements(limit=10)

    assert len(still_pending) == 2
    assert {pid for pid, _ in still_pending} == {pid for pid, _ in pending_m[3:]}


def test_pending_respects_batch_limit():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(50))

    batch = repo.pending_measurements(limit=10)

    assert len(batch) == 10
    # Han de venir ordenats per id ascendent (FIFO).
    ids = [pid for pid, _ in batch]
    assert ids == sorted(ids)


def test_purge_synced_does_not_touch_pending():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(4))
    pending = repo.pending_measurements(limit=10)
    # Marca només les dues primeres com a sincronitzades fa molt temps
    repo.mark_measurements_synced([pending[0][0], pending[1][0]], ts=1.0)

    deleted_m, deleted_e = repo.purge_synced_older_than(cutoff_ts=time.time())

    assert deleted_m == 2
    assert deleted_e == 0
    remaining = repo.pending_measurements(limit=10)
    assert len(remaining) == 2


# --------------------------------------------------------------------------- #
#  ReadFacade
# --------------------------------------------------------------------------- #
def test_read_facade_only_local_when_remote_is_none():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(2))
    facade = ReadFacade(repo, remote=None)

    rows = facade.query_measurements()

    assert len(rows) == 2
    assert facade.mode == "local"


def test_read_facade_uses_remote_when_available():
    local = StorageRepository(_new_conn())
    local.add_readings(_sample_readings(2))     # mai s'haurien de llegir

    class RemoteWithData:
        def query_measurements(self, flt):
            return _sample_readings(7)
        def latest_measurements(self, **kw):
            return {}
        def query_events(self, **kw):
            return []

    facade = ReadFacade(local, RemoteWithData())
    rows = facade.query_measurements()

    assert len(rows) == 7
    assert facade.mode == "remote"
    assert facade.last_error is None


def test_read_facade_falls_back_to_local_on_remote_failure():
    local = StorageRepository(_new_conn())
    local.add_readings(_sample_readings(2))

    class FlakyRemote:
        def query_measurements(self, flt):
            raise OracleUnavailable("boom")
        def latest_measurements(self, **kw):
            raise OracleUnavailable("boom")
        def query_events(self, **kw):
            raise OracleUnavailable("boom")

    facade = ReadFacade(local, FlakyRemote(), fallback_cooldown_s=60.0)
    rows = facade.query_measurements()

    assert len(rows) == 2
    assert facade.mode == "degraded"
    assert "boom" in (facade.last_error or "")


def test_read_facade_cooldown_skips_remote_after_failure():
    local = StorageRepository(_new_conn())
    local.add_readings(_sample_readings(1))

    class Counter:
        def __init__(self):
            self.calls = 0
        def query_measurements(self, flt):
            self.calls += 1
            raise OracleUnavailable("nope")
        def latest_measurements(self, **kw):
            self.calls += 1
            raise OracleUnavailable("nope")
        def query_events(self, **kw):
            self.calls += 1
            raise OracleUnavailable("nope")

    remote = Counter()
    facade = ReadFacade(local, remote, fallback_cooldown_s=10.0)

    facade.query_measurements()   # 1: prova remot, falla
    facade.query_measurements()   # 2: en cooldown, va directe al local

    assert remote.calls == 1      # només una crida real al remot


# --------------------------------------------------------------------------- #
#  OracleSyncService
# --------------------------------------------------------------------------- #
def test_sync_tick_pushes_pending_and_marks_synced():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(3))
    repo.add_events(_sample_events(2))
    remote = FakeOracleRepo()
    cfg = SyncConfig(enabled=True, push_period_s=0.01, batch_size=100, retention_local_days=0)

    sync = OracleSyncService(repo, remote, cfg)
    pushed = sync.tick()

    assert pushed == 5
    assert len(remote.readings) == 3
    assert len(remote.events) == 2
    assert repo.pending_measurements(limit=10) == []
    assert repo.pending_events(limit=10) == []
    assert sync.measurements_synced_total == 3
    assert sync.events_synced_total == 2


def test_sync_tick_returns_zero_when_nothing_pending():
    repo = StorageRepository(_new_conn())
    remote = FakeOracleRepo()
    sync = OracleSyncService(repo, remote, SyncConfig(enabled=True))

    assert sync.tick() == 0
    assert remote.add_readings_calls == 0


def test_sync_does_not_mark_when_remote_fails():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(2))
    remote = FakeOracleRepo(fail_n=99)        # falla sempre

    sync = OracleSyncService(repo, remote, SyncConfig(enabled=True))

    with pytest.raises(OracleUnavailable):
        sync.tick()

    # Les files han de quedar pendents per a un proper intent.
    assert len(repo.pending_measurements(limit=10)) == 2


def test_sync_backoff_doubles_on_failure_and_resets_on_success():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(1))
    remote = FakeOracleRepo(fail_n=2)
    cfg = SyncConfig(enabled=True, push_period_s=1.0, backoff_max_s=64.0)
    sync = OracleSyncService(repo, remote, cfg)

    sync._on_failure("err 1")
    sync._on_failure("err 2")
    sync._on_failure("err 3")
    assert sync._backoff == 8.0               # 1 -> 2 -> 4 -> 8

    sync._on_success()
    assert sync._backoff == cfg.push_period_s
    assert sync.last_push_ok is True
    assert sync.last_error is None


def test_sync_backoff_respects_max():
    repo = StorageRepository(_new_conn())
    sync = OracleSyncService(repo, FakeOracleRepo(), SyncConfig(
        enabled=True, push_period_s=1.0, backoff_max_s=10.0,
    ))
    for _ in range(20):
        sync._on_failure("repeated")
    assert sync._backoff == 10.0


def test_sync_purge_runs_only_after_check_period():
    repo = StorageRepository(_new_conn())
    repo.add_readings(_sample_readings(1))
    remote = FakeOracleRepo()
    fake_now = [1000.0]
    cfg = SyncConfig(enabled=True, retention_local_days=1, retention_check_period_s=60.0)
    sync = OracleSyncService(repo, remote, cfg, clock=lambda: fake_now[0])

    sync.tick()                                # bolca el 1 reading
    # Marquem-ho 'antic' manualment: ja s'ha marcat amb fake_now=1000.0
    fake_now[0] = 1000.0 + 86400 * 2           # +2 dies
    sync._maybe_purge()                         # primera vegada: corre
    remaining = repo.query_measurements()
    assert remaining == []                      # purgat
    sync._maybe_purge()                         # segona vegada: massa aviat


# --------------------------------------------------------------------------- #
#  Config (oracle:, sync:, secrets, validacions)
# --------------------------------------------------------------------------- #
def test_config_default_keeps_oracle_and_sync_disabled():
    cfg = load_config(ROOT / "config" / "config.example.yaml")
    assert cfg.oracle.enabled is False
    assert cfg.sync.enabled is False
    assert cfg.web.behind_proxy is False


def test_config_resolves_password_from_env(monkeypatch):
    monkeypatch.setenv("ORA_TEST_PWD", "s3cret")
    data = {
        "variador": {"equips": [{"id": "GRUP1_B1", "addr": 0}]},
        "oracle": {
            "enabled": True,
            "host": "h", "port": 1521, "service_name": "S",
            "user": "u",
            "password": "env:ORA_TEST_PWD",
        },
    }
    cfg = _build(data)
    assert cfg.oracle.password == "s3cret"


def test_config_resolves_password_with_braces(monkeypatch):
    monkeypatch.setenv("ORA_TEST_PWD2", "abc")
    data = {
        "variador": {"equips": [{"id": "GRUP1_B1", "addr": 0}]},
        "oracle": {
            "enabled": True,
            "host": "h", "port": 1521, "service_name": "S",
            "user": "u",
            "password": "${ORA_TEST_PWD2}",
        },
    }
    cfg = _build(data)
    assert cfg.oracle.password == "abc"


def test_config_sync_requires_oracle_enabled():
    data = {
        "variador": {"equips": [{"id": "GRUP1_B1", "addr": 0}]},
        "oracle": {"enabled": False},
        "sync":   {"enabled": True},
    }
    with pytest.raises(ConfigError, match="sync.enabled=true requereix oracle.enabled=true"):
        _build(data)


def test_config_oracle_needs_host_or_wallet():
    data = {
        "variador": {"equips": [{"id": "GRUP1_B1", "addr": 0}]},
        "oracle": {"enabled": True, "user": "u"},   # falta host/service_name
    }
    with pytest.raises(ConfigError, match="host.*service_name"):
        _build(data)
