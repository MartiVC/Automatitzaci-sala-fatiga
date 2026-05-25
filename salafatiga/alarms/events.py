"""Helpers per construir esdeveniments d'alarma."""
from __future__ import annotations

from salafatiga.core.datamodel import Event, EventType, Reading, Severity


def event_from_reading(
    reading: Reading,
    event_type: EventType,
    severity: Severity,
    code: str,
    message: str,
) -> Event:
    return Event(
        ts=reading.ts,
        equip_id=reading.equip_id,
        origin=reading.origin,
        type=event_type,
        severity=severity,
        code=code,
        message=message,
        variable_id=reading.variable_id,
        value=reading.value,
    )
