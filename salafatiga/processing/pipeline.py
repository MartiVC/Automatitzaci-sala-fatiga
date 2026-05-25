"""Pipeline de validacio i generacio d'esdeveniments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from salafatiga.alarms.engine import AlarmEngine
from salafatiga.core.datamodel import Event, Reading
from salafatiga.processing.validation import ReadingValidator


@dataclass(slots=True)
class PipelineResult:
    readings: list[Reading] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


class ProcessingPipeline:
    """Valida lectures i les passa pel motor d'alarmes."""

    def __init__(
        self,
        validator: ReadingValidator | None = None,
        alarm_engine: AlarmEngine | None = None,
    ) -> None:
        self.validator = validator or ReadingValidator()
        self.alarm_engine = alarm_engine or AlarmEngine()

    def process(
        self,
        readings: Iterable[Reading],
        events: Iterable[Event] = (),
    ) -> PipelineResult:
        output_readings: list[Reading] = []
        output_events: list[Event] = list(events)

        for reading in readings:
            validated = self.validator.validate(reading)
            output_readings.append(validated)
            output_events.extend(self.alarm_engine.process(validated))

        return PipelineResult(output_readings, output_events)
