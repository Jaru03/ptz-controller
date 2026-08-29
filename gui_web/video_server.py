"""Servidor HTTP local que sirve el último frame como MJPEG.

Alternativa elegida frente a empujar frames en base64 vía
``evaluate_js``: reutiliza la decodificación ``multipart/x-mixed-replace``
nativa del motor del navegador (WebView2/WebKitGTK), sin inflar cada
frame a base64 ni compartir el canal síncrono del bridge de eventos
(``gui_web/bridge.py``) con el vídeo. El salto es loopback local
(``127.0.0.1``), así que no añade una fuente de latencia relevante frente
al camino directo QImage->QLabel que usaba ``gui/video_widget.py``.

``LatestFrameStore`` es un buzón de "último frame gana": nunca acumula
backlog. Junto con ``VideoStreamThread`` fijando ``CAP_PROP_BUFFERSIZE=1``
(``core/video_stream.py``), evita la causa más habitual de vídeo que se
ve cada vez más retrasado.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.logger import get_logger

log = get_logger(__name__)

_BOUNDARY = "frame"


class LatestFrameStore:
    """Guarda un único frame JPEG; cada ``set`` sustituye al anterior."""

    def __init__(self) -> None:
        self._frame: bytes | None = None
        self._condition = threading.Condition()

    def set(self, jpeg_bytes: bytes) -> None:
        with self._condition:
            self._frame = jpeg_bytes
            self._condition.notify_all()

    def clear(self) -> None:
        with self._condition:
            self._frame = None

    def get_blocking(self, timeout: float) -> bytes | None:
        """Devuelve el frame actual, esperando hasta ``timeout`` si aún no hay ninguno."""
        with self._condition:
            if self._frame is None:
                self._condition.wait(timeout)
            return self._frame


class _StreamHandler(BaseHTTPRequestHandler):
    server: "_Server"  # anotación para el type checker; ver _Server más abajo

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # silencia el log por request de http.server; ya tenemos el nuestro

    def do_GET(self) -> None:  # noqa: N802 - nombre requerido por BaseHTTPRequestHandler
        if self.path != "/stream":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={_BOUNDARY}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        store = self.server.store
        try:
            while True:
                frame = store.get_blocking(timeout=1.0)
                if frame is None:
                    continue
                self.wfile.write(f"--{_BOUNDARY}\r\n".encode())
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # el navegador cerró la conexión (cambio de vista, cierre...)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: LatestFrameStore) -> None:
        super().__init__(address, _StreamHandler)
        self.store = store


class VideoHttpServer:
    """Servidor MJPEG local (``127.0.0.1``, puerto efímero por defecto)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.store = LatestFrameStore()
        self._server = _Server((host, port), self.store)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("Servidor de vídeo MJPEG escuchando en 127.0.0.1:%s", self.port)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
