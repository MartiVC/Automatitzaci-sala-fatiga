#!/usr/bin/env python3
"""Simulador del PLC de la sala de fatiga (servidor Modbus TCP)."""
from __future__ import annotations

import argparse
import logging
import sys

from salafatiga.acquisition.plc.map import PLC_TAGS
from salafatiga.acquisition.plc.simulation import PlcSignalSimulator
from salafatiga.acquisition.plc.simulator import (
    PlcRegisterImage,
    PlcSimulatorConfig,
    create_server_context,
    run_tcp_server,
    update_context_once,
)
from salafatiga.config import ConfigError, load_config
from salafatiga.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulador PLC Modbus TCP - Sala de fatiga")
    parser.add_argument("--config", default=None, help="Ruta del fitxer YAML de configuració.")
    parser.add_argument("--host", default=None, help="Host/IP d'escolta (per defecte: config.plc.host).")
    parser.add_argument("--port", type=int, default=None, help="Port TCP (per defecte: config.plc.port).")
    parser.add_argument("--unit-id", type=int, default=None, help="Unit/slave id Modbus.")
    parser.add_argument("--update-s", type=float, default=None, help="Període d'actualització dels registres.")
    parser.add_argument("--seed", type=int, default=None, help="Llavor del soroll pseudoaleatori.")
    parser.add_argument(
        "--anomaly",
        choices=("none", "heat", "vibration"),
        default="none",
        help="Anomalia simulada: none, heat o vibration.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="No arrenca el servidor; imprimeix una imatge de registres i surt.",
    )
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

    sim_cfg = PlcSimulatorConfig(
        host=args.host or cfg.plc.host,
        port=args.port or cfg.plc.port,
        unit_id=args.unit_id or cfg.plc.unit_id,
        update_period_s=args.update_s or cfg.plc.poll_period_s,
        anomaly=args.anomaly,
        seed=args.seed,
    )

    if args.once:
        _print_once(sim_cfg)
        return 0

    try:
        run_tcp_server(sim_cfg)
    except KeyboardInterrupt:
        log.info("Simulador PLC aturat per l'usuari")
        return 0
    except Exception as exc:
        logging.getLogger("salafatiga").error("No s'ha pogut arrencar el simulador PLC: %s", exc)
        return 1


def _print_once(cfg: PlcSimulatorConfig) -> None:
    image = PlcRegisterImage(PlcSignalSimulator(seed=cfg.seed, anomaly=cfg.anomaly))
    context = create_server_context(image)
    values = update_context_once(context, image)
    print(f"PLC simulator snapshot | {cfg.host}:{cfg.port} unit={cfg.unit_id} anomaly={cfg.anomaly}")
    for tag in PLC_TAGS:
        raw = values[tag.addr - image.first_addr]
        print(f"{tag.register}  addr={tag.addr:02d}  raw={raw:5d}  {tag.variable_id:<16} {tag.raw_to_value(raw):8.2f} {tag.unit}")


if __name__ == "__main__":
    raise SystemExit(main())
