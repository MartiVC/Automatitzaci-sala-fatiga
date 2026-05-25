"""Connexió i inicialització de la base de dades corporativa Oracle.

El PC LAB es connecta a un esquema propi (acordat amb IT) mitjançant el
driver oficial ``oracledb``. Per defecte fa servir el mode *thin* (Python
pur, sense Oracle Client). Si s'utilitza un wallet d'Oracle, el camí del
wallet s'indica al config.

Aquest mòdul només gestiona el pool/connexió i el desplegament de
l'esquema. La interfície d'inserció/consulta viu a :mod:`oracle_repository`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from salafatiga.config.models import EquipVariador, OracleConfig
from salafatiga.core import variables

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema_oracle.sql")


class OracleUnavailable(RuntimeError):
    """Es llança quan no es pot establir la connexió amb Oracle."""


def _import_oracledb():
    try:
        import oracledb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise OracleUnavailable(
            "Falta el driver 'oracledb'. Instal·la requirements.txt."
        ) from exc
    return oracledb


def open_pool(cfg: OracleConfig):
    """Obre un pool de connexions Oracle a partir del config."""
    oracledb = _import_oracledb()

    params: dict = {
        "user": cfg.user,
        "password": cfg.password,
        "min": cfg.pool_min,
        "max": cfg.pool_max,
        "increment": 1,
    }

    if cfg.wallet_dir:
        # Mode mTLS amb wallet: la cadena de connexió (alias TNS) viu al
        # tnsnames.ora dins del wallet. cfg.dsn ha de ser aquest alias.
        params["config_dir"] = str(cfg.wallet_dir)
        params["wallet_location"] = str(cfg.wallet_dir)
        if cfg.wallet_password:
            params["wallet_password"] = cfg.wallet_password
        params["dsn"] = cfg.dsn or cfg.service_name
    else:
        # Connexió directa per host/port/service_name.
        if not (cfg.host and cfg.port and cfg.service_name):
            raise OracleUnavailable(
                "Cal definir host/port/service_name (o un wallet_dir + dsn)."
            )
        params["dsn"] = oracledb.makedsn(cfg.host, cfg.port, service_name=cfg.service_name)

    try:
        return oracledb.create_pool(**params)
    except oracledb.Error as exc:
        raise OracleUnavailable(f"No s'ha pogut obrir el pool d'Oracle: {exc}") from exc


def initialize_schema(pool, *, equips: Iterable[EquipVariador] = ()) -> None:
    """Desplega l'esquema (idempotent) i sincronitza els catàlegs estàtics."""
    sql_script = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = _split_oracle_script(sql_script)

    with pool.acquire() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
        conn.commit()
        _upsert_devices(conn, equips)
        _upsert_variables(conn)
        conn.commit()


def _split_oracle_script(script: str) -> list[str]:
    """Divideix un script Oracle en sentències executables.

    El driver ``oracledb`` no accepta blocs PL/SQL terminats amb ``/`` ni
    múltiples sentències per ``execute()``. Separem per ``/`` a línia
    pròpia (estil SQL*Plus) i tornem cada bloc per separat.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for raw_line in script.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "/":
            stmt = "\n".join(buffer).strip()
            if stmt:
                statements.append(stmt)
            buffer = []
            continue
        buffer.append(line)
    tail = "\n".join(buffer).strip()
    if tail:
        # Sentències finals sense ``/`` (com el MERGE) — treu el punt i coma final
        # perquè oracledb el rebutja.
        for piece in _split_top_level(tail):
            piece = piece.strip().rstrip(";").strip()
            if piece:
                statements.append(piece)
    return statements


def _split_top_level(sql: str) -> list[str]:
    """Divideix per ``;`` a nivell superior. Adequat per a sentències SQL
    simples (no PL/SQL); els blocs PL/SQL ja s'han separat per ``/``.
    """
    return [chunk for chunk in sql.split(";\n") if chunk.strip()]


def _upsert_devices(conn, equips: Iterable[EquipVariador]) -> None:
    rows = [(e.id, e.descripcio, e.addr) for e in equips]
    if not rows:
        return
    sql = """
        MERGE INTO DEVICES d
        USING (SELECT :1 AS ID, :2 AS DESCRIPCIO, :3 AS ADDR FROM DUAL) s
        ON (d.ID = s.ID)
        WHEN MATCHED THEN UPDATE SET
            d.DESCRIPCIO = s.DESCRIPCIO,
            d.ADDR       = s.ADDR,
            d.ACTIVE     = 1
        WHEN NOT MATCHED THEN INSERT (ID, DESCRIPCIO, ADDR, ACTIVE, CREATED_AT)
        VALUES (s.ID, s.DESCRIPCIO, s.ADDR, 1, 0)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _upsert_variables(conn) -> None:
    rows = [
        (v.id, v.nom, v.origin.value, v.kind.value, v.unit, int(v.per_equip), v.descripcio)
        for v in variables.all_defs()
    ]
    sql = """
        MERGE INTO VARIABLES v
        USING (SELECT :1 AS ID, :2 AS NOM, :3 AS ORIGIN, :4 AS KIND,
                      :5 AS UNIT, :6 AS PER_EQUIP, :7 AS DESCRIPCIO FROM DUAL) s
        ON (v.ID = s.ID)
        WHEN MATCHED THEN UPDATE SET
            v.NOM        = s.NOM,
            v.ORIGIN     = s.ORIGIN,
            v.KIND       = s.KIND,
            v.UNIT       = s.UNIT,
            v.PER_EQUIP  = s.PER_EQUIP,
            v.DESCRIPCIO = s.DESCRIPCIO
        WHEN NOT MATCHED THEN INSERT
            (ID, NOM, ORIGIN, KIND, UNIT, PER_EQUIP, DESCRIPCIO)
        VALUES (s.ID, s.NOM, s.ORIGIN, s.KIND, s.UNIT, s.PER_EQUIP, s.DESCRIPCIO)
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


class OracleDatabase:
    """Gestor del cicle de vida del pool Oracle."""

    def __init__(self, cfg: OracleConfig, *, equips: Iterable[EquipVariador] = ()) -> None:
        self.cfg = cfg
        self._equips = list(equips)
        self.pool = None

    def open(self):
        if self.pool is None:
            self.pool = open_pool(self.cfg)
            if self.cfg.auto_create_schema:
                try:
                    initialize_schema(self.pool, equips=self._equips)
                except Exception as exc:  # noqa: BLE001
                    # Si l'usuari no té permisos de DDL no és fatal — IT pot
                    # haver desplegat l'esquema per separat.
                    log.warning("No s'ha pogut desplegar l'esquema Oracle: %s", exc)
        return self.pool

    def close(self) -> None:
        if self.pool is not None:
            try:
                self.pool.close()
            except Exception:  # noqa: BLE001
                pass
            self.pool = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
