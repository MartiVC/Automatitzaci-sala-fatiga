"""Repositori d'historic per a lectures i esdeveniments."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from salafatiga.core.datamodel import Event, EventType, Origin, Quality, Reading, Severity


@dataclass(frozen=True, slots=True)
class MeasurementFilter:
    """Filtre de consulta per a mesures historiques."""

    ts_from: Optional[float] = None
    ts_to: Optional[float] = None
    equip_id: Optional[str] = None
    variable_id: Optional[str] = None
    origin: Optional[Origin] = None
    quality: Optional[Quality] = None
    limit: Optional[int] = None
    newest_first: bool = False


class StorageRepository:
    """API de persistencia usada per adquisicio, UI, exportacio i web."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_reading(self, reading: Reading) -> int:
        return self.add_readings([reading])

    def add_readings(self, readings: Iterable[Reading]) -> int:
        rows = [
            (
                r.ts,
                r.equip_id,
                r.origin.value,
                r.variable_id,
                r.value,
                r.unit,
                r.quality.value,
                r.raw,
                r.status_code,
                r.note,
            )
            for r in readings
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO measurements
                    (ts, equip_id, origin, variable_id, value, unit, quality, raw, status_code, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def add_event(self, event: Event) -> int:
        return self.add_events([event])

    def add_events(self, events: Iterable[Event]) -> int:
        rows = [
            (
                e.ts,
                e.equip_id,
                e.origin.value,
                e.type.value,
                int(e.severity),
                e.code,
                e.message,
                e.variable_id,
                e.value,
            )
            for e in events
        ]
        if not rows:
            return 0
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO events
                    (ts, equip_id, origin, type, severity, code, message, variable_id, value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def query_measurements(self, flt: MeasurementFilter | None = None) -> list[Reading]:
        flt = flt or MeasurementFilter()
        clauses: list[str] = []
        params: list[object] = []

        if flt.ts_from is not None:
            clauses.append("ts >= ?")
            params.append(flt.ts_from)
        if flt.ts_to is not None:
            clauses.append("ts <= ?")
            params.append(flt.ts_to)
        if flt.equip_id is not None:
            clauses.append("equip_id = ?")
            params.append(flt.equip_id)
        if flt.variable_id is not None:
            clauses.append("variable_id = ?")
            params.append(flt.variable_id)
        if flt.origin is not None:
            clauses.append("origin = ?")
            params.append(flt.origin.value)
        if flt.quality is not None:
            clauses.append("quality = ?")
            params.append(flt.quality.value)

        sql = (
            "SELECT ts, equip_id, origin, variable_id, value, unit, quality, raw, status_code, note "
            "FROM measurements"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC" if flt.newest_first else " ORDER BY ts ASC"
        if flt.limit is not None:
            if flt.limit < 0:
                raise ValueError("MeasurementFilter.limit no pot ser negatiu.")
            sql += " LIMIT ?"
            params.append(flt.limit)

        return [_row_to_reading(row) for row in self.conn.execute(sql, params)]

    def latest_measurements(
        self,
        *,
        equip_id: str | None = None,
        variable_ids: Iterable[str] | None = None,
    ) -> dict[tuple[str, str], Reading]:
        """Retorna l'ultima lectura per parella ``(equip_id, variable_id)``."""
        params: list[object] = []
        clauses: list[str] = []
        if equip_id is not None:
            clauses.append("m.equip_id = ?")
            params.append(equip_id)

        variable_list = list(variable_ids or [])
        if variable_list:
            placeholders = ", ".join("?" for _ in variable_list)
            clauses.append(f"m.variable_id IN ({placeholders})")
            params.extend(variable_list)

        where_extra = " AND " + " AND ".join(clauses) if clauses else ""
        sql = f"""
            SELECT m.ts, m.equip_id, m.origin, m.variable_id, m.value, m.unit,
                   m.quality, m.raw, m.status_code, m.note
            FROM measurements m
            JOIN (
                SELECT equip_id, variable_id, MAX(ts) AS max_ts
                FROM measurements
                GROUP BY equip_id, variable_id
            ) latest
              ON latest.equip_id = m.equip_id
             AND latest.variable_id = m.variable_id
             AND latest.max_ts = m.ts
            WHERE 1 = 1{where_extra}
            ORDER BY m.equip_id, m.variable_id
        """
        readings = [_row_to_reading(row) for row in self.conn.execute(sql, params)]
        return {(r.equip_id, r.variable_id): r for r in readings}

    def query_events(
        self,
        *,
        ts_from: float | None = None,
        ts_to: float | None = None,
        equip_id: str | None = None,
        code: str | None = None,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list[object] = []
        if ts_from is not None:
            clauses.append("ts >= ?")
            params.append(ts_from)
        if ts_to is not None:
            clauses.append("ts <= ?")
            params.append(ts_to)
        if equip_id is not None:
            clauses.append("equip_id = ?")
            params.append(equip_id)
        if code is not None:
            clauses.append("code = ?")
            params.append(code)

        sql = (
            "SELECT ts, equip_id, origin, type, severity, code, message, variable_id, value "
            "FROM events"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC" if newest_first else " ORDER BY ts ASC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit no pot ser negatiu.")
            sql += " LIMIT ?"
            params.append(limit)

        return [_row_to_event(row) for row in self.conn.execute(sql, params)]

    def purge_older_than(self, cutoff_ts: float) -> tuple[int, int]:
        """Elimina mesures i esdeveniments mes antics que ``cutoff_ts``."""
        with self.conn:
            cur_meas = self.conn.execute("DELETE FROM measurements WHERE ts < ?", (cutoff_ts,))
            cur_evt = self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff_ts,))
        return cur_meas.rowcount, cur_evt.rowcount

    def purge_by_retention_days(self, retention_days: int) -> tuple[int, int]:
        if retention_days <= 0:
            return (0, 0)
        cutoff = time.time() - retention_days * 24 * 60 * 60
        return self.purge_older_than(cutoff)

    # ------------------------------------------------------------------ #
    #  API auxiliar per al sync SQLite -> Oracle
    # ------------------------------------------------------------------ #
    def pending_measurements(self, *, limit: int) -> list[tuple[int, Reading]]:
        """Retorna files de mesures encara no sincronitzades, ordenades per id."""
        if limit <= 0:
            return []
        cur = self.conn.execute(
            """
            SELECT id, ts, equip_id, origin, variable_id, value, unit, quality,
                   raw, status_code, note
            FROM measurements
            WHERE synced_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [(int(row["id"]), _row_to_reading(row)) for row in cur]

    def pending_events(self, *, limit: int) -> list[tuple[int, Event]]:
        if limit <= 0:
            return []
        cur = self.conn.execute(
            """
            SELECT id, ts, equip_id, origin, type, severity, code, message,
                   variable_id, value
            FROM events
            WHERE synced_at IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [(int(row["id"]), _row_to_event(row)) for row in cur]

    def mark_measurements_synced(self, ids: Iterable[int], ts: float | None = None) -> int:
        return self._mark_synced("measurements", ids, ts)

    def mark_events_synced(self, ids: Iterable[int], ts: float | None = None) -> int:
        return self._mark_synced("events", ids, ts)

    def _mark_synced(self, table: str, ids: Iterable[int], ts: float | None) -> int:
        id_list = list(ids)
        if not id_list:
            return 0
        when = time.time() if ts is None else ts
        placeholders = ",".join("?" for _ in id_list)
        with self.conn:
            cur = self.conn.execute(
                f"UPDATE {table} SET synced_at = ? WHERE id IN ({placeholders})",
                [when, *id_list],
            )
        return int(cur.rowcount)

    def purge_synced_older_than(self, cutoff_ts: float) -> tuple[int, int]:
        """Elimina files ja sincronitzades amb ``synced_at < cutoff_ts``.

        Conserva sempre el que encara no s'ha bolcat a Oracle.
        """
        with self.conn:
            cur_meas = self.conn.execute(
                "DELETE FROM measurements WHERE synced_at IS NOT NULL AND synced_at < ?",
                (cutoff_ts,),
            )
            cur_evt = self.conn.execute(
                "DELETE FROM events WHERE synced_at IS NOT NULL AND synced_at < ?",
                (cutoff_ts,),
            )
        return cur_meas.rowcount, cur_evt.rowcount

    def purge_synced_by_retention_days(self, retention_days: int) -> tuple[int, int]:
        if retention_days <= 0:
            return (0, 0)
        cutoff = time.time() - retention_days * 24 * 60 * 60
        return self.purge_synced_older_than(cutoff)


def _row_to_reading(row: sqlite3.Row) -> Reading:
    return Reading(
        ts=float(row["ts"]),
        equip_id=str(row["equip_id"]),
        origin=Origin(str(row["origin"])),
        variable_id=str(row["variable_id"]),
        value=None if row["value"] is None else float(row["value"]),
        unit=str(row["unit"] or ""),
        quality=Quality(str(row["quality"])),
        raw=None if row["raw"] is None else int(row["raw"]),
        status_code=None if row["status_code"] is None else int(row["status_code"]),
        note=str(row["note"] or ""),
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        ts=float(row["ts"]),
        equip_id=str(row["equip_id"]),
        origin=Origin(str(row["origin"])),
        type=EventType(str(row["type"])),
        severity=Severity(int(row["severity"])),
        code=str(row["code"]),
        message=str(row["message"]),
        variable_id=None if row["variable_id"] is None else str(row["variable_id"]),
        value=None if row["value"] is None else float(row["value"]),
    )
