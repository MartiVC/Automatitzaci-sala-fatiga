"""Fonts d'adquisicio del PLC real i simulador in-process."""
from __future__ import annotations

from salafatiga.acquisition.base import ConnectionState, DataSource, PollResult, SourceStatus
from salafatiga.acquisition.plc.map import PLC_TAGS, PlcTag
from salafatiga.acquisition.plc.modbus_tcp import PlcClient, PymodbusTcpPlcClient
from salafatiga.acquisition.plc.simulation import PlcSignalSimulator
from salafatiga.config.models import PlcConfig
from salafatiga.core.datamodel import Event, EventType, Origin, Reading, Severity


class ModbusTcpPlcSource(DataSource):
    """Llegeix tags del PLC per Modbus TCP."""

    source_id = "plc"

    def __init__(
        self,
        cfg: PlcConfig,
        *,
        equip_id: str,
        client: PlcClient | None = None,
        tags: tuple[PlcTag, ...] = PLC_TAGS,
    ) -> None:
        self.cfg = cfg
        self.equip_id = equip_id
        self.client = client
        self.tags = tags
        self.status = SourceStatus(self.source_id)
        self._was_lost = False

    def poll(self) -> PollResult:
        if not self.cfg.enabled:
            self.status.state = ConnectionState.DISABLED
            return PollResult(status=self.status)
        try:
            readings = self._read_all()
        except Exception as exc:
            return self._fail(exc)

        events: list[Event] = []
        if self._was_lost:
            events.append(
                Event.now(
                    "SISTEMA",
                    Origin.SISTEMA,
                    EventType.COMM_RESTORED,
                    Severity.INFO,
                    "COMM_PLC_OK",
                    "Comunicació amb el PLC recuperada",
                )
            )
        self._was_lost = False
        self.status.mark_ok(f"{len(readings)} lectures")
        return PollResult(readings=readings, events=events, status=self.status)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()

    def _client(self) -> PlcClient:
        if self.client is None:
            self.client = PymodbusTcpPlcClient(self.cfg)
        return self.client

    def _read_all(self) -> list[Reading]:
        first_addr = min(tag.addr for tag in self.tags)
        last_addr = max(tag.addr for tag in self.tags)
        registers = self._client().read_input_registers(first_addr, last_addr - first_addr + 1)
        readings: list[Reading] = []
        for tag in self.tags:
            raw = registers[tag.addr - first_addr]
            readings.append(
                Reading.now(
                    self.equip_id,
                    Origin.PLC,
                    tag.variable_id,
                    tag.raw_to_value(raw),
                    unit=tag.unit,
                    raw=raw,
                )
            )
        return readings

    def _fail(self, exc: Exception) -> PollResult:
        self.status.mark_error(str(exc), lost_after=1)
        events: list[Event] = []
        if self.status.state is ConnectionState.LOST and not self._was_lost:
            events.append(
                Event.now(
                    "SISTEMA",
                    Origin.SISTEMA,
                    EventType.COMM_LOST,
                    Severity.WARNING,
                    "COMM_PLC_LOST",
                    f"Comunicació amb el PLC perduda: {exc}",
                )
            )
            self._was_lost = True
        return PollResult(events=events, status=self.status)


class InProcessSimPlcSource(DataSource):
    """Simulador PLC sense xarxa per a demos i tests."""

    source_id = "plc_sim_inproc"

    def __init__(self, *, equip_id: str, seed: int | None = None, anomaly: str = "none") -> None:
        self.equip_id = equip_id
        self.status = SourceStatus(self.source_id)
        self._simulator = PlcSignalSimulator(seed=seed, anomaly=anomaly)

    def poll(self) -> PollResult:
        snapshot = self._simulator.snapshot()
        readings: list[Reading] = []
        for tag in PLC_TAGS:
            value = snapshot[tag.variable_id]
            readings.append(
                Reading.now(
                    self.equip_id,
                    Origin.PLC,
                    tag.variable_id,
                    value,
                    unit=tag.unit,
                    raw=tag.value_to_raw(value),
                )
            )
        self.status.mark_ok(f"{len(readings)} lectures simulades")
        return PollResult(readings=readings, status=self.status)
