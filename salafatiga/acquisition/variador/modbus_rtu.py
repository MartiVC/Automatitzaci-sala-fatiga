"""Wrapper de lectura Modbus RTU del SPEEDRIVE V2 amb minimalmodbus."""
from __future__ import annotations

from typing import Protocol

from salafatiga.acquisition.variador import registers
from salafatiga.config.models import VariadorConfig


class VariadorClient(Protocol):
    """Client minim que necessita :class:`VariadorSource`."""

    def read_input_register(self, doc_reg: int) -> int: ...
    def read_discrete_input(self, doc_reg: int) -> bool: ...
    def close(self) -> None: ...


class MinimalModbusRtuClient:
    """Client RTU real. La importacio es fa tard per facilitar tests sense hardware."""

    def __init__(self, cfg: VariadorConfig) -> None:
        try:
            import minimalmodbus
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "Falten dependències Modbus RTU. Instal·la requirements.txt."
            ) from exc

        instrument = minimalmodbus.Instrument(cfg.port, cfg.slave_id)
        instrument.serial.baudrate = cfg.baudrate
        instrument.serial.bytesize = cfg.bytesize
        instrument.serial.parity = cfg.parity
        instrument.serial.stopbits = cfg.stopbits
        instrument.serial.timeout = cfg.timeout_s
        instrument.mode = minimalmodbus.MODE_RTU
        instrument.clear_buffers_before_each_transaction = True
        instrument.close_port_after_each_call = False
        self._instrument = instrument
        self._serial = serial

    def read_input_register(self, doc_reg: int) -> int:
        if registers.function_of(doc_reg) != 4:
            raise ValueError(f"El registre {doc_reg} no es llegeix amb FC04.")
        return int(
            self._instrument.read_register(
                registers.addr_of(doc_reg),
                number_of_decimals=0,
                functioncode=4,
                signed=False,
            )
        )

    def read_discrete_input(self, doc_reg: int) -> bool:
        if registers.function_of(doc_reg) != 2:
            raise ValueError(f"El registre {doc_reg} no es llegeix amb FC02.")
        return bool(self._instrument.read_bit(registers.addr_of(doc_reg), functioncode=2))

    def close(self) -> None:
        serial_port = getattr(self._instrument, "serial", None)
        if serial_port is not None and getattr(serial_port, "is_open", False):
            serial_port.close()
