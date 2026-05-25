"""Mapa de registres Modbus del variador SPEEDRIVE V2.

Basat en el document «Protocolo MODBUS — Equipos SPEEDRIVE V2» (ESPA, v1).

Característiques de la comunicació (només lectura):
    - Capa física: RS-485, 9600, N, 8, 1.
    - Codificació big-endian, registres de 16 bits, esclau ID = 1 per defecte.
    - L'escriptura per Modbus RTU està anul·lada pel fabricant.

Mapa d'adreces (notació del document → adreça 0-based per a la trama):

    ===========  =========  ===================================  ==================
    Rang doc.    Funció     Tipus                                Conversió a addr
    ===========  =========  ===================================  ==================
    @0XXXX       01         Sortides digitals (coils)            addr = reg - 1
    @1XXXX       02         Entrades digitals (discrete inputs)  addr = reg - 10001
    @3XXXX       04         Registres d'entrada (paràmetres)     addr = reg - 30001
    ===========  =========  ===================================  ==================

Els equips d'un grup de pressió s'identifiquen per l'adreça @0..@7 dins el grup;
els registres «comunicats» porten aquest índex al nom (``ADDRx``).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

#: Nombre màxim d'equips (@0..@7) que pot tenir un grup de pressió.
MAX_EQUIPS = 8


# --------------------------------------------------------------------------- #
#  Conversió d'adreces  (document 3XXXX / 1XXXX / 0XXXX  →  adreça de trama)
# --------------------------------------------------------------------------- #
class RegSpace(enum.Enum):
    """Espai d'adreçament Modbus i la seva funció de lectura associada."""

    COIL = 1            # @0XXXX  — funció 01 (sortides digitals)
    DISCRETE_INPUT = 2  # @1XXXX  — funció 02 (entrades digitals)
    INPUT_REGISTER = 4  # @3XXXX  — funció 04 (registres d'entrada / paràmetres)


_BASE = {RegSpace.COIL: 1, RegSpace.DISCRETE_INPUT: 10001, RegSpace.INPUT_REGISTER: 30001}
_FUNCTION = {RegSpace.COIL: 1, RegSpace.DISCRETE_INPUT: 2, RegSpace.INPUT_REGISTER: 4}


def doc_to_addr(doc_reg: int) -> tuple[RegSpace, int, int]:
    """Converteix una adreça del document a ``(espai, addr_0based, codi_funció)``.

    Llança :class:`ValueError` si el número no encaixa en cap dels rangs coneguts.
    """
    if 1 <= doc_reg <= 9999:
        space = RegSpace.COIL
    elif 10001 <= doc_reg <= 19999:
        space = RegSpace.DISCRETE_INPUT
    elif 30001 <= doc_reg <= 39999:
        space = RegSpace.INPUT_REGISTER
    else:
        raise ValueError(f"Registre fora dels rangs Modbus coneguts del document: {doc_reg}")
    return space, doc_reg - _BASE[space], _FUNCTION[space]


def addr_of(doc_reg: int) -> int:
    """Adreça 0-based de trama per a un registre del document."""
    return doc_to_addr(doc_reg)[1]


def function_of(doc_reg: int) -> int:
    """Codi de funció Modbus de lectura per a un registre del document."""
    return doc_to_addr(doc_reg)[2]


def space_of(doc_reg: int) -> RegSpace:
    """Espai d'adreçament Modbus al qual pertany un registre del document."""
    return doc_to_addr(doc_reg)[0]


# --------------------------------------------------------------------------- #
#  Registres @3XXXX globals del variador (no indexats per equip)
# --------------------------------------------------------------------------- #
REG_15V = 30007            # tensió de control 15 V (exemple 6 del document)
REG_TENSION_BUS = 30008    # tensió del bus de contínua (VBUS) (exemple 6 del document)
REG_ALARMES = 30049        # codi d'alarma actiu: 0 = cap; 17..41 = codi (veure ALARM_CODES)


# --------------------------------------------------------------------------- #
#  Sortides digitals @0XXXX (funció 01) — informatives
# --------------------------------------------------------------------------- #
COIL_LED_FAULT = 1     # LED vermell superior de la caràtula
COIL_LED_RUN = 2       # LED verd intermedi de la caràtula
COIL_LED_LINE = 3      # LED verd inferior de la caràtula
COIL_RELE_ALARMA = 6   # sortida lliure de potència per a connexió d'alarma


# --------------------------------------------------------------------------- #
#  Registres «comunicats» indexats per adreça d'equip @x   (x = 0..7)
# --------------------------------------------------------------------------- #
#  @3XXXX (input registers, funció 04):
#      INTENSIDAD_ADDRx = 30013 + 2*x   (intensitat motor de l'equip @x)
#      PRESION_ADDRx    = 30014 + 2*x   (pressió transductor de l'equip @x)
#      HZ_MOTOR_ADDRx   = 30029 +   x   (freqüència motor de l'equip @x)
#  @1XXXX (discrete inputs, funció 02):
#      ALARMA_ADDRx     = 10021 + 3*x   (equip @x en alarma)
#      AUTO_ADDRx       = 10022 + 3*x   (equip @x en automàtic/manual)
#      BUS_485_ADDx     = 10023 + 3*x   (equip @x NO comunica pel RS-485 intern)
def _check_addr(addr_equip: int) -> None:
    if not 0 <= addr_equip < MAX_EQUIPS:
        raise ValueError(f"Adreça d'equip fora de rang (0..{MAX_EQUIPS - 1}): {addr_equip}")


