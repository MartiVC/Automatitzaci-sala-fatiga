"""Generador de senyals simulats del PLC."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class PlcSignalSimulator:
    """Model simple de temperatures, vibracions i rpm per a proves."""

    seed: int | None = None
    anomaly: str = "none"
    _t0: float = field(default_factory=time.time)
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def snapshot(self) -> dict[str, float]:
        elapsed = time.time() - self._t0
        return {
            "t_rodament_de": self.value("t_rodament_de", elapsed),
            "t_rodament_nde": self.value("t_rodament_nde", elapsed),
            "t_motor": self.value("t_motor", elapsed),
            "t_ambient": self.value("t_ambient", elapsed),
            "t_fluid": self.value("t_fluid", elapsed),
            "vib_de": self.value("vib_de", elapsed),
            "vib_nde": self.value("vib_nde", elapsed),
            "rpm_motor": self.value("rpm_motor", elapsed),
        }

    def value(self, variable_id: str, elapsed: float | None = None) -> float:
        elapsed = time.time() - self._t0 if elapsed is None else elapsed
        wave = math.sin(elapsed / 30.0)

        if variable_id.startswith("t_"):
            base = {
                "t_ambient": 24.0,
                "t_fluid": 31.0,
                "t_motor": 48.0,
                "t_rodament_de": 42.0,
                "t_rodament_nde": 40.0,
            }.get(variable_id, 35.0)
            drift = 0.0
            if self.anomaly == "heat" and variable_id in {"t_motor", "t_rodament_de"}:
                drift = min(elapsed * 0.03, 35.0)
            return round(base + drift + 1.5 * wave + self._rng.uniform(-0.2, 0.2), 2)

        if variable_id.startswith("vib_"):
            spike = 0.0
            if self.anomaly == "vibration" and variable_id == "vib_de":
                spike = 3.5 + 1.5 * max(0.0, math.sin(elapsed / 5.0))
            return round(1.8 + spike + 0.3 * wave + self._rng.uniform(-0.05, 0.05), 2)

        if variable_id == "rpm_motor":
            return round(2850 + 20 * wave + self._rng.uniform(-5, 5), 0)

        return 0.0
