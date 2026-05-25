"""Mapa de registres exposats pel PLC al PC LAB."""
from __future__ import annotations

from dataclasses import dataclass

from salafatiga.core import units, variables


@dataclass(frozen=True, slots=True)
class PlcTag:
    """Tag analogic exposat pel PLC com a input register."""

    variable_id: str
    register: int
    scale: float
    unit: str
    name: str

    @property
    def addr(self) -> int:
        return self.register - 30001

    def raw_to_value(self, raw: int) -> float:
        return raw * self.scale

    def value_to_raw(self, value: float) -> int:
        return int(round(value / self.scale))


PLC_TAGS: tuple[PlcTag, ...] = (
    PlcTag(variables.V_T_RODAMENT_DE, 30001, 0.1, units.DEG_C, "Temp. rodament DE"),
    PlcTag(variables.V_T_RODAMENT_NDE, 30002, 0.1, units.DEG_C, "Temp. rodament NDE"),
    PlcTag(variables.V_T_MOTOR, 30003, 0.1, units.DEG_C, "Temp. motor"),
    PlcTag(variables.V_T_AMBIENT, 30004, 0.1, units.DEG_C, "Temp. ambient"),
    PlcTag(variables.V_T_FLUID, 30005, 0.1, units.DEG_C, "Temp. fluid"),
    PlcTag(variables.V_VIB_DE, 30006, 0.01, units.MM_S, "Vibració DE RMS"),
    PlcTag(variables.V_VIB_NDE, 30007, 0.01, units.MM_S, "Vibració NDE RMS"),
    PlcTag(variables.V_RPM_MOTOR, 30008, 1.0, units.RPM, "RPM motor"),
)

PLC_TAGS_BY_VARIABLE: dict[str, PlcTag] = {tag.variable_id: tag for tag in PLC_TAGS}


def get_tag(variable_id: str) -> PlcTag:
    try:
        return PLC_TAGS_BY_VARIABLE[variable_id]
    except KeyError:
        raise KeyError(f"Tag PLC desconegut: {variable_id!r}") from None
