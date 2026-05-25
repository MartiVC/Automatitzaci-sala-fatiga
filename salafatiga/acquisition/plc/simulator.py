"""Servidor Modbus TCP autonom que simula el PLC."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from salafatiga.acquisition.plc.map import PLC_TAGS, PlcTag
from salafatiga.acquisition.plc.simulation import PlcSignalSimulator

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class PlcSimulatorConfig:
    host: str = "127.0.0.1"
    port: int = 5020
    unit_id: int = 1
    update_period_s: float = 1.0
    anomaly: str = "none"
    seed: int | None = None


class PlcRegisterImage:
    """Imatge de registres que s'actualitza amb el generador de senyals."""

    def __init__(
        self,
        simulator: PlcSignalSimulator | None = None,
        *,
        tags: tuple[PlcTag, ...] = PLC_TAGS,
    ) -> None:
        self.simulator = simulator or PlcSignalSimulator()
        self.tags = tags

    @property
    def first_addr(self) -> int:
        return min(tag.addr for tag in self.tags)

    @property
    def last_addr(self) -> int:
        return max(tag.addr for tag in self.tags)

    @property
    def count(self) -> int:
        return self.last_addr - self.first_addr + 1

    def values(self) -> list[int]:
        snapshot = self.simulator.snapshot()
        values = [0] * self.count
        for tag in self.tags:
            values[tag.addr - self.first_addr] = tag.value_to_raw(snapshot[tag.variable_id])
        return values


def create_server_context(image: PlcRegisterImage):
    """Crea el context pymodbus amb input registers carregats."""
    try:
        from pymodbus.datastore import (
            ModbusSequentialDataBlock,
            ModbusServerContext,
            ModbusSlaveContext,
        )
    except ImportError as exc:
        raise RuntimeError("Falta pymodbus. Instal·la requirements.txt.") from exc

    # Pymodbus 3.x suma 1 internament a l'adreca Modbus; per a una peticio
    # address=0 cal que el data block comenci a 1.
    start_address = image.first_addr + 1
    slave = ModbusSlaveContext(
        ir=ModbusSequentialDataBlock(start_address, image.values()),
    )
    return ModbusServerContext(slaves=slave, single=True)


def update_context_once(context, image: PlcRegisterImage) -> list[int]:
    """Actualitza els input registers i retorna els raw escrits."""
    values = image.values()
    slave = _single_slave_context(context)
    slave.setValues(4, image.first_addr, values)
    return values


def start_update_thread(
    context,
    image: PlcRegisterImage,
    *,
    period_s: float,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Actualitza la imatge de registres en un fil daemon."""
    stop = stop_event or threading.Event()

    def _run() -> None:
        while not stop.is_set():
            try:
                update_context_once(context, image)
            except Exception:
                LOG.exception("Error actualitzant la imatge de registres PLC")
            stop.wait(max(period_s, 0.1))

    thread = threading.Thread(target=_run, name="plc-sim-updater", daemon=True)
    thread.start()
    return thread


def run_tcp_server(cfg: PlcSimulatorConfig) -> None:
    """Arrenca el servidor Modbus TCP i bloqueja fins a Ctrl+C."""
    try:
        from pymodbus.server import StartTcpServer
    except ImportError as exc:
        raise RuntimeError("Falta pymodbus. Instal·la requirements.txt.") from exc

    signal_sim = PlcSignalSimulator(seed=cfg.seed, anomaly=cfg.anomaly)
    image = PlcRegisterImage(signal_sim)
    context = create_server_context(image)
    update_context_once(context, image)
    start_update_thread(context, image, period_s=cfg.update_period_s)

    LOG.info(
        "Simulador PLC Modbus TCP escoltant a %s:%d (unit=%d, update=%.2fs, anomaly=%s)",
        cfg.host,
        cfg.port,
        cfg.unit_id,
        cfg.update_period_s,
        cfg.anomaly,
    )
    StartTcpServer(context=context, address=(cfg.host, cfg.port))


def _single_slave_context(context):
    if getattr(context, "single", False):
        return context[0]
    return context.slaves()[0]