def reg_intensitat(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 30013 + 2 * addr_equip


def reg_pressio(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 30014 + 2 * addr_equip


def reg_hz_motor(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 30029 + addr_equip


def reg_alarma_equip(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 10021 + 3 * addr_equip


def reg_auto_manual(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 10022 + 3 * addr_equip


def reg_bus485_nok(addr_equip: int) -> int:
    _check_addr(addr_equip)
    return 10023 + 3 * addr_equip


@dataclass(frozen=True, slots=True)
class EquipRegisterSet:
    """Conjunt de registres del document associats a un equip @x del grup.

    Exposa les adreces «del document» (30013, 10021...); per obtenir l'adreça de
    trama o el codi de funció, passa-les per :func:`addr_of` / :func:`function_of`.
    """

    addr_equip: int

    def __post_init__(self) -> None:
        _check_addr(self.addr_equip)

    @property
    def intensitat(self) -> int:
        return reg_intensitat(self.addr_equip)

    @property
    def pressio(self) -> int:
        return reg_pressio(self.addr_equip)

    @property
    def hz_motor(self) -> int:
        return reg_hz_motor(self.addr_equip)

    @property
    def alarma(self) -> int:
        return reg_alarma_equip(self.addr_equip)

    @property
    def auto_manual(self) -> int:
        return reg_auto_manual(self.addr_equip)

    @property
    def bus485_nok(self) -> int:
        return reg_bus485_nok(self.addr_equip)


# --------------------------------------------------------------------------- #
#  Excepcions Modbus (resposta amb funció | 0x80 i codi d'error)
# --------------------------------------------------------------------------- #
class ModbusError(enum.IntEnum):
    """Codis d'excepció Modbus que pot retornar el SPEEDRIVE V2."""

    INVALID_FUNCTION = 1  # la funció rebuda no està permesa
    INVALID_ADDRESS = 2   # adreça fora de rang
    INVALID_DATA = 3      # la dada conté un valor no vàlid
    DEVICE_FAILURE = 4    # el controlador no respon
    ACK = 5               # funció acceptada i en procés
    BUSY = 6              # missatge rebut però no es pot processar ara


# --------------------------------------------------------------------------- #
#  Codis d'alarma del registre 30049
# --------------------------------------------------------------------------- #
#  El valor del registre 30049 NO és un camp de bits: és un codi enter amb el
#  significat següent (segons la taula del document). 0 (i valors no llistats)
#  s'interpreten com «sense alarma».
ALARM_CODES: dict[int, str] = {
    17: "Paràmetres incorrectes (cal actualitzar a paràmetres/versions de fàbrica)",
    18: "Curtcircuit al motor per consum excessiu",
    19: "Temperatura excessiva al mòdul IGBT (possible consum excessiu)",
    20: "UnderVoltage: tensió de control IGBT per sota del mínim",
    21: "Sobreintensitat: consum excessiu al motor",
    22: "Temperatura interna excessiva",
    23: "Sonda: no es detecta lectura del transductor de pressió",
    24: "Problemes en la regulació de pressió",
    25: "V20: error de tensió interna",
    26: "Derivació a terra: detecció de fuita a terra",
    27: "RFU0 (alarma reservada, no utilitzada)",
    28: "VBusMax: tensió excessiva al bus de contínua",
    29: "VBusMin: tensió mínima operativa del bus de contínua",
    30: "Diferència d'intensitat entre fases del motor excessiva",
    31: "NMI_IGBT: alarma al mòdul IGBT (sobreconsum, temperatura o tensió incorrecta)",
    32: "RFU1 (alarma reservada, no utilitzada)",
    33: "Treball en sec: no es detecta consum al motor (treballant sense aigua)",
    34: "Temperatura del motor excessiva",
    35: "Intensitat màxima instantània: sobreconsum al motor",
    36: "Falta d'aigua (entrada AUX1)",
    37: "Com485: error de comunicació RS-485 de regulació",
    38: "FaseEntrada: problema en alguna fase d'entrada (no connectada o desequilibrada) [T2/T4]",
    39: "Comunicació interna entre microprocessadors CPU i motor",
    40: "Versions: incoherència entre versió de CPU i versió de motor",
    41: "Canonada rebentada: pèrdua de pressió per canonada rebentada",
}


def alarm_text(code: int) -> str:
    """Descripció llegible d'un codi d'alarma del registre 30049.

    Retorna ``"Sense alarma"`` per a 0; ``"Alarma desconeguda (codi N)"`` si el
    codi no és al catàleg.
    """
    if code == 0:
        return "Sense alarma"
    return ALARM_CODES.get(code, f"Alarma desconeguda (codi {code})")
