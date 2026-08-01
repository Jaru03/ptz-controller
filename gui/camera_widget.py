"""Widget que representa visualmente la posición de la cámara.

En modo simulación (sin cámara física) este widget dibuja una vista
"virtual" de la cámara: un punto que se desplaza por pan/tilt, ejes,
flechas de dirección, barra de zoom y velocidad. Se actualiza con las
instantáneas ``PTZStatus`` que recibe del bus de eventos.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from models.commands import PTZStatus

_BG = QColor("#1e1e2e")
_GRID = QColor("#2f2f42")
_AXIS = QColor("#4a4a63")
_DOT = QColor("#00d9ff")
_DOT_GLOW = QColor(0, 217, 255, 60)
_TEXT = QColor("#cdd6f4")
_DIM = QColor("#7f849c")
_OK = QColor("#a6e3a1")
_ERR = QColor("#f38ba8")
_ZOOM_BG = QColor("#313244")
_ZOOM_FILL = QColor("#f9e2af")


class CameraWidget(QWidget):
    """Dibuja la representación virtual de la cámara PTZ."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._status = PTZStatus()
        self.setMinimumSize(360, 260)
        policy = self.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.setSizePolicy(policy)

    def update_status(self, status: PTZStatus) -> None:
        """Actualiza la instantánea mostrada y repinta."""
        self._status = status
        self.update()

    # -- Pintado ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 28

        painter.fillRect(0, 0, width, height, _BG)

        playfield = self._playfield_rect(margin)
        self._draw_grid(painter, playfield)
        self._draw_axes(painter, playfield)
        self._draw_arrows(painter, playfield)
        self._draw_zoom(painter, margin)
        self._draw_position_dot(painter, playfield)
        self._draw_status(painter, margin)
        self._draw_position_text(painter, margin)

    def _playfield_rect(self, margin: int):
        from PySide6.QtCore import QRect

        x = margin
        y = margin + 8
        w = self.width() - 2 * margin
        h = self.height() - 2 * margin - 42
        return QRect(x, y, max(1, w), max(1, h))

    def _draw_grid(self, painter: QPainter, rect) -> None:
        painter.setPen(QPen(_GRID, 1))
        for i in range(1, 5):
            x = rect.left() + rect.width() * i / 5
            y = rect.top() + rect.height() * i / 5
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

    def _draw_axes(self, painter: QPainter, rect) -> None:
        painter.setPen(QPen(_AXIS, 1))
        center_x = rect.left() + rect.width() // 2
        center_y = rect.top() + rect.height() // 2
        painter.drawLine(rect.left(), center_y, rect.right(), center_y)
        painter.drawLine(center_x, rect.top(), center_x, rect.bottom())

    def _draw_arrows(self, painter: QPainter, rect) -> None:
        """Dibuja las flechas de dirección (↑ ↓ ← →)."""
        painter.setPen(QPen(_DIM, 1))
        font = QFont(self.font())
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter), "↑")
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter), "↓")
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "←")
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), "→")

    def _draw_zoom(self, painter: QPainter, margin: int) -> None:
        bar_x = margin
        bar_y = self.height() - margin - 8
        bar_w = self.width() - 2 * margin
        bar_h = 8
        painter.setPen(Qt.NoPen)
        painter.setBrush(_ZOOM_BG)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)
        fill = int(bar_w * max(0.0, min(1.0, self._status.zoom)))
        painter.setBrush(_ZOOM_FILL)
        painter.drawRoundedRect(bar_x, bar_y, fill, bar_h, 4, 4)

        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(_DIM)
        painter.drawText(
            bar_x, bar_y - 4, f"Zoom {self._status.zoom:+.2f}   "
            f"Velocidad {self._status.speed * 100:.0f}%"
        )

    def _draw_position_dot(self, painter: QPainter, rect) -> None:
        center_x = rect.left() + rect.width() // 2
        center_y = rect.top() + rect.height() // 2
        radius_x = rect.width() // 2 - 14
        radius_y = rect.height() // 2 - 14

        dot_x = int(center_x + self._status.pan * radius_x)
        dot_y = int(center_y - self._status.tilt * radius_y)

        painter.setPen(Qt.NoPen)
        painter.setBrush(_DOT_GLOW)
        painter.drawEllipse(dot_x - 10, dot_y - 10, 20, 20)
        painter.setBrush(_DOT)
        painter.drawEllipse(dot_x - 5, dot_y - 5, 10, 10)

    def _draw_status(self, painter: QPainter, margin: int) -> None:
        connected = self._status.connected
        color = _OK if connected else _ERR
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(margin + 4, 10, 10, 10)
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(_TEXT)
        state = "Conectada" if connected else "Desconectada"
        painter.drawText(margin + 20, 19, f"{self._status.device_name} — {state}")

    def _draw_position_text(self, painter: QPainter, margin: int) -> None:
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(_DIM)
        painter.drawText(
            margin,
            self.height() - margin - 24,
            self.width() - 2 * margin,
            20,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            f"Pan {self._status.pan:+.2f}  Tilt {self._status.tilt:+.2f}",
        )
