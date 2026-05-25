"""Adquisició del variador SPEEDRIVE V2 (Modbus RTU sobre RS-485).

Mòduls:
    - ``registers``: mapa de registres del SPEEDRIVE V2 i conversió d'adreces.
    - ``modbus_rtu``: client de baix nivell sobre minimalmodbus.            [pas 3]
    - ``source``:     font de dades que emet Readings/Events del variador.  [pas 3]

Recordatori: l'escriptura per Modbus RTU està anul·lada pel fabricant; aquest
mòdul és exclusivament de lectura.
"""

from . import registers
from .simulation import InProcessSimVariadorSource
from .source import VariadorSource

__all__ = ["InProcessSimVariadorSource", "VariadorSource", "registers"]
