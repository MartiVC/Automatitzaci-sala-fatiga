"""API FastAPI per consultar l'historic."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from salafatiga.config.models import Config
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, Origin, Quality, Reading
from salafatiga.storage import (
    Database,
    MeasurementFilter,
    OracleDatabase,
    OracleRepository,
    OracleUnavailable,
    ReadFacade,
    StorageRepository,
)

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).with_name("web")


def create_app(cfg: Config, repository: ReadFacade | StorageRepository | None = None) -> FastAPI:
    """Crea l'aplicacio FastAPI. No parla amb dispositius de camp.

    ``repository`` pot ser:
      - ``None``: la pròpia app obre el SQLite local i, si oracle.enabled,
        també intenta obrir el pool d'Oracle, i munta una :class:`ReadFacade`.
      - una ``ReadFacade`` ja construïda (típicament des de run_app.py).
      - un ``StorageRepository`` (compatibilitat amb tests/usos antics).
    """
    db: Database | None = None
    oracle_db: OracleDatabase | None = None

    if repository is None:
        # Sempre necessitem el SQLite com a font de fallback.
        db = Database.from_config(cfg)
        conn = db.open()
        local_repo = StorageRepository(conn)
        remote_repo: OracleRepository | None = None
        if cfg.oracle.enabled:
            try:
                oracle_db = OracleDatabase(cfg.oracle, equips=cfg.variador.equips)
                pool = oracle_db.open()
                remote_repo = OracleRepository(pool)
                log.info("Oracle ON  (dashboard llegirà d'Oracle amb fallback al SQLite)")
            except OracleUnavailable as exc:
                log.warning("Oracle no disponible (%s). Dashboard llegirà del SQLite local.", exc)
                oracle_db = None
        repository = ReadFacade(local_repo, remote_repo)
    elif isinstance(repository, StorageRepository):
        repository = ReadFacade(repository, None)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if oracle_db is not None:
                oracle_db.close()
            if db is not None:
                db.close()

    app = FastAPI(
        title="Sala de fatiga",
        version="0.1.0",
        description="Consulta remota de l'historic del PC LAB.",
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.config = cfg

    def repo_dep() -> ReadFacade:
        return repository

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "installation": cfg.app.nom_installacio,
            "equips": [
                {"id": e.id, "addr": e.addr, "descripcio": e.descripcio}
                for e in cfg.variador.equips
            ],
            "db_path": str(cfg.storage.db_path),
            "storage_mode": repository.mode,
            "storage_error": repository.last_error,
            "ts": time.time(),
        }

    @app.get("/api/variables")
    def variable_catalog() -> list[dict]:
        return [_variable_to_dict(v) for v in variables.all_defs()]

    @app.get("/api/latest")
    def latest(
        equip_id: str | None = None,
        variable_id: Annotated[list[str] | None, Query()] = None,
        repo: ReadFacade = Depends(repo_dep),
    ) -> list[dict]:
        latest_map = repo.latest_measurements(equip_id=equip_id, variable_ids=variable_id)
        return [_reading_to_dict(reading) for reading in latest_map.values()]

    @app.get("/api/measurements")
    def measurements(
        ts_from: float | None = None,
        ts_to: float | None = None,
        equip_id: str | None = None,
        variable_id: str | None = None,
        origin: str | None = None,
        quality: str | None = None,
        limit: int = Query(default=500, ge=1, le=10_000),
        newest_first: bool = True,
        repo: ReadFacade = Depends(repo_dep),
    ) -> list[dict]:
        try:
            origin_enum = Origin(origin) if origin else None
            quality_enum = Quality(quality) if quality else None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        readings = repo.query_measurements(
            MeasurementFilter(
                ts_from=ts_from,
                ts_to=ts_to,
                equip_id=equip_id,
                variable_id=variable_id,
                origin=origin_enum,
                quality=quality_enum,
                limit=limit,
                newest_first=newest_first,
            )
        )
        return [_reading_to_dict(reading) for reading in readings]

    @app.get("/api/events")
    def events(
        ts_from: float | None = None,
        ts_to: float | None = None,
        equip_id: str | None = None,
        code: str | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
        newest_first: bool = True,
        repo: ReadFacade = Depends(repo_dep),
    ) -> list[dict]:
        rows = repo.query_events(
            ts_from=ts_from,
            ts_to=ts_to,
            equip_id=equip_id,
            code=code,
            limit=limit,
            newest_first=newest_first,
        )
        return [_event_to_dict(event) for event in rows]

    return app


def run_server(cfg: Config) -> None:
    """Arrenca el servidor web amb uvicorn (bloqueja fins a Ctrl+C)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Falta uvicorn. Instal·la requirements.txt.") from exc

    # Si està darrere d'un reverse proxy intern, uvicorn ha de confiar en les
    # capçaleres X-Forwarded-* perquè el FastAPI generi URLs correctes (https,
    # subdomini) i registri la IP real de l'usuari als logs.
    proxy_headers = bool(cfg.web.behind_proxy)
    forwarded_allow_ips = cfg.web.forwarded_allow_ips if proxy_headers else "127.0.0.1"

    uvicorn.run(
        create_app(cfg),
        host=cfg.web.host,
        port=cfg.web.port,
        log_level=cfg.logging.level.lower(),
        proxy_headers=proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
    )


def _reading_to_dict(reading: Reading) -> dict:
    return {
        "ts": reading.ts,
        "equip_id": reading.equip_id,
        "origin": reading.origin.value,
        "variable_id": reading.variable_id,
        "variable_name": _var_name(reading.variable_id),
        "value": reading.value,
        "unit": reading.unit,
        "quality": reading.quality.value,
        "raw": reading.raw,
        "status_code": reading.status_code,
        "note": reading.note,
    }


def _event_to_dict(event: Event) -> dict:
    return {
        "ts": event.ts,
        "equip_id": event.equip_id,
        "origin": event.origin.value,
        "type": event.type.value,
        "severity": int(event.severity),
        "severity_name": event.severity.name,
        "code": event.code,
        "message": event.message,
        "variable_id": event.variable_id,
        "variable_name": _var_name(event.variable_id) if event.variable_id else None,
        "value": event.value,
    }


def _variable_to_dict(var_def) -> dict:
    return {
        "id": var_def.id,
        "name": var_def.nom,
        "origin": var_def.origin.value,
        "kind": var_def.kind.value,
        "unit": var_def.unit,
        "per_equip": var_def.per_equip,
        "valid_min": var_def.valid_min,
        "valid_max": var_def.valid_max,
        "warn_min": var_def.warn_min,
        "warn_max": var_def.warn_max,
        "alarm_min": var_def.alarm_min,
        "alarm_max": var_def.alarm_max,
    }


def _var_name(variable_id: str) -> str:
    try:
        return variables.get(variable_id).nom
    except KeyError:
        return variable_id
