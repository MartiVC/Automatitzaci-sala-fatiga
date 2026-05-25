"""Simulador in-process del variador SPEEDRIVE V2."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from salafatiga.acquisition.base import DataSource, PollResult, SourceStatus
from salafatiga.acquisition.variador import registers
from salafatiga.config.models import VariadorConfig
from salafatiga.core import variables
from salafatiga.core.datamodel import Origin, Reading


@dataclass(slots=True)
class VariadorSignalSimulator:
    """Genera valors plausibles del variador per a proves fora del laboratori."""

    seed: int | None = None
    anomaly: str = "none"
    _t0: float = field(default_factory=time.time)
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def snapshot(self, addr: int) -> dict[str, float | int | bool]:
        elapsed = time.time() - self._t0
        phase = addr * 0.8
        wave = math.sin(elapsed / 25.0 + phase)
        small = self._rng.uniform(-0.15, 0.15)

        freq = max(0.0, 42.0 + 8.0 * wave + small)
        pressure = max(0.0, 5.0 + 1.2 * math.sin(elapsed / 33.0 + phase) + small)
        intensity = max(0.0, 8.0 + 2.5 * wave + self._rng.uniform(-0.3, 0.3))
        alarm_code = 0
        if self.anomaly == "dry_run" and int(elapsed) % 120 > 80:
            alarm_code = 33
            pressure = max(0.5, pressure - 3.0)
            intensity = max(0.5, intensity - 5.0)

        return {
            variables.V_INTENSITAT: round(intensity, 2),
            variables.V_PRESSIO: round(pressure, 2),
            variables.V_FREQ_HZ: round(freq, 2),
            variables.V_ALARMA_CODI: alarm_code,
            variables.V_ESTAT_ALARMA: alarm_code != 0,
            variables.V_ESTAT_AUTO_MAN: True,
            variables.V_COMM_485_NOK: False,
        }


class InProcessSimVariadorSource(DataSource):
    """Font de dades simulada del variador sense RS-485."""

    source_id = "variador"

    def __init__(
        self,
        cfg: VariadorConfig,
        *,
        seed: int | None = None,
        anomaly: str = "none",
    ) -> None:
        self.cfg = cfg
        self.status = SourceStatus(self.source_id)
        self._simulator = VariadorSignalSimulator(seed=seed, anomaly=anomaly)

    def poll(self) -> PollResult:
        readings: list[Reading] = []
        for equip in self.cfg.equips:
            snapshot = self._simulator.snapshot(equip.addr)
            readings.extend(
                [
                    self._analog(equip.id, variables.V_INTENSITAT, snapshot[variables.V_INTENSITAT]),
                    self._analog(equip.id, variables.V_PRESSIO, snapshot[variables.V_PRESSIO]),
                    self._analog(equip.id, variables.V_FREQ_HZ, snapshot[variables.V_FREQ_HZ]),
                    self._code(equip.id, int(snapshot[variables.V_ALARMA_CODI])),
                    self._digital(equip.id, variables.V_ESTAT_ALARMA, bool(snapshot[variables.V_ESTAT_ALARMA])),
                    self._digital(equip.id, variables.V_ESTAT_AUTO_MAN, bool(snapshot[variables.V_ESTAT_AUTO_MAN])),
                    self._digital(equip.id, variables.V_COMM_485_NOK, bool(snapshot[variables.V_COMM_485_NOK])),
                ]
            )
        self.status.mark_ok(f"{len(readings)} lectures simulades")
        return PollResult(readings=readings, status=self.status)

    def _analog(self, equip_id: str, variable_id: str, value: float | int | bool) -> Reading:
        var = variables.get(variable_id)
        numeric = float(value)
        return Reading.now(
            equip_id,
            Origin.VARIADOR,
            variable_id,
            numeric,
            unit=var.unit,
            raw=int(round(numeric)),
        )

    def _code(self, equip_id: str, code: int) -> Reading:
        var = variables.get(variables.V_ALARMA_CODI)
        return Reading.now(
            equip_id,
            Origin.VARIADOR,
            variables.V_ALARMA_CODI,
            float(code),
            unit=var.unit,
            raw=code,
            status_code=code,
            note=registers.alarm_text(code),
        )

    def _digital(self, equip_id: str, variable_id: str, value: bool) -> Reading:
        var = variables.get(variable_id)
        raw = int(value)
        return Reading.now(equip_id, Origin.VARIADOR, variable_id, float(raw), unit=var.unit, raw=raw)
