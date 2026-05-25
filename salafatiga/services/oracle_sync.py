"""Servei de sincronització del buffer SQLite local cap a Oracle corporatiu.

Funcionament:
    1. Cada ``push_period_s`` segons, llegeix del SQLite local les files de
       ``measurements`` i ``events`` amb ``synced_at IS NULL`` (en lots).
    2. Les insereix a Oracle.
    3. Marca les files com a sincronitzades amb la marca temporal actual.
    4. Cada ``retention_check_period_s`` segons, purga del SQLite les files
       ja sincronitzades més antigues que ``retention_local_days``.

Si Oracle no és accessible, fa *backoff* exponencial sense aturar
l'adquisició: les noves lectures s'acumulen al buffer i s'enviaran quan
torni el servei.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from salafatiga.config.models import SyncConfig
from salafatiga.storage.oracle_database import OracleUnavailable
from salafatiga.storage.oracle_repository import OracleRepository
from salafatiga.storage.repository import StorageRepository

log = logging.getLogger(__name__)


class OracleSyncService:
    """Hilo en background que bolca el buffer SQLite cap a Oracle."""

    def __init__(
        self,
        local: StorageRepository,
        remote: OracleRepository,
        cfg: SyncConfig,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.local = local
        self.remote = remote
        self.cfg = cfg
        self._clock = clock

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_purge = 0.0
        self._backoff = cfg.push_period_s

        # Estat exposat per als logs/UI.
        self.last_push_ts: float | None = None
        self.last_push_ok: bool = True
        self.last_error: str | None = None
        self.measurements_synced_total: int = 0
        self.events_synced_total: int = 0

    # ------------------------------------------------------------------ #
    #  Cicle de vida
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="oracle-sync", daemon=True,
        )
        self._thread.start()
        log.info(
            "Oracle sync: ON  push_period=%.1fs  batch=%d  retention_local=%dd",
            self.cfg.push_period_s,
            self.cfg.batch_size,
            self.cfg.retention_local_days,
        )

    def stop(self, *, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------ #
    #  Bucle principal
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                pushed = self.tick()
                self._on_success()
                # Si hi havia molts pendents, no esperem: tornem a omplir lots.
                if pushed >= self.cfg.batch_size:
                    continue
            except OracleUnavailable as exc:
                self._on_failure(str(exc))
            except Exception as exc:  # noqa: BLE001
                self._on_failure(f"Error inesperat al sync: {exc}")

            self._maybe_purge()
            if self._stop.wait(self._backoff):
                break

    def tick(self) -> int:
        """Fa un cicle: lot de mesures + lot d'esdeveniments. Retorna files enviades."""
        pushed = 0
        pushed += self._push_measurements()
        pushed += self._push_events()
        return pushed

    # ------------------------------------------------------------------ #
    #  Push
    # ------------------------------------------------------------------ #
    def _push_measurements(self) -> int:
        pending = self.local.pending_measurements(limit=self.cfg.batch_size)
        if not pending:
            return 0
        ids = [pid for pid, _ in pending]
        readings = [r for _, r in pending]
        self.remote.add_readings(readings)
        marked = self.local.mark_measurements_synced(ids, ts=self._clock())
        self.measurements_synced_total += marked
        log.debug("Oracle sync: %d mesures enviades.", marked)
        return marked

    def _push_events(self) -> int:
        pending = self.local.pending_events(limit=self.cfg.batch_size)
        if not pending:
            return 0
        ids = [pid for pid, _ in pending]
        events = [e for _, e in pending]
        self.remote.add_events(events)
        marked = self.local.mark_events_synced(ids, ts=self._clock())
        self.events_synced_total += marked
        log.debug("Oracle sync: %d esdeveniments enviats.", marked)
        return marked

    # ------------------------------------------------------------------ #
    #  Retenció local del buffer
    # ------------------------------------------------------------------ #
    def _maybe_purge(self) -> None:
        if self.cfg.retention_local_days <= 0:
            return
        now = self._clock()
        if now - self._last_purge < self.cfg.retention_check_period_s:
            return
        self._last_purge = now
        try:
            meas_n, evt_n = self.local.purge_synced_by_retention_days(
                self.cfg.retention_local_days
            )
            if meas_n or evt_n:
                log.info(
                    "Purga buffer SQLite: %d mesures + %d esdeveniments antics > %dd.",
                    meas_n, evt_n, self.cfg.retention_local_days,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("Error en la purga del buffer SQLite: %s", exc)

    # ------------------------------------------------------------------ #
    #  Backoff
    # ------------------------------------------------------------------ #
    def _on_success(self) -> None:
        self.last_push_ts = self._clock()
        self.last_push_ok = True
        self.last_error = None
        self._backoff = self.cfg.push_period_s

    def _on_failure(self, message: str) -> None:
        self.last_push_ts = self._clock()
        self.last_push_ok = False
        self.last_error = message
        # Backoff exponencial entre push_period_s i backoff_max_s.
        self._backoff = min(self._backoff * 2, self.cfg.backoff_max_s)
        log.warning("Oracle sync: %s (proper intent en %.0fs)", message, self._backoff)
