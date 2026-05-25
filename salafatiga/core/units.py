"""Unitats i conversió de valors crus (raw) a unitats d'enginyeria.

El protocol Modbus del SPEEDRIVE V2 lliura registres de 16 bits sense indicar
el factor d'escala. De moment es registra el valor cru i s'aplica una conversió
lineal ``valor = raw * scale + offset`` definida per variable al catàleg
(:mod:`salafatiga.core.variables`). Quan es disposi dels factors reals només cal
ajustar aquesta taula, sense tocar la resta del sistema.
"""
from __future__ import annotations

# Símbols d'unitat. Cadenes lliures, però centralitzades aquí per coherència.
A = "A"        # ampere (intensitat)
BAR = "bar"    # bar (pressió)
HZ = "Hz"      # hertz (freqüència de treball del motor)
DEG_C = "°C"   # grau Celsius (temperatures)
MM_S = "mm/s"  # mil·límetres per segon (vibració: RMS de velocitat, ISO 10816)
G = "g"        # acceleració de la gravetat (vibració amb acceleròmetre)
RPM = "rpm"    # revolucions per minut
V = "V"        # volt
PCT = "%"      # percentatge
COUNT = "u"    # comptador / adimensional
CODE = ""      # codi (estat o alarma): sense unitat


def raw_to_eng(raw: float, scale: float = 1.0, offset: float = 0.0) -> float:
    """Converteix un valor cru a unitats d'enginyeria: ``raw * scale + offset``."""
    return raw * scale + offset


def eng_to_raw(value: float, scale: float = 1.0, offset: float = 0.0) -> float:
    """Conversió inversa de :func:`raw_to_eng` (útil per a simuladors i tests)."""
    if scale == 0:
        raise ValueError("scale no pot ser 0")
    return (value - offset) / scale
