"""Tests del pas 5: validacio, pipeline i alarmes."""
from __future__ import annotations

from dataclasses import dataclass

from salafatiga.acquisition.base import ConnectionState, PollResult, SourceStatus
from salafatiga.alarms.engine import AlarmEngine
from salafatiga.core import variables
from salafatiga.core.datamodel import EventType, Origin, Quality, Reading
from salafatiga.processing.pipeline import ProcessingPipeline
from salafatiga.processing.validation import ReadingValidator, ValidationConfig
from salafatiga.services.acquisition_service import AcquisitionService
from salafatiga.services.bus import SignalBus


def test_validator_marks_out_of_range_as_bad():
    validator = ReadingValidator(ValidationConfig(max_age_s=100.0))
    reading = Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 250.0, "°C")

    validated = validator.validate(reading, now=101.0)

    assert validated.quality is Quality.BAD
    assert "rang valid" in validated.note


def test_validator_marks_old_reading_as_stale():
    validator = ReadingValidator(ValidationConfig(max_age_s=5.0))
    reading = Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 50.0, "°C")

    validated = validator.validate(reading, now=110.0)

    assert validated.quality is Quality.STALE
    assert "antiga" in validated.note


def test_validator_marks_large_jump_as_uncertain():
    validator = ReadingValidator(
        ValidationConfig(max_age_s=100.0, max_jump_abs={variables.V_T_MOTOR: 10.0})
    )
    first = Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 50.0, "°C")
    second = Reading(101.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 75.0, "°C")

    assert validator.validate(first, now=101.0).quality is Quality.GOOD
    validated = validator.validate(second, now=102.0)

    assert validated.quality is Quality.UNCERTAIN
    assert "Salt sobtat" in validated.note


def test_threshold_alarm_engine_emits_set_and_clear_events():
    engine = AlarmEngine()
    normal = Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 70.0, "°C")
    warning = Reading(101.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 95.0, "°C")
    alarm = Reading(102.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 111.0, "°C")
    recovered = Reading(103.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 60.0, "°C")

    assert engine.process(normal) == []
    warning_events = engine.process(warning)
    alarm_events = engine.process(alarm)
    clear_events = engine.process(recovered)

    assert [e.type for e in warning_events] == [EventType.WARNING_SET]
    assert [e.type for e in alarm_events] == [EventType.WARNING_CLEAR, EventType.ALARM_SET]
    assert [e.type for e in clear_events] == [EventType.ALARM_CLEAR]


def test_vfd_alarm_code_generates_events_once_and_clear():
    engine = AlarmEngine()
    active = Reading(
        100.0,
        "GRUP1_B1",
        Origin.VARIADOR,
        variables.V_ALARMA_CODI,
        33.0,
        status_code=33,
    )
    clear = Reading(
        101.0,
        "GRUP1_B1",
        Origin.VARIADOR,
        variables.V_ALARMA_CODI,
        0.0,
        status_code=0,
    )

    events = engine.process(active)
    repeated = engine.process(active)
    clear_events = engine.process(clear)

    assert len(events) == 1
    assert events[0].type is EventType.ALARM_SET
    assert events[0].code == "VFD_33"
    assert repeated == []
    assert [e.type for e in clear_events] == [EventType.ALARM_CLEAR]


def test_pipeline_validates_before_alarm_engine():
    pipeline = ProcessingPipeline()
    reading = Reading(100.0, "GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 250.0, "°C")

    result = pipeline.process([reading])

    assert result.readings[0].quality is Quality.BAD
    assert result.events == []


@dataclass(slots=True)
class HotMotorSource:
    source_id: str = "hot"

    def poll(self) -> PollResult:
        return PollResult(
            readings=[
                Reading.now("GRUP1_B1", Origin.PLC, variables.V_T_MOTOR, 111.0, unit="°C")
            ],
            status=SourceStatus(self.source_id, ConnectionState.OK),
        )

    def close(self) -> None:
        pass


def test_acquisition_service_can_publish_pipeline_events():
    bus = SignalBus()
    events = []
    bus.on_event(events.append)
    pipeline = ProcessingPipeline(
        validator=ReadingValidator(ValidationConfig(max_age_s=1_000_000.0)),
        alarm_engine=AlarmEngine(),
    )
    service = AcquisitionService([HotMotorSource()], bus=bus, pipeline=pipeline)

    result = service.poll_once()

    assert result.readings[0].quality is Quality.GOOD
    assert [e.type for e in result.events] == [EventType.ALARM_SET]
    assert events == result.events
