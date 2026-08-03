"""Vista previa RTSP de la cámara mediante OpenCV.

Captura el stream en un hilo dedicado (``VideoStreamThread``) y convierte
cada frame a ``QImage`` para mostrarlo en un ``QLabel``. Si el stream no
está disponible (modo simulación) se muestra un texto de relleno.
"""

from __future__ import annotations

import logging
import os
import time

import cv2
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from utils.logger import get_app_log_level, get_logger

log = get_logger(__name__)

_RECONNECT_BASE_DELAY_S = 1.0
_RECONNECT_MAX_DELAY_S = 8.0
_STREAM_TIMEOUT_US = 5_000_000  # timeout de socket de FFmpeg: 5 s (microsegundos)
_MAX_DELAY_US = 500_000  # margen máximo de reordenación: 0,5 s
_SOCKET_BUFFER_BYTES = 1_048_576  # búfer de recepción: absorbe ráfagas por WiFi
_MAX_READ_FAILURES = 3  # lecturas fallidas seguidas antes de reconectar


def build_ffmpeg_options(transport: str) -> str:
    """Genera las opciones FFmpeg para el backend de captura de OpenCV.

    ``OPENCV_FFMPEG_CAPTURE_OPTIONS`` usa el formato ``clave;valor``
    separadas por ``|``. El transporte RTSP TCP evita la pérdida de
    paquetes RTP/UDP, principal causa de errores de referencia H.264
    ("reference picture missing", "mmco: unref short failure", ...).

    Se envían ``timeout`` y ``stimeout`` a la vez a propósito: FFmpeg
    renombró la opción en la versión 5 y cada rueda de ``opencv-python``
    empaqueta su propia versión; la que no exista se ignora. Sin ella
    ``read()`` puede quedarse bloqueado indefinidamente y el stream nunca
    se reconecta.
    """
    options = [
        f"rtsp_transport;{transport}",
        f"timeout;{_STREAM_TIMEOUT_US}",
        f"stimeout;{_STREAM_TIMEOUT_US}",
        f"max_delay;{_MAX_DELAY_US}",
        f"buffer_size;{_SOCKET_BUFFER_BYTES}",
        "fflags;nobuffer",
        "flags;low_delay",
    ]
    if transport == "tcp":
        # Sobre TCP los paquetes llegan en orden: la cola de reordenación
        # solo añadiría latencia.
        options.append("reorder_queue_size;0")
    return "|".join(options)


def build_ffmpeg_loglevel() -> str:
    """Nivel de log a aplicar a FFmpeg vía ``OPENCV_FFMPEG_LOGLEVEL``.

    Con el logger de la aplicación en DEBUG se dejan pasar los mensajes de
    FFmpeg (útiles para depurar). En caso contrario se silencian: los
    errores del decodificador H.264 ("reference picture missing during
    reorder", "mmco: unref short failure", ...) son no fatales y se
    recuperan en el siguiente keyframe (IDR).
    """
    return "32" if get_app_log_level() <= logging.DEBUG else "0"


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


class VideoStreamThread(QThread):
    """Hilo que captura frames de una URL RTSP con OpenCV."""

    frame_ready = Signal(QImage)
    stream_error = Signal(str)
    stream_stopped = Signal()

    def __init__(
        self,
        url: str,
        fps: int = 15,
        transport: str = "tcp",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._fps = max(1, fps)
        self._transport = transport
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        retries = 0
        first_failure = True
        while self._running:
            capture = self._open_capture()
            if capture is None or not capture.isOpened():
                if not self._running:
                    break
                log.warning("No se pudo abrir el stream; reintentando…")
                if first_failure:
                    self.stream_error.emit(f"No se pudo abrir el stream: {self._url}")
                    first_failure = False
                if not self._sleep_reconnect(retries):
                    break
                retries += 1
                continue
            log.info("Stream RTSP abierto (transporte %s): %s", self._transport, self._url)
            first_failure = True
            retries = 0
            self._consume(capture)
            capture.release()
            if not self._running:
                break
            if not self._sleep_reconnect(retries):
                break
            retries += 1
        self.stream_stopped.emit()
        log.info("Stream RTSP cerrado")

    # -- Internos ---------------------------------------------------------

    def _consume(self, capture: cv2.VideoCapture) -> None:
        """Lee frames hasta que el stream falla o se pide la parada.

        Se lee **sin pausas**: ``read()`` ya bloquea hasta que llega el
        siguiente frame, así que dormir entre lecturas hace que el búfer
        de recepción se llene y la imagen acabe llegando con retardo
        creciente, a tirones y con cortes. El límite de fps se aplica
        solo al emitir hacia la GUI, descartando los frames sobrantes.
        """
        min_interval = 1.0 / self._fps
        last_emit = 0.0
        failures = 0
        while self._running:
            ok, frame = capture.read()
            if not ok or frame is None:
                failures += 1
                if failures >= _MAX_READ_FAILURES:
                    log.warning("Stream interrumpido; reintentando…")
                    return
                time.sleep(0.05)
                continue
            failures = 0
            now = time.monotonic()
            if now - last_emit < min_interval:
                continue
            last_emit = now
            self.frame_ready.emit(_to_qimage(frame))

    def _open_capture(self) -> cv2.VideoCapture | None:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = build_ffmpeg_options(
            self._transport
        )
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = build_ffmpeg_loglevel()
        return cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

    def _sleep_reconnect(self, retries: int) -> bool:
        """Espera con backoff exponencial en fragmentos cortos; False si se
        pidió la parada durante la espera."""
        delay = min(
            _RECONNECT_MAX_DELAY_S, _RECONNECT_BASE_DELAY_S * (2 ** retries)
        )
        deadline = time.monotonic() + delay
        while self._running and time.monotonic() < deadline:
            time.sleep(0.05)
        return self._running


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
        self._thread = VideoStreamThread(url, self._fps, self._transport)
        self._thread.frame_ready.connect(self._show_frame)
        self._thread.stream_error.connect(self._on_stream_error)
        self._thread.start()

    def stop(self) -> None:
        """Detiene la captura en curso sin bloquear la interfaz.

        Si el hilo no termina enseguida (puede estar dentro de un
        ``read()`` que agota su timeout), se le suelta pero se conserva la
        referencia y se desconectan sus señales: así no sigue pintando
        frames del stream anterior ni se destruye mientras corre.
        """
        thread = self._thread
        self._thread = None
        self._last_pixmap = None
        if thread is None:
            return
        thread.frame_ready.disconnect(self._show_frame)
        thread.stream_error.disconnect(self._on_stream_error)
        thread.stop()
        if thread.wait(500):
            return
        self._stopping.append(thread)
        thread.finished.connect(lambda: self._forget_thread(thread))

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
