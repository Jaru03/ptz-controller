"""Arranca/detiene la captura de vídeo según ``ptz.stream`` y alimenta el
servidor MJPEG (``gui_web/video_server.py``) con los frames codificados.

Sustituye a la parte de ``gui/main_window.py`` que reacciona a
``ptz.stream`` arrancando/parando ``VideoWidget``. Publica
``gui.streamState`` (sin señal/conectando/en directo/error) para que
``VideoPanel.tsx`` sepa qué texto de relleno mostrar — el ``<img>`` del
MJPEG en sí no lleva ese estado, solo pixels.
"""

from __future__ import annotations

import cv2

from core.event_bus import EventBus
from core.video_stream import VideoStreamThread
from gui_web.video_server import VideoHttpServer
from utils.logger import get_logger

log = get_logger(__name__)

_JPEG_QUALITY = 80
_NO_SIGNAL_MESSAGE = "Sin señal\n(conéctese una cámara real para ver el stream RTSP)"


class VideoController:
    """Traduce ``ptz.stream`` (URL) en captura + estado publicado en el bus."""

    def __init__(
        self, bus: EventBus, server: VideoHttpServer, fps: int, transport: str
    ) -> None:
        self._bus = bus
        self._server = server
        self._fps = fps
        self._transport = transport
        self._thread: VideoStreamThread | None = None
        self._url = ""
        self._last_state: tuple[str, str] | None = None
        bus.subscribe("ptz.stream", self._on_stream_uri)

    def stop(self) -> None:
        """Detiene la captura en curso (cierre de la aplicación)."""
        self._url = ""
        self._stop_thread()
        self._server.store.clear()

    # -- Reacción a ptz.stream ---------------------------------------------

    def _on_stream_uri(self, url: object) -> None:
        url = str(url or "").strip()
        if url == self._url:
            return
        self._url = url
        self._stop_thread()
        if not url:
            self._server.store.clear()
            self._publish_state("stopped", _NO_SIGNAL_MESSAGE)
            return
        self._publish_state("connecting", "Conectando con el stream…")
        thread = VideoStreamThread(
            url,
            self._fps,
            self._transport,
            on_frame=self._on_frame,
            on_error=self._on_error,
        )
        self._thread = thread
        thread.start()

    def _stop_thread(self) -> None:
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.stop()

    # -- Callables de VideoStreamThread -------------------------------------

    def _on_frame(self, frame: object) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        if not ok:
            return
        self._server.store.set(buf.tobytes())
        self._publish_state("streaming", "")

    def _on_error(self, message: str) -> None:
        log.error("Error de vídeo: %s", message)
        self._publish_state("error", message)

    def _publish_state(self, status: str, message: str) -> None:
        state = (status, message)
        if state == self._last_state:
            return
        self._last_state = state
        self._bus.publish("gui.streamState", {"status": status, "message": message})
