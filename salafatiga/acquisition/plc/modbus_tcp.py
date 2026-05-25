"""Wrapper Modbus TCP per llegir els tags del PLC."""
from __future__ import annotations

from typing import Protocol

from salafatiga.config.models import PlcConfig


class PlcClient(Protocol):
    """Client minim que necessita :class:`ModbusTcpPlcSource`."""

    def read_input_registers(self, address: int, count: int) -> list[int]: ...
    def close(self) -> None: ...


class PymodbusTcpPlcClient:
    """Client TCP real basat en pymodbus."""

    def __init__(self, cfg: PlcConfig) -> None:
        try:
            from pymodbus.client import ModbusTcpClient
        except ImportError as exc:
            raise RuntimeError(
                "Falta pymodbus. Instal·la requirements.txt per comunicar amb el PLC."
            ) from exc

        self.cfg = cfg
        self._client = ModbusTcpClient(host=cfg.host, port=cfg.port, timeout=cfg.timeout_s)

    def read_input_registers(self, address: int, count: int) -> list[int]:
        if not self._client.connect():
            raise ConnectionError(f"No es pot connectar al PLC {self.cfg.host}:{self.cfg.port}")

        try:
            result = self._client.read_input_registers(
                address=address,
                count=count,
                slave=self.cfg.unit_id,
            )
        except TypeError:
            result = self._client.read_input_registers(
                address=address,
                count=count,
                unit=self.cfg.unit_id,
            )

        if result.isError():
            raise IOError(f"Error Modbus TCP llegint input registers @{address}: {result}")
        return [int(v) for v in result.registers]

    def close(self) -> None:
        self._client.close()
