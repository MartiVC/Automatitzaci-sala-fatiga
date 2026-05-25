"""Motor d'alarmes per llindars i codis del variador."""
from __future__ import annotations

import enum
from dataclasses import dataclass

from salafatiga.alarms.catalog import threshold_code, vfd_alarm
from salafatiga.alarms.events import event_from_reading
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, EventType, Quality, Reading, Severity


class AlarmLevel(enum.IntEnum):
    OK = 0
    WARNING = 1
    ALARM = 2


@dataclass(slots=True)
class _TrackedState:
    stable: AlarmLevel = AlarmLevel.OK
    pending: AlarmLevel = AlarmLevel.OK
    pending_count: int = 0
    code: str = ""


class AlarmEngine:
    """Genera esdeveniments quan canvia l'estat d'alarma."""

    def __init__(self, *, debounce_count: int = 1) -> None:
        self.debounce_count = max(debounce_count, 1)
        self._threshold_states: dict[tuple[str, str], _TrackedState] = {}
        self._vfd_codes: dict[str, int] = {}

    def process(self, reading: Reading) -> list[Event]:
        if reading.quality not in (Quality.GOOD, Quality.UNCERTAIN):
            return []
        if reading.variable_id == variables.V_ALARMA_CODI:
            return self._process_vfd_alarm(reading)
        return self._process_threshold(reading)

    def _process_vfd_alarm(self, reading: Reading) -> list[Event]:
        raw_code = reading.status_code
        if raw_code is None and reading.raw is not None:
            raw_code = reading.raw
        if raw_code is None and reading.value is not None:
            raw_code = int(reading.value)
        raw_code = int(raw_code or 0)

        previous = self._vfd_codes.get(reading.equip_id, 0)
        if raw_code == previous:
            return []

        events: list[Event] = []
        if previous:
            previous_def = vfd_alarm(previous)
            events.append(
                event_from_reading(
                    reading,
                    EventType.ALARM_CLEAR,
                    Severity.INFO,
                    previous_def.code if previous_def else f"VFD_{previous}",
                    f"Alarma variador resolta: codi {previous}",
                )
            )

        if raw_code:
            alarm_def = vfd_alarm(raw_code)
            events.append(
                event_from_reading(
                    reading,
                    EventType.ALARM_SET,
                    alarm_def.severity if alarm_def else Severity.ALARM,
                    alarm_def.code if alarm_def else f"VFD_{raw_code}",
                    alarm_def.message if alarm_def else f"Alarma desconeguda del variador ({raw_code})",
                )
            )

        self._vfd_codes[reading.equip_id] = raw_code
        return events

    def _process_threshold(self, reading: Reading) -> list[Event]:
        if reading.quality not in (Quality.GOOD, Quality.UNCERTAIN) or reading.value is None:
            return []

        try:
            var_def = variables.get(reading.variable_id)
        except KeyError:
            return []

        desired = _desired_level(reading.value, var_def)
        if desired is None:
            return []

        key = (reading.equip_id, reading.variable_id)
        state = self._threshold_states.setdefault(key, _TrackedState())
        if desired == state.stable:
            state.pending = desired
            state.pending_count = 0
            return []

        if desired == state.pending:
            state.pending_count += 1
        else:
            state.pending = desired
            state.pending_count = 1

        if state.pending_count < self.debounce_count:
            return []

        events = self._transition_events(reading, state.stable, desired)
        state.stable = desired
        state.pending = desired
        state.pending_count = 0
        return events

    def _transition_events(
        self,
        reading: Reading,
        old: AlarmLevel,
        new: AlarmLevel,
    ) -> list[Event]:
        events: list[Event] = []
        if old is AlarmLevel.ALARM:
            events.append(_threshold_event(reading, EventType.ALARM_CLEAR, Severity.INFO))
        elif old is AlarmLevel.WARNING:
            events.append(_threshold_event(reading, EventType.WARNING_CLEAR, Severity.INFO))

        if new is AlarmLevel.WARNING:
            events.append(_threshold_event(reading, EventType.WARNING_SET, Severity.WARNING))
        elif new is AlarmLevel.ALARM:
            events.append(_threshold_event(reading, EventType.ALARM_SET, Severity.ALARM))
        return events


def _desired_level(value: float, var_def) -> AlarmLevel | None:
    has_threshold = any(
        threshold is not None
        for threshold in (var_def.warn_min, var_def.warn_max, var_def.alarm_min, var_def.alarm_max)
    )
    if not has_threshold:
        return None

    if var_def.alarm_min is not None and value <= var_def.alarm_min:
        return AlarmLevel.ALARM
    if var_def.alarm_max is not None and value >= var_def.alarm_max:
        return AlarmLevel.ALARM
    if var_def.warn_min is not None and value <= var_def.warn_min:
        return AlarmLevel.WARNING
    if var_def.warn_max is not None and value >= var_def.warn_max:
        return AlarmLevel.WARNING
    return AlarmLevel.OK


def _threshold_event(reading: Reading, event_type: EventType, severity: Severity) -> Event:
    var_def = variables.get(reading.variable_id)
    level = "alarm" if event_type in (EventType.ALARM_SET, EventType.ALARM_CLEAR) else "warning"
    action = "activada" if event_type in (EventType.ALARM_SET, EventType.WARNING_SET) else "resolta"
    code = threshold_code(reading.variable_id, level)
    message = f"{var_def.nom}: {level} {action} ({reading.value:g} {reading.unit})"
    return event_from_reading(reading, event_type, severity, code, message)
