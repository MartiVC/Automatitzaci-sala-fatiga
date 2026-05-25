"""Widget d'estat de comunicacions."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QWidget

from salafatiga.acquisition.base import ConnectionState, SourceStatus


class CommStatusWidget(QWidget):
    """Mostra l'estat de comunicacio de cada font."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        for row, source_id in enumerate(("variador", "plc", "plc_sim_inproc", "oracle")):
            name = QLabel(_source_name(source_id))
            name.setObjectName("mutedLabel")
            badge = QLabel("DISCONNECTED")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setMinimumWidth(110)
            badge.setFrameShape(QFrame.Shape.StyledPanel)
            badge.setProperty("state", ConnectionState.DISCONNECTED.value)
            self._labels[source_id] = badge
            layout.addWidget(name, row, 0)
            layout.addWidget(badge, row, 1)
        layout.setColumnStretch(2, 1)

    def update_status(self, status: SourceStatus) -> None:
        label = self._labels.get(status.source_id)
        if label is None:
            return
        label.setText(status.state.value.upper())
        label.setProperty("state", status.state.value)
        label.setToolTip(status.message)
        label.style().unpolish(label)
        label.style().polish(label)

    def update_oracle_state(self, state: str, text: str, tooltip: str = "") -> None:
        """Actualitza el badge d'Oracle.

        ``state`` ha de ser un dels valors entesos pel style.qss
        (``ok`` / ``lost`` / ``error`` / ``disabled``).
        """
        label = self._labels.get("oracle")
        if label is None:
            return
        label.setText(text)
        label.setProperty("state", state)
        label.setToolTip(tooltip)
        label.style().unpolish(label)
        label.style().polish(label)


def _source_name(source_id: str) -> str:
    return {
        "variador": "Variador RS-485",
        "plc": "PLC Modbus TCP",
        "plc_sim_inproc": "PLC sim",
        "oracle": "Oracle (històric)",
    }.get(source_id, source_id)
