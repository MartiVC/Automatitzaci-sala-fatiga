"""Font d'adquisicio del variador SPEEDRIVE V2."""
from __future__ import annotations

from salafatiga.acquisition.base import ConnectionState, DataSource, PollResult, SourceStatus
from salafatiga.acquisition.variador import registers
from salafatiga.acquisition.variador.modbus_rtu import MinimalModbusRtuClient, VariadorClient
from salafatiga.config.models import VariadorConfig
from salafatiga.core import variables
from salafatiga.core.datamodel import Event, EventType, Origin, Quality, Reading, Severity


class VariadorSource(DataSource):
    """Llegeix registres del Speedrive i emet ``Reading`` normalitzats."""

    source_id = "variador"

    def __init__(self, cfg: VariadorConfig, client: VariadorClient | None = None) -> None:
        self.cfg = cfg
        self.client = client
        self.status = SourceStatus(self.source_id)
        self._was_lost = False

    def poll(self) -> PollResult:
        if not self.cfg.enabled:
            self.status.state = ConnectionState.DISABLED
            return PollResult(status=self.status)

        try:
            client = self._client()
            readings = self._read_all(client)
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
                    "COMM_VARIADOR_OK",
                    "Comunicació amb el variador recuperada",
                )
            )
        self._was_lost = False
        self.status.mark_ok(f"{len(readings)} lectures")
        return PollResult(readings=readings, events=events, status=self.status)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()

    def _client(self) -> VariadorClient:
        if self.client is None:
            self.client = MinimalModbusRtuClient(self.cfg)
        return self.client

    def _read_all(self, client: VariadorClient) -> list[Reading]:
        readings: list[Reading] = []
        alarm_raw = client.read_input_register(registers.REG_ALARMES)

        for equip in self.cfg.equips:
            regset = registers.EquipRegisterSet(equip.addr)
            readings.extend(
                [
                    self._analog(equip.id, variables.V_INTENSITAT, client.read_input_register(regset.intensitat)),
                    self._analog(equip.id, variables.V_PRESSIO, client.read_input_register(regset.pressio)),
                    self._analog(equip.id, variables.V_FREQ_HZ, client.read_input_register(regset.hz_motor)),
                    self._code(equip.id, variables.V_ALARMA_CODI, alarm_raw),
                    self._digital(equip.id, variables.V_ESTAT_ALARMA, client.read_discrete_input(regset.alarma)),
                    self._digital(equip.id, variables.V_ESTAT_AUTO_MAN, client.read_discrete_input(regset.auto_manual)),
                    self._digital(equip.id, variables.V_COMM_485_NOK, client.read_discrete_input(regset.bus485_nok)),
                ]
            )
        return readings

    def _analog(self, equip_id: str, variable_id: str, raw: int) -> Reading:
        var = variables.get(variable_id)
        return Reading.now(
            equip_id,
            Origin.VARIADOR,
            variable_id,
            var.to_eng(raw),
            unit=var.unit,
            raw=raw,
        )

    def _code(self, equip_id: str, variable_id: str, raw: int) -> Reading:
        var = variables.get(variable_id)
        return Reading.now(
            equip_id,
            Origin.VARIADOR,
            variable_id,
            float(raw),
            unit=var.unit,
            raw=raw,
            status_code=raw,
            note=registers.alarm_text(raw),
        )

    def _digital(self, equip_id: str, variable_id: str, raw: bool) -> Reading:
        var = variables.get(variable_id)
        value = 1.0 if raw else 0.0
        return Reading.now(
            equip_id,
            Origin.VARIADOR,
            variable_id,
            value,
            unit=var.unit,
            raw=int(value),
        )

    def _fail(self, exc: Exception) -> PollResult:
        self.status.mark_error(str(exc), lost_after=self.cfg.comm_lost_after)
        events: list[Event] = []
        if self.status.state is ConnectionState.LOST and not self._was_lost:
            events.append(
                Event.now(
                    "SISTEMA",
                    Origin.SISTEMA,
                    EventType.COMM_LOST,
                    Severity.WARNING,
                    "COMM_VARIADOR_LOST",
                    f"Comunicació amb el variador perduda: {exc}",
                )
            )
            self._was_lost = True
        return PollResult(events=events, status=self.status)
