"""Pruebas de la captura de vídeo RTSP (core/video_stream.py, sin GUI)."""

import logging
import os
import time

from core.video_stream import VideoStreamThread, build_ffmpeg_loglevel, build_ffmpeg_options
from utils.logger import APP_LOGGER_NAME


def _options(transport: str) -> dict[str, str]:
    return dict(
        part.split(";", 1) for part in build_ffmpeg_options(transport).split("|")
    )


def test_ffmpeg_options_default_to_tcp() -> None:
    options = _options("tcp")
    assert options["rtsp_transport"] == "tcp"
    assert options["reorder_queue_size"] == "0"


def test_ffmpeg_options_keep_transport_for_udp() -> None:
    options = _options("udp")
    assert options["rtsp_transport"] == "udp"
    assert "reorder_queue_size" not in options


def test_ffmpeg_options_set_socket_timeout_under_both_names() -> None:
    # FFmpeg renombró 'stimeout' a 'timeout' en la versión 5 y cada rueda
    # de opencv-python trae la suya: sin timeout, read() puede bloquearse
    # para siempre y el stream nunca se reconecta.
    options = _options("tcp")
    assert options["timeout"] == options["stimeout"] != "0"


def test_ffmpeg_options_are_parseable_pairs() -> None:
    for transport in ("tcp", "udp"):
        for part in build_ffmpeg_options(transport).split("|"):
            assert part.count(";") == 1
            assert all(part.split(";"))


def test_ffmpeg_loglevel_silenced_outside_debug(monkeypatch) -> None:
    monkeypatch.setattr(logging.getLogger(APP_LOGGER_NAME), "level", logging.INFO)
    assert build_ffmpeg_loglevel() == "0"


def test_ffmpeg_loglevel_verbose_in_debug(monkeypatch) -> None:
    monkeypatch.setattr(logging.getLogger(APP_LOGGER_NAME), "level", logging.DEBUG)
    assert build_ffmpeg_loglevel() == "32"


def test_open_capture_sets_ffmpeg_options_and_buffer_size(monkeypatch) -> None:
    import cv2

    opened: list[str] = []
    buffer_sizes: list[float] = []

    class FakeCapture:
        def __init__(self, url, api):
            opened.append(url)

        def isOpened(self):
            return True

        def set(self, prop, value):
            if prop == cv2.CAP_PROP_BUFFERSIZE:
                buffer_sizes.append(value)

    monkeypatch.setattr(cv2, "VideoCapture", FakeCapture)
    thread = VideoStreamThread("rtsp://cam/stream", transport="udp")
    thread._open_capture()
    assert opened == ["rtsp://cam/stream"]
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == build_ffmpeg_options("udp")
    assert "OPENCV_FFMPEG_LOGLEVEL" in os.environ
    # Sin esto el búfer de OpenCV/FFmpeg va acumulando frames y el vídeo
    # se ve cada vez más retrasado (ver core/video_stream.py).
    assert buffer_sizes == [1]


def test_consume_does_not_throttle_reads(monkeypatch) -> None:
    """Se debe leer sin pausas: dormir entre lecturas llena el búfer RTSP."""
    import numpy

    frames = 40

    class FakeCapture:
        def __init__(self) -> None:
            self.reads = 0

        def read(self):
            self.reads += 1
            if self.reads > frames:
                return False, None
            return True, numpy.zeros((4, 4, 3), dtype=numpy.uint8)

    thread = VideoStreamThread("rtsp://cam/stream", fps=1)
    thread._running = True
    emitted: list[object] = []
    thread._on_frame = emitted.append
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    capture = FakeCapture()
    thread._consume(capture)

    assert capture.reads > frames  # se leyeron todos los frames disponibles
    assert len(emitted) <= 2  # pero solo se entrega al ritmo de fps


def test_consume_tolerates_transient_read_failures(monkeypatch) -> None:
    import numpy

    results = [
        (False, None),
        (True, numpy.zeros((4, 4, 3), dtype=numpy.uint8)),
        (False, None),
        (False, None),
        (False, None),
    ]

    class FakeCapture:
        def read(self):
            return results.pop(0)

    thread = VideoStreamThread("rtsp://cam/stream", fps=30)
    thread._running = True
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    thread._consume(FakeCapture())
    assert results == []  # un fallo aislado no corta el stream; tres seguidos sí


def test_on_frame_on_error_on_stopped_default_to_noop() -> None:
    """Sin callables explícitos, el hilo no debe lanzar al invocarlos."""
    thread = VideoStreamThread("rtsp://cam/stream")
    thread._on_frame(object())
    thread._on_error("algo falló")
    thread._on_stopped()
