"""Interficies comunes per a fonts d'adquisicio."""
from __future__ import annotations

import enum
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from salafatiga.core.datamodel import Event, Reading


class ConnectionState(enum.Enum):
    """Estat de connexio d'una font de dades."""

    DISABLED = "disabled"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    OK = "ok"
    LOST = "lost"
    ERROR = "error"


@dataclass(slots=True)
class SourceStatus:
    """Estat observable d'una font d'adquisicio."""

    source_id: str
    state: ConnectionState = ConnectionState.DISCONNECTED
    last_ok_ts: float | None = None
    last_error_ts: float | None = None
    consecutive_errors: int = 0
    message: str = ""

    def mark_ok(self, message: str = "") -> None:
        self.state = ConnectionState.OK
        self.last_ok_ts = time.time()
        self.consecutive_errors = 0
        self.message = message

    def mark_error(self, message: str, *, lost_after: int = 1) -> None:
        self.last_error_ts = time.time()
        self.consecutive_errors += 1
        self.state = (
            ConnectionState.LOST
            if self.consecutive_errors >= max(lost_after, 1)
            else ConnectionState.ERROR
        )
        self.message = message


@dataclass(slots=True)
class PollResult:
    """Resultat d'un cicle de lectura d'una font."""

    readings: list[Reading] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    status: SourceStatus | None = None


class DataSource(ABC):
    """Contracte minim que compleixen variador, PLC real i simuladors."""

    source_id: str

    @abstractmethod
    def poll(self) -> PollResult:
        """Executa una lectura i retorna dades normalitzades."""

    def close(self) -> None:
        """Allibera recursos de la font, si en te."""
