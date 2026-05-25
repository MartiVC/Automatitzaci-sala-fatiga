"""Exportacio de mesures i esdeveniments a fitxers."""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from salafatiga.core import variables
from salafatiga.core.datamodel import Event, Reading
from salafatiga.storage import MeasurementFilter, StorageRepository


@dataclass(frozen=True, slots=True)
class ExportResult:
    path: Path
    row_count: int
    kind: str
    format: str = "csv"


class DataExporter:
    """Exporta consultes del repositori a fitxers CSV."""

    def __init__(self, repository: StorageRepository, export_dir: str | Path) -> None:
        self.repository = repository
        self.export_dir = Path(export_dir)

    def export_measurements_csv(
        self,
        flt: MeasurementFilter | None = None,
        *,
        path: str | Path | None = None,
    ) -> ExportResult:
        readings = self.repository.query_measurements(flt)
        output = Path(path) if path is not None else self._default_path("measurements")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "ts_iso",
                    "ts_unix",
                    "equip_id",
                    "origin",
                    "variable_id",
                    "variable_name",
                    "value",
                    "unit",
                    "quality",
                    "raw",
                    "status_code",
                    "note",
                ]
            )
            for reading in readings:
                writer.writerow(_measurement_row(reading))
        return ExportResult(output, len(readings), "measurements")

    def export_events_csv(
        self,
        *,
        ts_from: float | None = None,
        ts_to: float | None = None,
        equip_id: str | None = None,
        code: str | None = None,
        limit: int | None = None,
        path: str | Path | None = None,
    ) -> ExportResult:
        events = self.repository.query_events(
            ts_from=ts_from,
            ts_to=ts_to,
            equip_id=equip_id,
            code=code,
            limit=limit,
            newest_first=False,
        )
        output = Path(path) if path is not None else self._default_path("events")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "ts_iso",
                    "ts_unix",
                    "equip_id",
                    "origin",
                    "type",
                    "severity",
                    "code",
                    "message",
                    "variable_id",
                    "variable_name",
                    "value",
                ]
            )
            for event in events:
                writer.writerow(_event_row(event))
        return ExportResult(output, len(events), "events")

    def export_measurements(
        self,
        flt: MeasurementFilter | None = None,
        *,
        format: str = "csv",
        path: str | Path | None = None,
    ) -> ExportResult:
        if format.lower() != "csv":
            raise ValueError("Format no implementat encara: només csv")
        return self.export_measurements_csv(flt, path=path)

    def export_events(
        self,
        *,
        format: str = "csv",
        ts_from: float | None = None,
        ts_to: float | None = None,
        equip_id: str | None = None,
        code: str | None = None,
        limit: int | None = None,
        path: str | Path | None = None,
    ) -> ExportResult:
        if format.lower() != "csv":
            raise ValueError("Format no implementat encara: només csv")
        return self.export_events_csv(
            ts_from=ts_from,
            ts_to=ts_to,
            equip_id=equip_id,
            code=code,
            limit=limit,
            path=path,
        )

    def _default_path(self, prefix: str) -> Path:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.export_dir / f"{prefix}_{stamp}.csv"


def _measurement_row(reading: Reading) -> list[object]:
    return [
        _iso(reading.ts),
        f"{reading.ts:.3f}",
        reading.equip_id,
        reading.origin.value,
        reading.variable_id,
        _var_name(reading.variable_id),
        "" if reading.value is None else reading.value,
        reading.unit,
        reading.quality.value,
        "" if reading.raw is None else reading.raw,
        "" if reading.status_code is None else reading.status_code,
        reading.note,
    ]


def _event_row(event: Event) -> list[object]:
    return [
        _iso(event.ts),
        f"{event.ts:.3f}",
        event.equip_id,
        event.origin.value,
        event.type.value,
        int(event.severity),
        event.code,
        event.message,
        "" if event.variable_id is None else event.variable_id,
        "" if event.variable_id is None else _var_name(event.variable_id),
        "" if event.value is None else event.value,
    ]


def _iso(ts: float) -> str:
    value = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=ts)
    return value.astimezone().isoformat(timespec="seconds")


def _var_name(variable_id: str) -> str:
    try:
        return variables.get(variable_id).nom
    except KeyError:
        return variable_id
