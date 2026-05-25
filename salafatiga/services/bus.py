"""Bus simple de publicacio per desacoblar adquisicio, storage, alarmes i UI."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from salafatiga.acquisition.base import SourceStatus
from salafatiga.core.datamodel import Event, Reading

ReadingHandler = Callable[[Reading], None]
EventHandler = Callable[[Event], None]
StatusHandler = Callable[[SourceStatus], None]


@dataclass(slots=True)
class SignalBus:
    """Bus in-process basat en callbacks.

    La UI Qt pot subscriure aquests callbacks i reenviar-los a senyals Qt quan
    calgui. Mantindre aquest bus pur facilita tests i simuladors sense QApplication.
    """

    _reading_handlers: list[ReadingHandler] = field(default_factory=list)
    _event_handlers: list[EventHandler] = field(default_factory=list)
    _status_handlers: list[StatusHandler] = field(default_factory=list)

    def on_reading(self, handler: ReadingHandler) -> None:
        self._reading_handlers.append(handler)

    def on_event(self, handler: EventHandler) -> None:
        self._event_handlers.append(handler)

    def on_status(self, handler: StatusHandler) -> None:
        self._status_handlers.append(handler)

    def publish_reading(self, reading: Reading) -> None:
        for handler in list(self._reading_handlers):
            handler(reading)

    def publish_event(self, event: Event) -> None:
        for handler in list(self._event_handlers):
            handler(event)

    def publish_status(self, status: SourceStatus) -> None:
        for handler in list(self._status_handlers):
            handler(status)
