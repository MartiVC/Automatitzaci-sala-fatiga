"""Façana de lectura amb fallback Oracle → SQLite.

El dashboard FastAPI llegeix sempre a través d'aquesta façana:

- Si Oracle està configurat i respon, retorna les dades d'Oracle (font de
  veritat corporativa).
- Si Oracle falla, cau automàticament al SQLite local (les últimes
  ``retention_local_days`` de dades, segons la configuració de sync). Així
  la web no queda cega davant talls de xarxa.

L'estat ``degraded`` queda exposat a través de ``last_error``/``mode`` per a
què la UI pugui mostrar un avís discret.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Iterable

from salafatiga.core.datamodel import Event, Reading
from salafatiga.storage.oracle_repository import OracleRepository
from salafatiga.storage.repository import MeasurementFilter, StorageRepository

log = logging.getLogger(__name__)


class ReadFacade:
    """API de consulta utilitzada pel FastAPI, agnòstica del backend."""

    def __init__(
        self,
        local: StorageRepository,
        remote: OracleRepository | None = None,
        *,
        local_lock: threading.Lock | None = None,
        fallback_cooldown_s: float = 30.0,
    ) -> None:
        self.local = local
        self.remote = remote
        self.local_lock = local_lock or threading.Lock()
        self.fallback_cooldown_s = fallback_cooldown_s

        self._last_remote_error_ts: float = 0.0
        self.last_error: str | None = None

    @property
    def mode(self) -> str:
        if self.remote is None:
            return "local"
        if self.last_error and (time.time() - self._last_remote_error_ts) < self.fallback_cooldown_s:
            return "degraded"
        return "remote"

    # ------------------------------------------------------------------ #
    #  Escriptura — sempre al SQLite local (el sync ja s'encarregarà
    #  d'empènyer-ho a Oracle). Útil per a tests i per a esdeveniments
    #  generats des de la UI/API que han d'entrar a l'històric local.
    # ------------------------------------------------------------------ #
    def add_readings(self, readings):
        with self.local_lock:
            return self.local.add_readings(readings)

    def add_reading(self, reading):
        with self.local_lock:
            return self.local.add_reading(reading)

    def add_events(self, events):
        with self.local_lock:
            return self.local.add_events(events)

    def add_event(self, event):
        with self.local_lock:
            return self.local.add_event(event)

    # ------------------------------------------------------------------ #
    #  Mètodes públics — mateixa firma que StorageRepository
    # ------------------------------------------------------------------ #
    def query_measurements(self, flt: MeasurementFilter | None = None) -> list[Reading]:
        return self._try(
            remote_call=lambda: self.remote.query_measurements(flt),
            local_call=lambda: self.local.query_measurements(flt),
        )

    def latest_measurements(
        self,
        *,
        equip_id: str | None = None,
        variable_ids: Iterable[str] | None = None,
    ) -> dict[tuple[str, str], Reading]:
        return self._try(
            remote_call=lambda: self.remote.latest_measurements(
                equip_id=equip_id, variable_ids=variable_ids
            ),
            local_call=lambda: self.local.latest_measurements(
                equip_id=equip_id, variable_ids=variable_ids
            ),
        )

    def query_events(self, **kwargs) -> list[Event]:
        return self._try(
            remote_call=lambda: self.remote.query_events(**kwargs),
            local_call=lambda: self.local.query_events(**kwargs),
        )

    # ------------------------------------------------------------------ #
    def _try(self, *, remote_call, local_call):
        if self.remote is not None:
            # Si fa poc que Oracle ha fallat, no insistim: anem directament al
            # buffer local i estalviem la latència del timeout.
            cooldown_active = (
                self.last_error is not None
                and (time.time() - self._last_remote_error_ts) < self.fallback_cooldown_s
            )
            if not cooldown_active:
                try:
                    result = remote_call()
                    self.last_error = None
                    return result
                except Exception as exc:  # noqa: BLE001
                    self._last_remote_error_ts = time.time()
                    self.last_error = str(exc)
                    log.warning(
                        "Lectura Oracle ha fallat, faig fallback al SQLite local: %s", exc,
                    )

        with self.local_lock:
            return local_call()
