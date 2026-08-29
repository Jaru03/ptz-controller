"""Vista previa RTSP de la cámara mediante OpenCV.

La captura (``VideoStreamThread``) vive en ``core/video_stream.py``,
reutilizada también por ``gui_web/video_controller.py`` (migración a
pywebview). Este módulo solo pone el pegamento con Qt: un ``QObject`` que
reemite los callables planos del hilo de captura como señales Qt (así Qt
encola automáticamente la entrega en el hilo de la GUI cuando el emisor
es un hilo en segundo plano — antes lo conseguía heredando de
``QThread`` directamente) y el ``QLabel`` que muestra el frame. Si el
stream no está disponible (modo simulación) se muestra un texto de
relleno.
"""

from __future__ import annotations

import cv2
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.video_stream import VideoStreamThread
from utils.logger import get_logger

log = get_logger(__name__)


def _to_qimage(frame) -> QImage:
    """Convierte un frame BGR de OpenCV en un ``QImage`` independiente."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, channels = rgb.shape
    return QImage(
        rgb.data,
        width,
        height,
        channels * width,
        QImage.Format.Format_RGB888,
    ).copy()


class _StreamBridge(QObject):
    """Reemite los callables de ``VideoStreamThread`` como señales Qt.

    Se construye en el hilo de la GUI: Qt encola automáticamente
    (``AutoConnection``) la entrega al hilo de la GUI cuando ``emit`` se
    llama desde el hilo de captura.
    """

    frame_ready = Signal(QImage)
    stream_error = Signal(str)
    stream_stopped = Signal()


class VideoWidget(QWidget):
    """Panel de vista previa con gestión de arranque/parada del stream."""

    def __init__(
        self,
        fps: int = 15,
        transport: str = "tcp",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fps = fps
        self._transport = transport
        self._thread: VideoStreamThread | None = None
        self._bridge: _StreamBridge | None = None
        self._stopping: list[VideoStreamThread] = []
        self._last_pixmap: QPixmap | None = None

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background-color: #15151f; color: #7f849c;")
        self._label.setWordWrap(True)
        self._show_placeholder("Sin señal\n(conéctese una cámara real para ver el stream RTSP)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

    def start(self, url: str) -> None:
        """Arranca la captura del stream RTSP indicado."""
        self.stop()
        self._show_placeholder("Conectando con el stream…")

        bridge = _StreamBridge()
        bridge.frame_ready.connect(self._show_frame)
        bridge.stream_error.connect(self._on_stream_error)
        self._bridge = bridge

        thread = VideoStreamThread(
            url,
            self._fps,
            self._transport,
            on_frame=lambda frame: bridge.frame_ready.emit(_to_qimage(frame)),
            on_error=bridge.stream_error.emit,
            on_stopped=bridge.stream_stopped.emit,
        )
        bridge.stream_stopped.connect(lambda: self._forget_thread(thread))
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        """Detiene la captura en curso sin bloquear la interfaz.

        Un ``threading.Thread`` normal no tiene un ``wait()`` bloqueante
        "amable" como ``QThread``; en vez de eso se pide la parada y se
        deja que ``on_stopped`` (reemitido como ``bridge.stream_stopped``,
        entregado en el hilo de la GUI) limpie la referencia cuando el
        hilo termine de verdad — puede estar dentro de un ``read()`` que
        agota su propio timeout, así que no conviene esperarlo aquí.
        """
        thread = self._thread
        bridge = self._bridge
        self._thread = None
        self._bridge = None
        self._last_pixmap = None
        if thread is None:
            return
        if bridge is not None:
            bridge.frame_ready.disconnect(self._show_frame)
            bridge.stream_error.disconnect(self._on_stream_error)
        thread.stop()
        if thread.is_alive():
            self._stopping.append(thread)

    def _forget_thread(self, thread: VideoStreamThread) -> None:
        if thread in self._stopping:
            self._stopping.remove(thread)

    def show_placeholder(self, text: str) -> None:
        """Muestra un mensaje de relleno (p. ej. en modo simulación)."""
        self.stop()
        self._show_placeholder(text)

    # -- Slots internos ---------------------------------------------------

    def _show_frame(self, image: QImage) -> None:
        self._last_pixmap = QPixmap.fromImage(image)
        self._render_pixmap()

    def _render_pixmap(self) -> None:
        if self._last_pixmap is None:
            return
        scaled = self._last_pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def _on_stream_error(self, message: str) -> None:
        log.error("Error de vídeo: %s", message)
        self._show_placeholder(message)

    def _show_placeholder(self, text: str) -> None:
        self._label.setPixmap(QPixmap())
        self._label.setText(text)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        self._render_pixmap()
