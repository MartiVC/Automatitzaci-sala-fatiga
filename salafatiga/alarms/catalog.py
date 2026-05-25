"""Cataleg d'alarmes del sistema."""
from __future__ import annotations

from dataclasses import dataclass

from salafatiga.acquisition.variador.registers import ALARM_CODES
from salafatiga.core.datamodel import Severity


@dataclass(frozen=True, slots=True)
class AlarmDefinition:
    code: str
    severity: Severity
    message: str


VFD_ALARMS: dict[int, AlarmDefinition] = {
    code: AlarmDefinition(f"VFD_{code}", Severity.ALARM, message)
    for code, message in ALARM_CODES.items()
}


def vfd_alarm(code: int) -> AlarmDefinition | None:
    return VFD_ALARMS.get(code)


def threshold_code(variable_id: str, level: str) -> str:
    return f"{level.upper()}_{variable_id.upper()}"
