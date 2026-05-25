"""Connexio i inicialitzacio de la base de dades SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from salafatiga.config.models import Config, EquipVariador
from salafatiga.core import variables

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def open_connection(path: str | Path) -> sqlite3.Connection:
    """Obre una connexio SQLite preparada per a l'aplicacio."""
    db_path = Path(path)
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    # WAL: permet que el dashboard web llegeixi mentre l'app de captura escriu,
    # sense bloquejos mutus. busy_timeout: espera (no falla) si la BD està ocupada.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn


def initialize_database(
    conn: sqlite3.Connection,
    *,
    equips: Iterable[EquipVariador] = (),
) -> None:
    """Crea l'esquema i sincronitza els catalegs estatics."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn:
        conn.executescript(schema)
        _migrate_add_synced_at(conn)
        _upsert_devices(conn, equips)
        _upsert_variables(conn)


def _migrate_add_synced_at(conn: sqlite3.Connection) -> None:
    """Afegeix la columna synced_at a measurements/events si encara no hi és.

    Bases creades amb una versió anterior del schema no la tenen; el sync amb
    Oracle la necessita per saber quines files queden pendents de bolcar.
    També crea els índexs sobre 'synced_at' (no es poden posar al schema.sql
    perquè sobre BD antigues la columna encara no existeix quan s'executa).
    """
    for table, index in (("measurements", "idx_meas_sync"), ("events", "idx_evt_sync")):
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "synced_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN synced_at REAL")
        conn.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} (synced_at, id)")


def _upsert_devices(conn: sqlite3.Connection, equips: Iterable[EquipVariador]) -> None:
    conn.executemany(
        """
        INSERT INTO devices (id, descripcio, addr, active)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(id) DO UPDATE SET
            descripcio = excluded.descripcio,
            addr = excluded.addr,
            active = 1
        """,
        ((e.id, e.descripcio, e.addr) for e in equips),
    )


def _upsert_variables(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO variables (id, nom, origin, kind, unit, per_equip, descripcio)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            nom = excluded.nom,
            origin = excluded.origin,
            kind = excluded.kind,
            unit = excluded.unit,
            per_equip = excluded.per_equip,
            descripcio = excluded.descripcio
        """,
        (
            (
                v.id,
                v.nom,
                v.origin.value,
                v.kind.value,
                v.unit,
                int(v.per_equip),
                v.descripcio,
            )
            for v in variables.all_defs()
        ),
    )


class Database:
    """Gestor simple del cicle de vida de la connexio SQLite."""

    def __init__(self, path: str | Path, *, equips: Iterable[EquipVariador] = ()) -> None:
        self.path = Path(path)
        self._equips = list(equips)
        self.conn: sqlite3.Connection | None = None

    @classmethod
    def from_config(cls, cfg: Config) -> "Database":
        return cls(cfg.storage.db_path, equips=cfg.variador.equips)

    def open(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = open_connection(self.path)
            initialize_database(self.conn, equips=self._equips)
        return self.conn

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> sqlite3.Connection:
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
