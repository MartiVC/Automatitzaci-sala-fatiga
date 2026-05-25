#!/usr/bin/env python3
"""Punt d'entrada de l'aplicacio local del PC LAB."""
from __future__ import annotations

import argparse
import sqlite3
import sys

from salafatiga.acquisition.plc.source import InProcessSimPlcSource, ModbusTcpPlcSource
from salafatiga.acquisition.variador import InProcessSimVariadorSource, VariadorSource
from salafatiga.config import ConfigError, load_config
from salafatiga.config.models import Config
from salafatiga.logging_setup import setup_logging
from salafatiga.processing import ProcessingPipeline
from salafatiga.services import AcquisitionService, OracleSyncService
from salafatiga.storage import (
    Database,
    OracleDatabase,
    OracleRepository,
    OracleUnavailable,
    StorageRepository,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PC LAB - Sala de fatiga")
    parser.add_argument(
        "--config",
        default=None,
        help="Ruta del fitxer de configuracio YAML (per defecte: config/config.yaml).",
    )
    parser.add_argument("--no-ui", action="store_true", help="Carrega config i SQLite sense obrir Qt.")
    parser.add_argument("--start", action="store_true", help="Inicia l'adquisicio quan s'obri la UI.")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"[CONFIG] {exc}", file=sys.stderr)
        return 2

    log = setup_logging(
        cfg.logging.level,
        cfg.logging.dir,
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
    )

    log.info("==================================================================")
    log.info("  %s", cfg.app.nom_installacio)
    log.info("  Configuracio carregada de: %s", cfg.source_path)
    log.info("==================================================================")
    _log_config_summary(cfg, log)

    db = Database.from_config(cfg)
    try:
        conn = db.open()
    except (OSError, sqlite3.Error) as exc:
        log.error("No s'ha pogut preparar la base de dades SQLite: %s", exc)
        return 3

    repository = StorageRepository(conn)
    if cfg.storage.retention_days > 0:
        repository.purge_by_retention_days(cfg.storage.retention_days)

    log.info(
        "Historic: %s  (flush cada %.1fs, esquema SQLite preparat)",
        cfg.storage.db_path,
        cfg.storage.flush_period_s,
    )
    log.info("Exportacions: %s  (format per defecte: %s)", cfg.export.dir, cfg.export.default_format)
    log.info("Web: %s", f"ON {cfg.web.host}:{cfg.web.port}" if cfg.web.enabled else "OFF")

    oracle_db, sync_service = _start_oracle_sync(cfg, repository, log)

    if args.no_ui:
        if sync_service is not None:
            sync_service.stop()
        if oracle_db is not None:
            oracle_db.close()
        db.close()
        return 0

    try:
        from PySide6.QtWidgets import QApplication
        from salafatiga.ui import MainWindow
    except ImportError as exc:
        log.error("No es pot arrencar la UI Qt. Instal.la PySide6: %s", exc)
        if sync_service is not None:
            sync_service.stop()
        if oracle_db is not None:
            oracle_db.close()
        db.close()
        return 4

    app = QApplication.instance() or QApplication(sys.argv[:1])
    service = _build_acquisition_service(cfg)
    window = MainWindow(cfg, repository, service, sync_service=sync_service)
    window.show()
    if args.start:
        window.start_acquisition()

    try:
        return int(app.exec())
    finally:
        service.close()
        if sync_service is not None:
            sync_service.stop()
        if oracle_db is not None:
            oracle_db.close()
        db.close()


def _start_oracle_sync(
    cfg: Config,
    repository: StorageRepository,
    log,
) -> tuple[OracleDatabase | None, OracleSyncService | None]:
    """Obre Oracle (si està habilitat) i arrenca el servei de sync.

    Retorna ``(oracle_db, sync_service)``. Si Oracle no és accessible a
    l'arrencada, retorna ``(None, None)`` i el PC LAB continua treballant
    només amb el buffer SQLite local — el sync es podrà reactivar
    reiniciant l'app un cop IT confirmi la connectivitat.
    """
    if not cfg.oracle.enabled:
        log.info("Oracle: OFF (només SQLite local)")
        return None, None

    try:
        oracle_db = OracleDatabase(cfg.oracle, equips=cfg.variador.equips)
        pool = oracle_db.open()
    except OracleUnavailable as exc:
        log.warning("Oracle: ON però no accessible (%s). Es continua només amb SQLite.", exc)
        return None, None

    log.info("Oracle: ON  | user=%s  pool=%d..%d", cfg.oracle.user, cfg.oracle.pool_min, cfg.oracle.pool_max)
    if not cfg.sync.enabled:
        log.info("Sync: OFF (oracle obert però el push periòdic està desactivat)")
        return oracle_db, None

    remote = OracleRepository(pool)
    sync = OracleSyncService(repository, remote, cfg.sync)
    sync.start()
    return oracle_db, sync


def _log_config_summary(cfg: Config, log) -> None:
    if cfg.variador.enabled:
        log.info(
            "Variador: ON  | mode=%s  port=%s  id=%s  %d %d%s%d  timeout=%.2fs  poll=%.2fs",
            cfg.variador.mode,
            cfg.variador.port,
            cfg.variador.slave_id,
            cfg.variador.baudrate,
            cfg.variador.bytesize,
            cfg.variador.parity,
            cfg.variador.stopbits,
            cfg.variador.timeout_s,
            cfg.variador.poll_period_s,
        )
        for equip in cfg.variador.equips:
            log.info("    equip %-12s @%d  %s", equip.id, equip.addr, equip.descripcio)
    else:
        log.info("Variador: OFF")

    if cfg.plc.enabled:
        log.info(
            "PLC: ON  | mode=%s  %s:%d  unit=%d  timeout=%.2fs  poll=%.2fs",
            cfg.plc.mode,
            cfg.plc.host,
            cfg.plc.port,
            cfg.plc.unit_id,
            cfg.plc.timeout_s,
            cfg.plc.poll_period_s,
        )
    else:
        log.info("PLC: OFF")


def _build_acquisition_service(cfg: Config) -> AcquisitionService:
    sources = []
    equip_id = cfg.ui.equip_per_defecte or (cfg.variador.equips[0].id if cfg.variador.equips else "PLC")

    if cfg.variador.enabled:
        if cfg.variador.mode == "sim_inproc":
            sources.append(InProcessSimVariadorSource(cfg.variador))
        else:
            sources.append(VariadorSource(cfg.variador))
    if cfg.plc.enabled:
        if cfg.plc.mode == "sim_inproc":
            sources.append(InProcessSimPlcSource(equip_id=equip_id))
        else:
            sources.append(ModbusTcpPlcSource(cfg.plc, equip_id=equip_id))

    return AcquisitionService(sources, pipeline=ProcessingPipeline())


if __name__ == "__main__":
    raise SystemExit(main())
