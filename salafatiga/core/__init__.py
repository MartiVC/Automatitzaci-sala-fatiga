"""Nucli comú: model de dades, catàleg de variables i unitats.

Aquests mòduls són la referència transversal que fan servir totes les capes
(adquisició, validació, alarmes, emmagatzematge, UI, web).
"""

from .datamodel import (
    Event,
    EventType,
    Origin,
    Quality,
    Reading,
    Severity,
    SISTEMA_EQUIP_ID,
)

__all__ = [
    "Reading",
    "Event",
    "Origin",
    "Quality",
    "EventType",
    "Severity",
    "SISTEMA_EQUIP_ID",
]
