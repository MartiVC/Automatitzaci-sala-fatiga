"""Repositori d'històric sobre Oracle.

Té la mateixa interfície pública que :class:`StorageRepository` per a que el
dashboard FastAPI hi pugui llegir sense saber d'on venen les dades. Els
mètodes d'inserció s'utilitzen pel servei de sincronització (push periòdic
des del buffer SQLite local cap a Oracle).
"""
from __future__ import annotations

from typing import Iterable

from salafatiga.core.datamodel import Event, EventType, Origin, Quality, Reading
from salafatiga.storage.repository import MeasurementFilter


class OracleRepository:
    """Lectura/inserció contra l'esquema Oracle corporatiu."""

    def __init__(self, pool) -> None:
        self.pool = pool

    # ------------------------------------------------------------------ #
    #  Insercions (les usa el sync; no l'adquisició directa)
    # ------------------------------------------------------------------ #
    def add_readings(self, readings: Iterable[Reading]) -> int:
        rows = [
            (
                r.ts, r.equip_id, r.origin.value, r.variable_id, r.value,
                r.unit, r.quality.value, r.raw, r.status_code, r.note,
            )
            for r in readings
        ]
        if not rows:
            return 0
        sql = """
            INSERT INTO MEASUREMENTS
                (TS, EQUIP_ID, ORIGIN, VARIABLE_ID, VALUE, UNIT,
                 QUALITY, RAW, STATUS_CODE, NOTE)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10)
        """
        with self.pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
        return len(rows)

    def add_events(self, events: Iterable[Event]) -> int:
        rows = [
            (
                e.ts, e.equip_id, e.origin.value, e.type.value, int(e.severity),
                e.code, e.message, e.variable_id, e.value,
            )
            for e in events
        ]
        if not rows:
            return 0
        sql = """
            INSERT INTO EVENTS
                (TS, EQUIP_ID, ORIGIN, TYPE, SEVERITY, CODE, MESSAGE,
                 VARIABLE_ID, VALUE)
            VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
        """
        with self.pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
        return len(rows)

    # ------------------------------------------------------------------ #
    #  Consultes (les usa el dashboard FastAPI)
    # ------------------------------------------------------------------ #
    def query_measurements(self, flt: MeasurementFilter | None = None) -> list[Reading]:
        flt = flt or MeasurementFilter()
        clauses: list[str] = []
        params: dict[str, object] = {}

        if flt.ts_from is not None:
            clauses.append("TS >= :ts_from"); params["ts_from"] = flt.ts_from
        if flt.ts_to is not None:
            clauses.append("TS <= :ts_to"); params["ts_to"] = flt.ts_to
        if flt.equip_id is not None:
            clauses.append("EQUIP_ID = :equip_id"); params["equip_id"] = flt.equip_id
        if flt.variable_id is not None:
            clauses.append("VARIABLE_ID = :variable_id"); params["variable_id"] = flt.variable_id
        if flt.origin is not None:
            clauses.append("ORIGIN = :origin"); params["origin"] = flt.origin.value
        if flt.quality is not None:
            clauses.append("QUALITY = :quality"); params["quality"] = flt.quality.value

        sql = (
            "SELECT TS, EQUIP_ID, ORIGIN, VARIABLE_ID, VALUE, UNIT, QUALITY, "
            "RAW, STATUS_CODE, NOTE FROM MEASUREMENTS"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY TS DESC" if flt.newest_first else " ORDER BY TS ASC"
        if flt.limit is not None:
            if flt.limit < 0:
                raise ValueError("MeasurementFilter.limit no pot ser negatiu.")
            sql += " FETCH FIRST :limit ROWS ONLY"
            params["limit"] = flt.limit

        with self.pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [_row_to_reading(row) for row in cur]

    def latest_measurements(
        self,
        *,
        equip_id: str | None = None,
        variable_ids: Iterable[str] | None = None,
    ) -> dict[tuple[str, str], Reading]:
        params: dict[str, object] = {}
        clauses: list[str] = []
        if equip_id is not None:
            clauses.append("m.EQUIP_ID = :equip_id")
            params["equip_id"] = equip_id

        variable_list = list(variable_ids or [])
        if variable_list:
            bindings = []
            for i, var_id in enumerate(variable_list):
                key = f"var_{i}"
                bindings.append(f":{key}")
                params[key] = var_id
            clauses.append(f"m.VARIABLE_ID IN ({', '.join(bindings)})")

        where_extra = " AND " + " AND ".join(clauses) if clauses else ""
        sql = f"""
            SELECT m.TS, m.EQUIP_ID, m.ORIGIN, m.VARIABLE_ID, m.VALUE, m.UNIT,
                   m.QUALITY, m.RAW, m.STATUS_CODE, m.NOTE
            FROM MEASUREMENTS m
            JOIN (
                SELECT EQUIP_ID, VARIABLE_ID, MAX(TS) AS MAX_TS
                FROM MEASUREMENTS
                GROUP BY EQUIP_ID, VARIABLE_ID
            ) latest
              ON latest.EQUIP_ID    = m.EQUIP_ID
             AND latest.VARIABLE_ID = m.VARIABLE_ID
             AND latest.MAX_TS      = m.TS
            WHERE 1 = 1{where_extra}
            ORDER BY m.EQUIP_ID, m.VARIABLE_ID
        """
        with self.pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                readings = [_row_to_reading(row) for row in cur]
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
        params: dict[str, object] = {}
        if ts_from is not None:
            clauses.append("TS >= :ts_from"); params["ts_from"] = ts_from
        if ts_to is not None:
            clauses.append("TS <= :ts_to"); params["ts_to"] = ts_to
        if equip_id is not None:
            clauses.append("EQUIP_ID = :equip_id"); params["equip_id"] = equip_id
        if code is not None:
            clauses.append("CODE = :code"); params["code"] = code

        sql = (
            "SELECT TS, EQUIP_ID, ORIGIN, TYPE, SEVERITY, CODE, MESSAGE, "
            "VARIABLE_ID, VALUE FROM EVENTS"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY TS DESC" if newest_first else " ORDER BY TS ASC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit no pot ser negatiu.")
            sql += " FETCH FIRST :limit ROWS ONLY"
            params["limit"] = limit

        with self.pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [_row_to_event(row) for row in cur]


def _row_to_reading(row) -> Reading:
    (ts, equip_id, origin, variable_id, value, unit, quality,
     raw, status_code, note) = row
    return Reading(
        ts=float(ts),
        equip_id=str(equip_id),
        origin=Origin(str(origin)),
        variable_id=str(variable_id),
        value=None if value is None else float(value),
        unit=str(unit or ""),
        quality=Quality(str(quality)),
        raw=None if raw is None else int(raw),
        status_code=None if status_code is None else int(status_code),
        note=str(note or ""),
    )


def _row_to_event(row) -> Event:
    from salafatiga.core.datamodel import Severity

    (ts, equip_id, origin, type_, severity, code, message,
     variable_id, value) = row
    return Event(
        ts=float(ts),
        equip_id=str(equip_id),
        origin=Origin(str(origin)),
        type=EventType(str(type_)),
        severity=Severity(int(severity)),
        code=str(code),
        message=str(message),
        variable_id=None if variable_id is None else str(variable_id),
        value=None if value is None else float(value),
    )
