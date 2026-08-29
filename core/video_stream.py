"""Captura de vídeo RTSP en un hilo dedicado, sin dependencias de GUI.

Reubicado desde ``gui/video_widget.py`` (PySide6): la lógica de
captura/reconexión/FFmpeg es la misma, solo cambia el mecanismo de
entrega de frames — antes señales Qt (``QThread``/``Signal``), ahora
callables planos — para que sea reutilizable tanto por
``gui/video_widget.py`` (adapta los callables a señales Qt con un
pequeño puente) como por ``gui_web/video_controller.py`` (los codifica a
JPEG para el servidor MJPEG).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

import cv2

from utils.logger import get_app_log_level, get_logger

log = get_logger(__name__)

_RECONNECT_BASE_DELAY_S = 1.0
_RECONNECT_MAX_DELAY_S = 8.0
_STREAM_TIMEOUT_US = 5_000_000  # timeout de socket de FFmpeg: 5 s (microsegundos)
_MAX_DELAY_US = 500_000  # margen máximo de reordenación: 0,5 s
_SOCKET_BUFFER_BYTES = 1_048_576  # búfer de recepción: absorbe ráfagas por WiFi
_MAX_READ_FAILURES = 3  # lecturas fallidas seguidas antes de reconectar
_CAPTURE_BUFFER_FRAMES = 1  # ver nota de latencia en _open_capture


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


class VideoStreamThread(threading.Thread):
    """Hilo que captura frames de una URL RTSP con OpenCV.

    Entrega cada frame BGR (tal cual lo da OpenCV, sin convertir) vía
    ``on_frame`` en vez de una señal Qt: quien lo use decide qué hacer
    con él (convertir a ``QImage``, codificar a JPEG...).
    """

    def __init__(
        self,
        url: str,
        fps: int = 15,
        transport: str = "tcp",
        on_frame: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_stopped: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._url = url
        self._fps = max(1, fps)
        self._transport = transport
        self._on_frame = on_frame or (lambda frame: None)
        self._on_error = on_error or (lambda message: None)
        self._on_stopped = on_stopped or (lambda: None)
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
                    self._on_error(f"No se pudo abrir el stream: {self._url}")
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
        self._on_stopped()
        log.info("Stream RTSP cerrado")

    # -- Internos ---------------------------------------------------------

    def _consume(self, capture: cv2.VideoCapture) -> None:
        """Lee frames hasta que el stream falla o se pide la parada.

        Se lee **sin pausas**: ``read()`` ya bloquea hasta que llega el
        siguiente frame, así que dormir entre lecturas hace que el búfer
        de recepción se llene y la imagen acabe llegando con retardo
        creciente, a tirones y con cortes. El límite de fps se aplica
        solo al entregar el frame, descartando los sobrantes.
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
            self._on_frame(frame)

    def _open_capture(self) -> cv2.VideoCapture | None:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = build_ffmpeg_options(
            self._transport
        )
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = build_ffmpeg_loglevel()
        capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        # Sin esto, OpenCV/FFmpeg van acumulando un búfer interno de
        # frames si el consumo no va tan rápido como la llegada, y la
        # imagen acaba llegando cada vez más retrasada (el vídeo "se ve
        # lento" aunque la red vaya bien). Con buffer=1 siempre se lee el
        # frame más reciente disponible en vez de arrastrar backlog.
        capture.set(cv2.CAP_PROP_BUFFERSIZE, _CAPTURE_BUFFER_FRAMES)
        return capture

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
