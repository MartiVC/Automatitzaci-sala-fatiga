"""Catàleg de variables monitoritzades.

Cada variable té un identificador estable (``id``), una unitat, l'origen
previst, la conversió raw→enginyeria i (opcionalment) límits de validació i de
llindars d'avís/alarma. Aquest catàleg és la referència única que fan servir
l'adquisició, la validació, les alarmes, l'emmagatzematge i la UI.

Important: per al PLC, les variables són tags/registres que el PLC ja ha calculat
a partir dels sensors físics. El PC LAB no tracta sensors: només llegeix aquestes
variables ja processades.

Els límits d'avís/alarma definits aquí són valors INICIALS raonables; s'han
d'afinar amb dades reals i amb les potències de cada bomba (2 / 3 / 5,5 / 7,5 HP
segons el plec). Els de vibració prenen com a referència orientativa la norma
ISO 10816 per a màquines petites.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional

from . import units
from .datamodel import Origin


class VarKind(enum.Enum):
    """Naturalesa de la variable, per a tractament i visualització."""

    ANALOG = "analog"    # magnitud contínua (I, P, Hz, T, vibració, rpm...)
    DIGITAL = "digital"  # booleà 0/1 (estat run, auto/manual, comunicació...)
    CODE = "code"        # enter amb significat catalogat (codi d'alarma 30049...)


@dataclass(frozen=True, slots=True)
class VariableDef:
    """Definició d'una variable del catàleg."""

    id: str
    nom: str
    origin: Origin
    kind: VarKind = VarKind.ANALOG
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0
    # Rang físicament possible. Fora d'aquí la dada es marca com a no fiable.
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    # Llindars d'avís (warning) i d'alarma. El motor d'alarmes els fa servir;
    # aquí són purament declaratius.
    warn_min: Optional[float] = None
    warn_max: Optional[float] = None
    alarm_min: Optional[float] = None
    alarm_max: Optional[float] = None
    # True: la variable existeix per cada equip.  False: és global del sistema.
    per_equip: bool = True
    descripcio: str = ""

    def to_eng(self, raw: float) -> float:
        """Aplica escala i offset a un valor cru."""
        return units.raw_to_eng(raw, self.scale, self.offset)


# --------------------------------------------------------------------------- #
#  Identificadors de variable (constants, per evitar strings màgics arreu)
# --------------------------------------------------------------------------- #
# --- Del variador (Modbus RTU) ---
V_FREQ_HZ = "freq_hz"
V_INTENSITAT = "intensitat"
V_PRESSIO = "pressio"
V_ALARMA_CODI = "alarma_codi"            # valor del registre 30049
V_ESTAT_ALARMA = "estat_alarma"          # ALARMA_ADDRx (entrada digital comunicada)
V_ESTAT_AUTO_MAN = "estat_auto_manual"   # AUTO_ADDRx
V_COMM_485_NOK = "comm_485_nok"          # BUS_485_ADDx (1 = NO comunica pel RS-485 intern)

# --- Del PLC (sensors externs ja concentrats) ---
V_T_RODAMENT_DE = "t_rodament_de"        # temperatura rodament costat acoblament (Drive End)
V_T_RODAMENT_NDE = "t_rodament_nde"      # temperatura rodament costat oposat (Non-Drive End)
V_T_MOTOR = "t_motor"                    # temperatura carcassa del motor
V_T_FLUID = "t_fluid"                    # temperatura del fluid bombat
V_T_AMBIENT = "t_ambient"                # temperatura ambient de la sala
V_VIB_DE = "vib_de"                      # vibració al rodament DE (RMS de velocitat)
V_VIB_NDE = "vib_nde"                    # vibració al rodament NDE (RMS de velocitat)
V_RPM_MOTOR = "rpm_motor"                # velocitat de gir del motor

# --- Del sistema (PC LAB) ---
V_COMM_VARIADOR = "comm_variador"        # 1 = comunicació OK amb el variador
V_COMM_PLC = "comm_plc"                  # 1 = comunicació OK amb el PLC


