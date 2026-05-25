"""Tests del pas 4: simulador PLC Modbus TCP autonom."""
from __future__ import annotations

from salafatiga.acquisition.plc.map import PLC_TAGS
from salafatiga.acquisition.plc.simulation import PlcSignalSimulator
from salafatiga.acquisition.plc.simulator import (
    PlcRegisterImage,
    create_server_context,
    update_context_once,
)
from salafatiga.core import variables
from run_plc_simulator import main as simulator_main


def test_plc_register_image_matches_tag_map():
    image = PlcRegisterImage(PlcSignalSimulator(seed=1))
    values = image.values()

    assert image.first_addr == PLC_TAGS[0].addr
    assert image.count == len(PLC_TAGS)
    assert len(values) == len(PLC_TAGS)
    assert values[PLC_TAGS[-1].addr - image.first_addr] > 0


def test_pymodbus_context_is_updated_with_input_registers():
    image = PlcRegisterImage(PlcSignalSimulator(seed=2))
    context = create_server_context(image)
    values = update_context_once(context, image)

    slave = context[0]
    stored = slave.getValues(4, image.first_addr, image.count)

    assert stored == values


def test_heat_anomaly_increases_hot_variables():
    normal = PlcSignalSimulator(seed=1, anomaly="none")
    heat = PlcSignalSimulator(seed=1, anomaly="heat")

    assert heat.value(variables.V_T_MOTOR, elapsed=2_000) > normal.value(
        variables.V_T_MOTOR,
        elapsed=2_000,
    )


def test_run_plc_simulator_once(capsys):
    rc = simulator_main(["--once", "--seed", "1"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "PLC simulator snapshot" in captured.out
    assert variables.V_T_MOTOR in captured.out
