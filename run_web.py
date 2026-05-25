#!/usr/bin/env python3
"""Dashboard web de consulta remota de l'historic."""
from __future__ import annotations

import argparse
import sys

from salafatiga.config import ConfigError, load_config
from salafatiga.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dashboard web - Sala de fatiga")
    parser.add_argument("--config", default=None, help="Ruta del fitxer YAML de configuracio.")
    parser.add_argument("--host", default=None, help="Host/IP d'escolta.")
    parser.add_argument("--port", type=int, default=None, help="Port TCP.")
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"[CONFIG] {exc}", file=sys.stderr)
        return 2

    if args.host:
        cfg.web.host = args.host
    if args.port:
        cfg.web.port = args.port

    setup_logging(
        cfg.logging.level,
        cfg.logging.dir,
        max_bytes=cfg.logging.max_bytes,
        backup_count=cfg.logging.backup_count,
    )

    try:
        from salafatiga.remote.api import run_server
    except ImportError as exc:
        print(f"[WEB] Falten dependències FastAPI/uvicorn: {exc}", file=sys.stderr)
        return 4

    try:
        run_server(cfg)
    except RuntimeError as exc:
        print(f"[WEB] {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
