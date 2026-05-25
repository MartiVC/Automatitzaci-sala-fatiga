"""Model de dades comú del sistema.

Tota dada que entra al PC LAB (del variador, del PLC o del propi sistema) es
converteix immediatament a un :class:`Reading`. Els canvis d'estat, alarmes i
incidències es modelen com a :class:`Event`. Aquests dos tipus són la moneda de
canvi entre les capes d'adquisició, validació, emmagatzematge, alarmes i UI.

Camps mínims demanats al plec per a cada lectura: timestamp, equip/bomba,
origen de la dada (variador / PLC / sensor / sistema), variable, valor, unitat,
qualitat de dada / estat de comunicació i codi d'alarma o estat si aplica.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass
from typing import Optional

#: Identificador d'"equip" reservat per a esdeveniments globals del sistema.
SISTEMA_EQUIP_ID = "SISTEMA"


# --------------------------------------------------------------------------- #
#  Enumeracions bàsiques
# --------------------------------------------------------------------------- #
class Origin(enum.Enum):
    """D'on prové la dada."""

    VARIADOR = "variador"  # llegit del SPEEDRIVE V2 per Modbus RTU
    PLC = "plc"            # rebut del PLC (sensors externs ja concentrats)
    SISTEMA = "sistema"    # generat pel propi PC LAB (estat de comunicació, etc.)


class Quality(enum.Enum):
    """Qualitat / fiabilitat de la dada (inspirat en la "quality" d'OPC)."""

    GOOD = "good"            # dada vàlida i fresca
    UNCERTAIN = "uncertain"  # dada sospitosa (fora de rang tou, salt gran...)
    STALE = "stale"          # dada antiga (no s'ha pogut refrescar)
    BAD = "bad"              # dada no vàlida (error de comunicació o decodificació)


class EventType(enum.Enum):
    """Tipus d'esdeveniment registrat a l'històric."""

    ALARM_SET = "alarm_set"          # s'activa una alarma
    ALARM_CLEAR = "alarm_clear"      # es desactiva una alarma
    WARNING_SET = "warning_set"      # s'activa un avís (llindar tou)
    WARNING_CLEAR = "warning_clear"  # es desactiva l'avís
    STATE_CHANGE = "state_change"    # canvi d'estat d'un equip (auto/manual, run/stop...)
    COMM_LOST = "comm_lost"          # pèrdua de comunicació amb una font
    COMM_RESTORED = "comm_restored"  # recuperació de comunicació
    SYSTEM = "system"                # esdeveniment del sistema (arrencada, aturada, error intern)


class Severity(enum.IntEnum):
    """Severitat d'un esdeveniment (ordenable)."""

    INFO = 0
    WARNING = 1
    ALARM = 2
    CRITICAL = 3


# --------------------------------------------------------------------------- #
#  Lectura (sèrie temporal)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Reading:
    """Una mesura puntual d'una variable d'un equip en un instant donat.

    Attributes:
        ts: marca temporal UNIX (segons, UTC) de la lectura.
        equip_id: identificador de l'equip/bomba (p. ex. ``"GRUP1_B1"``).
        origin: origen de la dada (:class:`Origin`).
        variable_id: identificador de la variable dins el catàleg
            (:mod:`salafatiga.core.variables`), p. ex. ``"intensitat"``.
        value: valor en unitats d'enginyeria (després d'escala/offset).
            ``None`` si la lectura ha fallat (en aquest cas ``quality == BAD``).
        unit: unitat del valor (p. ex. ``"A"``, ``"bar"``, ``"Hz"``, ``"°C"``).
        quality: qualitat de la dada (:class:`Quality`).
        raw: valor cru llegit del dispositiu (registre Modbus...), si escau.
        status_code: codi d'estat o d'alarma associat (p. ex. el valor del
            registre 30049 del variador), si escau.
        note: text lliure opcional (motiu de qualitat dolenta, etc.).
    """

    ts: float
    equip_id: str
    origin: Origin
    variable_id: str
    value: Optional[float]
    unit: str = ""
    quality: Quality = Quality.GOOD
    raw: Optional[int] = None
    status_code: Optional[int] = None
    note: str = ""

    @staticmethod
    def now(
        equip_id: str,
        origin: Origin,
        variable_id: str,
        value: Optional[float],
        *,
        unit: str = "",
        quality: Quality = Quality.GOOD,
        raw: Optional[int] = None,
        status_code: Optional[int] = None,
        note: str = "",
    ) -> "Reading":
        """Crea una :class:`Reading` amb ``ts = time.time()``."""
        return Reading(
            time.time(), equip_id, origin, variable_id, value,
            unit=unit, quality=quality, raw=raw, status_code=status_code, note=note,
        )

    @property
    def is_usable(self) -> bool:
        """Cert si la lectura té valor i una qualitat acceptable per a tendències."""
        return self.value is not None and self.quality in (Quality.GOOD, Quality.UNCERTAIN)


# --------------------------------------------------------------------------- #
#  Esdeveniment (alarmes, estats, incidències)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Event:
    """Un esdeveniment puntual: canvi d'estat, alarma, incidència de comunicació...

    Attributes:
        ts: marca temporal UNIX (segons, UTC).
        equip_id: equip afectat, o :data:`SISTEMA_EQUIP_ID` per esdeveniments globals.
        origin: origen (:class:`Origin`).
        type: tipus d'esdeveniment (:class:`EventType`).
        severity: severitat (:class:`Severity`).
        code: codi intern de l'esdeveniment/alarma (p. ex. del catàleg d'alarmes).
        message: descripció llegible.
        variable_id: variable relacionada, si escau.
        value: valor que ha disparat l'esdeveniment, si escau.
    """

    ts: float
    equip_id: str
    origin: Origin
    type: EventType
    severity: Severity
    code: str
    message: str
    variable_id: Optional[str] = None
    value: Optional[float] = None

    @staticmethod
    def now(
        equip_id: str,
        origin: Origin,
        type: EventType,
        severity: Severity,
        code: str,
        message: str,
        *,
        variable_id: Optional[str] = None,
        value: Optional[float] = None,
    ) -> "Event":
        """Crea un :class:`Event` amb ``ts = time.time()``."""
        return Event(
            time.time(), equip_id, origin, type, severity, code, message,
            variable_id=variable_id, value=value,
        )
