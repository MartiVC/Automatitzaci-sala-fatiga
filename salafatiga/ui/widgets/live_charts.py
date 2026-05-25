"""Gràfic de tendència en viu, dibuixat amb QPainter.

No depèn de cap llibreria de gràfics externa: es pinta tot amb QPainter, així que
funciona en qualsevol instal·lació amb PySide6. L'usuari tria quines variables vol
veure amb les caselles de la part superior; l'eix Y s'autoescala a les sèries
seleccionades i l'eix X mostra la finestra temporal recent (``ui.chart_window_s``).
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLabel, QVBoxLayout, QWidget

from salafatiga.core import variables
from salafatiga.core.datamodel import Reading

#: Variables analògiques que es poden representar al gràfic.
CHART_VARIABLES: tuple[str, ...] = (
    variables.V_FREQ_HZ,
    variables.V_PRESSIO,
    variables.V_INTENSITAT,
    variables.V_T_RODAMENT_DE,
    variables.V_T_RODAMENT_NDE,
    variables.V_T_MOTOR,
    variables.V_T_FLUID,
    variables.V_T_AMBIENT,
    variables.V_VIB_DE,
    variables.V_VIB_NDE,
    variables.V_RPM_MOTOR,
)
#: Selecció inicial (variables de procés del variador, de magnitud comparable).
DEFAULT_SELECTED: tuple[str, ...] = (variables.V_FREQ_HZ, variables.V_PRESSIO, variables.V_INTENSITAT)

SERIES_COLORS: tuple[QColor, ...] = (
    QColor("#1f6feb"), QColor("#1f9d57"), QColor("#d97706"), QColor("#cc2f3a"),
    QColor("#7c3aed"), QColor("#0f8a8a"), QColor("#b8336a"), QColor("#4d5a6b"),
)

_GRID = QColor("#e1e7f0")
_AXIS = QColor("#9aa4b2")
_INK = QColor("#334155")
_FAINT = QColor("#7a8494")
_BG = QColor("#ffffff")
_MAX_POINTS = 6000


def _color_for(variable_id: str) -> QColor:
    try:
        idx = CHART_VARIABLES.index(variable_id)
    except ValueError:
        idx = 0
    return SERIES_COLORS[idx % len(SERIES_COLORS)]


def _fmt(value: float) -> str:
    a = abs(value)
    if a >= 1000:
        return f"{value:,.0f}".replace(",", " ")
    if a >= 100:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    if a >= 1:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _nice_scale(lo: float, hi: float, count: int = 5) -> tuple[float, float, list[float]]:
    if not (math.isfinite(lo) and math.isfinite(hi)):
        return 0.0, 1.0, [0.0, 1.0]
    if lo == hi:
        lo -= 1.0
        hi += 1.0
    rng = hi - lo
    raw = rng / max(count, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    norm = raw / mag
    step = (1 if norm < 1.5 else 2 if norm < 3 else 5 if norm < 7 else 10) * mag
    nmin = math.floor(lo / step) * step
    nmax = math.ceil(hi / step) * step
    ticks: list[float] = []
    v = nmin
    while v <= nmax + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    return nmin, nmax, ticks


@dataclass(slots=True)
class _Series:
    timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=_MAX_POINTS))
    values: deque[float] = field(default_factory=lambda: deque(maxlen=_MAX_POINTS))

    def add(self, ts: float, value: float) -> None:
        self.timestamps.append(ts)
        self.values.append(value)

    def clear(self) -> None:
        self.timestamps.clear()
        self.values.clear()

    def window_points(self, t0: float) -> list[tuple[float, float]]:
        return [(t, v) for t, v in zip(self.timestamps, self.values) if t >= t0]


class _ChartCanvas(QWidget):
    """Llenç que pinta les sèries seleccionades."""

    MARGINS = (58, 16, 14, 42)  # esquerra, dreta, dalt, baix

    def __init__(self, owner: "LiveChartsWidget", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._owner = owner
        self.setMinimumHeight(300)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, _BG)

        ml, mr, mt, mb = self.MARGINS
        plot = QRectF(ml, mt, max(10.0, w - ml - mr), max(10.0, h - mt - mb))

        now = time.time()
        window_s = max(self._owner.window_s, 5)
        t0 = now - window_s

        active: list[tuple[str, QColor, list[tuple[float, float]]]] = []
        for var_id in CHART_VARIABLES:
            if var_id not in self._owner.selected:
                continue
            series = self._owner.series.get(var_id)
            if series is None:
                continue
            pts = series.window_points(t0)
            if not pts:
                continue
            active.append((var_id, _color_for(var_id), pts))

        # marc del gràfic
        p.setPen(QPen(_AXIS, 1))
        p.drawRect(plot)

        if not active:
            p.setPen(_FAINT)
            p.setFont(QFont(self.font().family(), 10))
            msg = (
                "Selecciona alguna variable a dalt."
                if not self._owner.selected
                else "Encara no hi ha dades. Inicia l'adquisició."
            )
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, msg)
            return

        all_values = [v for _, _, pts in active for _, v in pts]
        lo, hi = min(all_values), max(all_values)
        pad = (hi - lo) * 0.08 or 1.0
        ymin, ymax, yticks = _nice_scale(lo - pad, hi + pad, 5)
        yspan = ymax - ymin or 1.0

        def x_of(ts: float) -> float:
            return plot.left() + (ts - t0) / window_s * plot.width()

        def y_of(value: float) -> float:
            return plot.bottom() - (value - ymin) / yspan * plot.height()

        # graella + etiquetes Y
        small = QFont(self.font().family(), 8)
        p.setFont(small)
        for tick in yticks:
            y = y_of(tick)
            if y < plot.top() - 0.5 or y > plot.bottom() + 0.5:
                continue
            p.setPen(QPen(_GRID, 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(_FAINT)
            p.drawText(QRectF(0, y - 8, ml - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt(tick))

        # graella + etiquetes X (temps)
        x_ticks = 5
        for i in range(x_ticks + 1):
            ts = t0 + (i / x_ticks) * window_s
            x = x_of(ts)
            if 0 < i < x_ticks:
                p.setPen(QPen(_GRID, 1))
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(_FAINT)
            label = time.strftime("%H:%M:%S", time.localtime(ts))
            flags = Qt.AlignmentFlag.AlignTop
            if i == 0:
                flags |= Qt.AlignmentFlag.AlignLeft
                rect = QRectF(x, plot.bottom() + 4, 64, 14)
            elif i == x_ticks:
                flags |= Qt.AlignmentFlag.AlignRight
                rect = QRectF(x - 64, plot.bottom() + 4, 64, 14)
            else:
                flags |= Qt.AlignmentFlag.AlignHCenter
                rect = QRectF(x - 40, plot.bottom() + 4, 80, 14)
            p.drawText(rect, flags, label)

        # sèries
        p.setClipRect(plot)
        for var_id, color, pts in active:
            if len(pts) == 1:
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(x_of(pts[0][0]), y_of(pts[0][1])), 2.5, 2.5)
                continue
            path = QPainterPath()
            for j, (ts, value) in enumerate(pts):
                pt = QPointF(x_of(ts), y_of(value))
                if j == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.setClipping(False)

        # llegenda (cantonada superior dreta del plot)
        p.setFont(QFont(self.font().family(), 9))
        lx = plot.left() + 8
        ly = plot.top() + 14
        for var_id, color, pts in active:
            last = pts[-1][1]
            var_def = variables.get(var_id)
            text = f"{var_def.nom}: {_fmt(last)} {var_def.unit}".rstrip()
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(lx, ly - 8, 9, 9))
            p.setPen(_INK)
            p.drawText(QPointF(lx + 14, ly), text)
            ly += 16


class LiveChartsWidget(QWidget):
    """Pestanya de gràfiques en viu de l'aplicació Qt."""

    def __init__(self, window_s: int = 120, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.window_s = max(int(window_s), 5)
        self._equip_id: str | None = None
        self.series: dict[str, _Series] = {var_id: _Series() for var_id in CHART_VARIABLES}
        self.selected: set[str] = set(DEFAULT_SELECTED)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Variables a representar:"))
        picker = QWidget()
        grid = QGridLayout(picker)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(2)
        self._checks: dict[str, QCheckBox] = {}
        for i, var_id in enumerate(CHART_VARIABLES):
            var_def = variables.get(var_id)
            cb = QCheckBox(f"{var_def.nom} [{var_def.unit}]" if var_def.unit else var_def.nom)
            cb.setChecked(var_id in self.selected)
            color = _color_for(var_id)
            cb.setStyleSheet(f"QCheckBox {{ color: {color.name()}; }}")
            cb.toggled.connect(lambda checked, v=var_id: self._on_toggle(v, checked))
            self._checks[var_id] = cb
            grid.addWidget(cb, i // 4, i % 4)
        layout.addWidget(picker)

        self.canvas = _ChartCanvas(self)
        layout.addWidget(self.canvas, 1)

    # -- API usada per MainWindow ------------------------------------------- #
    def set_equip(self, equip_id: str) -> None:
        if equip_id == self._equip_id:
            return
        self._equip_id = equip_id
        for series in self.series.values():
            series.clear()
        self.canvas.update()

    def update_reading(self, reading: Reading) -> None:
        if self._equip_id is not None and reading.equip_id != self._equip_id:
            return
        if reading.variable_id not in self.series or reading.value is None:
            return
        try:
            value = float(reading.value)
        except (TypeError, ValueError):
            return
        self.series[reading.variable_id].add(reading.ts, value)
        if reading.variable_id in self.selected:
            self.canvas.update()

    # -- intern ------------------------------------------------------------- #
    def _on_toggle(self, variable_id: str, checked: bool) -> None:
        if checked:
            self.selected.add(variable_id)
        else:
            self.selected.discard(variable_id)
        self.canvas.update()