# --------------------------------------------------------------------------- #
#  Catàleg
# --------------------------------------------------------------------------- #
_DEFS: list[VariableDef] = [
    # ----- Variador --------------------------------------------------------- #
    VariableDef(
        V_FREQ_HZ, "Freqüència motor", Origin.VARIADOR, VarKind.ANALOG,
        unit=units.HZ, valid_min=0, valid_max=70,
        descripcio="Freqüència de treball del motor (registre 30029 + ADDRx).",
    ),
    VariableDef(
        V_INTENSITAT, "Intensitat motor", Origin.VARIADOR, VarKind.ANALOG,
        unit=units.A, valid_min=0, valid_max=100,
        descripcio="Intensitat consumida pel motor (registre 30013 + 2·ADDRx).",
    ),
    VariableDef(
        V_PRESSIO, "Pressió", Origin.VARIADOR, VarKind.ANALOG,
        unit=units.BAR, valid_min=0, valid_max=25,
        descripcio="Pressió del transductor connectat al variador (registre 30014 + 2·ADDRx).",
    ),
    VariableDef(
        V_ALARMA_CODI, "Codi d'alarma del variador", Origin.VARIADOR, VarKind.CODE,
        unit=units.CODE, valid_min=0, valid_max=255,
        descripcio="Registre 30049: 0 = cap alarma; 17..41 = codi d'alarma (veure catàleg d'alarmes).",
    ),
    VariableDef(
        V_ESTAT_ALARMA, "Equip en alarma", Origin.VARIADOR, VarKind.DIGITAL,
        unit=units.CODE, valid_min=0, valid_max=1,
        descripcio="ALARMA_ADDRx (entrada digital comunicada): 1 = l'equip @x està en alarma.",
    ),
    VariableDef(
        V_ESTAT_AUTO_MAN, "Mode automàtic/manual", Origin.VARIADOR, VarKind.DIGITAL,
        unit=units.CODE, valid_min=0, valid_max=1,
        descripcio="AUTO_ADDRx (entrada digital comunicada): mode de funcionament de l'equip @x.",
    ),
    VariableDef(
        V_COMM_485_NOK, "Sense comunicació RS-485 (equip)", Origin.VARIADOR, VarKind.DIGITAL,
        unit=units.CODE, valid_min=0, valid_max=1,
        descripcio="BUS_485_ADDx: 1 = l'equip @x NO comunica pel RS-485 intern del grup de bombes.",
    ),

    # ----- PLC (sensors externs) ------------------------------------------- #
    VariableDef(
        V_T_RODAMENT_DE, "Temp. rodament DE", Origin.PLC, VarKind.ANALOG,
        unit=units.DEG_C, valid_min=-20, valid_max=200, warn_max=80, alarm_max=95,
        descripcio="Temperatura del rodament costat acoblament (Drive End).",
    ),
    VariableDef(
        V_T_RODAMENT_NDE, "Temp. rodament NDE", Origin.PLC, VarKind.ANALOG,
        unit=units.DEG_C, valid_min=-20, valid_max=200, warn_max=80, alarm_max=95,
        descripcio="Temperatura del rodament costat oposat (Non-Drive End).",
    ),
    VariableDef(
        V_T_MOTOR, "Temp. motor", Origin.PLC, VarKind.ANALOG,
        unit=units.DEG_C, valid_min=-20, valid_max=200, warn_max=90, alarm_max=110,
        descripcio="Temperatura de la carcassa del motor.",
    ),
    VariableDef(
        V_T_FLUID, "Temp. fluid", Origin.PLC, VarKind.ANALOG,
        unit=units.DEG_C, valid_min=-20, valid_max=150, warn_max=60, alarm_max=80,
        descripcio="Temperatura del fluid bombat.",
    ),
    VariableDef(
        V_T_AMBIENT, "Temp. ambient", Origin.PLC, VarKind.ANALOG,
        unit=units.DEG_C, valid_min=-20, valid_max=80,
        descripcio="Temperatura ambient de la sala de fatiga.",
    ),
    VariableDef(
        V_VIB_DE, "Vibració DE (RMS)", Origin.PLC, VarKind.ANALOG,
        unit=units.MM_S, valid_min=0, valid_max=50, warn_max=4.5, alarm_max=7.1,
        descripcio="Velocitat de vibració RMS al rodament DE (referència orientativa ISO 10816).",
    ),
    VariableDef(
        V_VIB_NDE, "Vibració NDE (RMS)", Origin.PLC, VarKind.ANALOG,
        unit=units.MM_S, valid_min=0, valid_max=50, warn_max=4.5, alarm_max=7.1,
        descripcio="Velocitat de vibració RMS al rodament NDE (referència orientativa ISO 10816).",
    ),
    VariableDef(
        V_RPM_MOTOR, "RPM motor", Origin.PLC, VarKind.ANALOG,
        unit=units.RPM, valid_min=0, valid_max=4000,
        descripcio="Velocitat de gir del motor mesurada pel sensor de rpm.",
    ),

    # ----- Sistema --------------------------------------------------------- #
    VariableDef(
        V_COMM_VARIADOR, "Comunicació variador", Origin.SISTEMA, VarKind.DIGITAL,
        unit=units.CODE, valid_min=0, valid_max=1, per_equip=False,
        descripcio="1 = el PC LAB comunica correctament amb el variador per RS-485.",
    ),
    VariableDef(
        V_COMM_PLC, "Comunicació PLC", Origin.SISTEMA, VarKind.DIGITAL,
        unit=units.CODE, valid_min=0, valid_max=1, per_equip=False,
        descripcio="1 = el PC LAB comunica correctament amb el PLC per Modbus TCP.",
    ),
]

#: Catàleg indexat per id de variable.
VARIABLES: dict[str, VariableDef] = {d.id: d for d in _DEFS}


def get(variable_id: str) -> VariableDef:
    """Retorna la definició d'una variable; KeyError si no existeix al catàleg."""
    try:
        return VARIABLES[variable_id]
    except KeyError:
        raise KeyError(f"Variable desconeguda al catàleg: {variable_id!r}") from None


def by_origin(origin: Origin) -> list[VariableDef]:
    """Variables del catàleg que provenen d'un origen donat."""
    return [d for d in _DEFS if d.origin is origin]


def all_defs() -> list[VariableDef]:
    """Totes les definicions del catàleg, en ordre de declaració."""
    return list(_DEFS)
