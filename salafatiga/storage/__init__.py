"""Persistencia historica: SQLite local (buffer) i Oracle corporatiu."""

from .database import Database, initialize_database, open_connection
from .oracle_database import OracleDatabase, OracleUnavailable
from .oracle_repository import OracleRepository
from .read_facade import ReadFacade
from .repository import MeasurementFilter, StorageRepository

__all__ = [
    "Database",
    "MeasurementFilter",
    "OracleDatabase",
    "OracleRepository",
    "OracleUnavailable",
    "ReadFacade",
    "StorageRepository",
    "initialize_database",
    "open_connection",
]
