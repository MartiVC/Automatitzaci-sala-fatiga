"""Configuració del sistema de logs intern de l'aplicació.

Escriu logs a consola i a un fitxer rotatiu sota el directori configurat (per
defecte ``logs/``). Hi ha un únic logger arrel, ``salafatiga``; cada mòdul ha
d'obtenir el seu logger amb ``logging.getLogger(__name__)`` o amb
:func:`get_logger`.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

ROOT_LOGGER_NAME = "salafatiga"

_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(
    level: str = "INFO",
    log_dir: str | Path = "logs",
    *,
    max_bytes: int = 5_000_000,
    backup_count: int = 10,
    filename: str = "salafatiga.log",
) -> logging.Logger:
    """Configura (una sola vegada) el logger arrel de l'aplicació i el retorna.

    Crides posteriors no tornen a configurar res; només retornen el logger.
    """
    global _configured
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    logger.propagate = False
    fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        d = Path(log_dir)
        d.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            d / filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:  # p. ex. directori no escrivible
        logger.warning("No s'ha pogut obrir el fitxer de log (%s): %s", log_dir, exc)

    _configured = True
    logger.debug("Logging inicialitzat (level=%s, dir=%s)", level, log_dir)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Retorna un logger fill del logger arrel de l'aplicació.

    ``get_logger("acquisition.variador")`` → logger ``salafatiga.acquisition.variador``.
    """
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
