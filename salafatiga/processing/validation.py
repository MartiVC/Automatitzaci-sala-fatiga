"""Validacio basica de lectures normalitzades."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace

from salafatiga.core import variables
from salafatiga.core.datamodel import Quality, Reading
from salafatiga.core.variables import VarKind


@dataclass(slots=True)
class ValidationConfig:
    """Parametres de validacio de dades."""

    max_age_s: float = 10.0
    max_jump_abs: dict[str, float] = field(default_factory=dict)

    @staticmethod
    def defaults() -> "ValidationConfig":
        return ValidationConfig(
            max_age_s=10.0,
            max_jump_abs={
                variables.V_FREQ_HZ: 20.0,
                variables.V_INTENSITAT: 50.0,
                variables.V_PRESSIO: 10.0,
                variables.V_T_RODAMENT_DE: 15.0,
                variables.V_T_RODAMENT_NDE: 15.0,
                variables.V_T_MOTOR: 20.0,
                variables.V_T_FLUID: 15.0,
                variables.V_T_AMBIENT: 10.0,
                variables.V_VIB_DE: 5.0,
                variables.V_VIB_NDE: 5.0,
                variables.V_RPM_MOTOR: 1000.0,
            },
        )


_QUALITY_RANK = {
    Quality.GOOD: 0,
    Quality.UNCERTAIN: 1,
    Quality.STALE: 2,
    Quality.BAD: 3,
}


class ReadingValidator:
    """Valida rangs, antiguitat i salts sobtats."""

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self.config = config or ValidationConfig.defaults()
        self._last_good: dict[tuple[str, str], Reading] = {}

    def validate(self, reading: Reading, *, now: float | None = None) -> Reading:
        now = time.time() if now is None else now
        notes: list[str] = [reading.note] if reading.note else []

        try:
            var_def = variables.get(reading.variable_id)
        except KeyError:
            return replace(
                reading,
                quality=Quality.BAD,
                note=_join_notes(notes, "Variable no definida al cataleg"),
            )

        quality = reading.quality

        if reading.value is None:
            quality = _worse(quality, Quality.BAD)
            notes.append("Valor absent")
        elif not math.isfinite(float(reading.value)):
            quality = _worse(quality, Quality.BAD)
            notes.append("Valor no finit")
        else:
            value = float(reading.value)
            if var_def.valid_min is not None and value < var_def.valid_min:
                quality = _worse(quality, Quality.BAD)
                notes.append(f"Valor per sota del rang valid ({value:g} < {var_def.valid_min:g})")
            if var_def.valid_max is not None and value > var_def.valid_max:
                quality = _worse(quality, Quality.BAD)
                notes.append(f"Valor per sobre del rang valid ({value:g} > {var_def.valid_max:g})")
            if var_def.kind is VarKind.DIGITAL and value not in (0.0, 1.0):
                quality = _worse(quality, Quality.BAD)
                notes.append("Variable digital fora de 0/1")

            if quality is not Quality.BAD:
                jump_note = self._jump_note(reading, value)
                if jump_note:
                    quality = _worse(quality, Quality.UNCERTAIN)
                    notes.append(jump_note)

        if now - reading.ts > self.config.max_age_s:
            quality = _worse(quality, Quality.STALE)
            notes.append(f"Lectura antiga ({now - reading.ts:.1f}s)")

        validated = replace(reading, quality=quality, note=_join_notes(notes))
        if validated.is_usable:
            self._last_good[(validated.equip_id, validated.variable_id)] = validated
        return validated

    def validate_many(self, readings: list[Reading], *, now: float | None = None) -> list[Reading]:
        current_time = time.time() if now is None else now
        return [self.validate(reading, now=current_time) for reading in readings]

    def _jump_note(self, reading: Reading, value: float) -> str:
        max_jump = self.config.max_jump_abs.get(reading.variable_id)
        if max_jump is None:
            return ""
        previous = self._last_good.get((reading.equip_id, reading.variable_id))
        if previous is None or previous.value is None:
            return ""
        delta = abs(value - previous.value)
        if delta > max_jump:
            return f"Salt sobtat ({delta:g} > {max_jump:g})"
        return ""


def _worse(a: Quality, b: Quality) -> Quality:
    return a if _QUALITY_RANK[a] >= _QUALITY_RANK[b] else b


def _join_notes(notes: list[str], extra: str = "") -> str:
    clean = [n for n in notes if n]
    if extra:
        clean.append(extra)
    return "; ".join(clean)
