"""Tests del pas 3: fonts d'adquisicio i bus."""
from __future__ import annotations

from dataclasses import dataclass

from salafatiga.acquisition.base import ConnectionState
from salafatiga.acquisition.plc.map import PLC_TAGS
from salafatiga.acquisition.plc.source import InProcessSimPlcSource, ModbusTcpPlcSource
from salafatiga.acquisition.variador import registers
from salafatiga.acquisition.variador.simulation import InProcessSimVariadorSource
from salafatiga.acquisition.variador.source import VariadorSource
from salafatiga.config.models import EquipVariador, PlcConfig, VariadorConfig
from salafatiga.core import variables
from salafatiga.core.datamodel import EventType, Origin, Reading
from salafatiga.services.acquisition_service import AcquisitionService
from salafatiga.services.bus import SignalBus


class FakeVariadorClient:
    def __init__(self) -> None:
        self.input_registers = {
            registers.REG_ALARMES: 33,
            registers.reg_intensitat(0): 42,
            registers.reg_pressio(0): 15,
            registers.reg_hz_motor(0): 50,
        }
        self.discrete_inputs = {
            registers.reg_alarma_equip(0): True,
            registers.reg_auto_manual(0): False,
            registers.reg_bus485_nok(0): False,
        }

    def read_input_register(self, doc_reg: int) -> int:
        return self.input_registers[doc_reg]

    def read_discrete_input(self, doc_reg: int) -> bool:
        return self.discrete_inputs[doc_reg]

    def close(self) -> None:
        pass


class FailingVariadorClient(FakeVariadorClient):
    def read_input_register(self, doc_reg: int) -> int:
        raise TimeoutError("timeout")


class FakePlcClient:
    def read_input_registers(self, address: int, count: int) -> list[int]:
        assert address == PLC_TAGS[0].addr
        assert count == len(PLC_TAGS)
        return [420, 410, 550, 240, 315, 180, 190, 2850]

    def close(self) -> None:
        pass


@dataclass(slots=True)
class StaticSource:
    source_id: str = "static"

    def poll(self):
        from salafatiga.acquisition.base import PollResult, SourceStatus

        status = SourceStatus(self.source_id, ConnectionState.OK)
        return PollResult(
            readings=[Reading.now("E1", Origin.SISTEMA, variables.V_COMM_PLC, 1.0)],
            status=status,
        )

    def close(self) -> None:
        pass


def test_variador_source_reads_equipment_registers():
    cfg = VariadorConfig(
        equips=[EquipVariador("GRUP1_B1", 0, "demo")],
        comm_lost_after=2,
    )
    source = VariadorSource(cfg, client=FakeVariadorClient())

    result = source.poll()
    by_var = {r.variable_id: r for r in result.readings}

    assert result.status is not None
    assert result.status.state is ConnectionState.OK
    assert by_var[variables.V_INTENSITAT].value == 42.0
    assert by_var[variables.V_PRESSIO].value == 15.0
    assert by_var[variables.V_FREQ_HZ].value == 50.0
    assert by_var[variables.V_ALARMA_CODI].status_code == 33
    assert "sec" in by_var[variables.V_ALARMA_CODI].note.lower()
    assert by_var[variables.V_ESTAT_ALARMA].value == 1.0


def test_variador_source_emits_comm_lost_after_threshold():
    cfg = VariadorConfig(
        equips=[EquipVariador("GRUP1_B1", 0, "demo")],
        comm_lost_after=2,
    )
    source = VariadorSource(cfg, client=FailingVariadorClient())

    first = source.poll()
    second = source.poll()

    assert first.events == []
    assert second.status is not None
    assert second.status.state is ConnectionState.LOST
    assert second.events[0].type is EventType.COMM_LOST


def test_modbus_tcp_plc_source_reads_tags():
    source = ModbusTcpPlcSource(PlcConfig(), equip_id="GRUP1_B1", client=FakePlcClient())

    result = source.poll()
    by_var = {r.variable_id: r for r in result.readings}

    assert result.status is not None
    assert result.status.state is ConnectionState.OK
    assert by_var[variables.V_T_RODAMENT_DE].value == 42.0
    assert by_var[variables.V_VIB_DE].value == 1.8
    assert by_var[variables.V_RPM_MOTOR].value == 2850.0


def test_inprocess_plc_simulator_returns_all_tags():
    source = InProcessSimPlcSource(equip_id="GRUP1_B1", seed=1)

    result = source.poll()

    assert len(result.readings) == len(PLC_TAGS)
    assert {r.origin for r in result.readings} == {Origin.PLC}
    assert all(r.raw is not None for r in result.readings)


def test_inprocess_variador_simulator_returns_all_equipment_variables():
    cfg = VariadorConfig(
        mode="sim_inproc",
        equips=[EquipVariador("GRUP1_B1", 0, "demo")],
    )
    source = InProcessSimVariadorSource(cfg, seed=1)

    result = source.poll()
    by_var = {r.variable_id: r for r in result.readings}

    assert result.status is not None
    assert result.status.state is ConnectionState.OK
    assert set(by_var) == {
        variables.V_INTENSITAT,
        variables.V_PRESSIO,
        variables.V_FREQ_HZ,
        variables.V_ALARMA_CODI,
        variables.V_ESTAT_ALARMA,
        variables.V_ESTAT_AUTO_MAN,
        variables.V_COMM_485_NOK,
    }
    assert by_var[variables.V_INTENSITAT].origin is Origin.VARIADOR
    assert by_var[variables.V_FREQ_HZ].value is not None


def test_acquisition_service_publishes_to_bus():
    bus = SignalBus()
    seen_readings: list[Reading] = []
    seen_statuses = []
    bus.on_reading(seen_readings.append)
    bus.on_status(seen_statuses.append)
    service = AcquisitionService([StaticSource()], bus=bus)

    result = service.poll_once()

    assert len(result.readings) == 1
    assert seen_readings == result.readings
    assert seen_statuses[0].source_id == "static"
