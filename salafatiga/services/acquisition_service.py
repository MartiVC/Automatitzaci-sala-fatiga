"""Orquestracio de fonts d'adquisicio."""
from __future__ import annotations

from dataclasses import dataclass, field

from salafatiga.acquisition.base import DataSource, PollResult
from salafatiga.core.datamodel import Event, Reading
from salafatiga.processing.pipeline import ProcessingPipeline
from salafatiga.services.bus import SignalBus


@dataclass(slots=True)
class AcquisitionService:
    """Executa fonts i publica el resultat al bus.

    En el pas d'UI aquest servei es cridara amb QTimer. De moment exposa
    ``poll_once`` per tests, simuladors i execucio manual.
    """

    sources: list[DataSource]
    bus: SignalBus = field(default_factory=SignalBus)
    pipeline: ProcessingPipeline | None = None

    def poll_once(self) -> PollResult:
        all_readings: list[Reading] = []
        all_events: list[Event] = []
        last_status = None

        for source in self.sources:
            result = source.poll()
            if self.pipeline is not None:
                processed = self.pipeline.process(result.readings, result.events)
                readings = processed.readings
                events = processed.events
            else:
                readings = result.readings
                events = result.events

            all_readings.extend(readings)
            all_events.extend(events)
            last_status = result.status

            for reading in readings:
                self.bus.publish_reading(reading)
            for event in events:
                self.bus.publish_event(event)
            if result.status is not None:
                self.bus.publish_status(result.status)

        return PollResult(all_readings, all_events, last_status)

    def close(self) -> None:
        for source in self.sources:
            source.close()
