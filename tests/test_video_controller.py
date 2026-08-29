"""Tests de gui_web/video_controller.py (sin captura RTSP real)."""

import gui_web.video_controller as video_controller_module
from core.event_bus import EventBus
from gui_web.video_controller import VideoController
from gui_web.video_server import VideoHttpServer


class _FakeThread:
    """Sustituye a VideoStreamThread: no arranca ningún hilo de verdad."""

    instances: list["_FakeThread"] = []

    def __init__(self, url, fps, transport, on_frame=None, on_error=None, on_stopped=None):
        self.url = url
        self.on_frame = on_frame
        self.on_error = on_error
        self.stopped = False
        _FakeThread.instances.append(self)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True


def _controller(monkeypatch) -> tuple[VideoController, EventBus, list[dict]]:
    _FakeThread.instances = []
    monkeypatch.setattr(video_controller_module, "VideoStreamThread", _FakeThread)
    bus = EventBus()
    states: list[dict] = []
    bus.subscribe("gui.streamState", states.append)
    server = VideoHttpServer()
    controller = VideoController(bus, server, fps=15, transport="tcp")
    return controller, bus, states


def test_empty_url_publishes_stopped_state(monkeypatch) -> None:
    # "" es el valor inicial de _url: la transición real es tras haber
    # tenido una URL (p. ej. al desconectar), no en el arranque en frío.
    controller, bus, states = _controller(monkeypatch)
    bus.publish("ptz.stream", "rtsp://cam/stream")
    first = _FakeThread.instances[0]

    bus.publish("ptz.stream", "")

    assert states[-1]["status"] == "stopped"
    assert first.stopped is True


def test_url_starts_a_capture_thread_and_publishes_connecting(monkeypatch) -> None:
    controller, bus, states = _controller(monkeypatch)

    bus.publish("ptz.stream", "rtsp://cam/stream")

    assert states[-1]["status"] == "connecting"
    assert len(_FakeThread.instances) == 1
    assert _FakeThread.instances[0].url == "rtsp://cam/stream"


def test_same_url_is_a_no_op(monkeypatch) -> None:
    controller, bus, states = _controller(monkeypatch)

    bus.publish("ptz.stream", "rtsp://cam/stream")
    bus.publish("ptz.stream", "rtsp://cam/stream")

    assert len(_FakeThread.instances) == 1  # no se reinicia el hilo


def test_new_url_stops_the_previous_thread(monkeypatch) -> None:
    controller, bus, states = _controller(monkeypatch)

    bus.publish("ptz.stream", "rtsp://cam1/stream")
    first = _FakeThread.instances[0]
    bus.publish("ptz.stream", "rtsp://cam2/stream")

    assert first.stopped is True
    assert len(_FakeThread.instances) == 2


def test_on_frame_stores_jpeg_and_publishes_streaming(monkeypatch) -> None:
    import numpy

    controller, bus, states = _controller(monkeypatch)
    bus.publish("ptz.stream", "rtsp://cam/stream")
    thread = _FakeThread.instances[0]

    frame = numpy.zeros((4, 4, 3), dtype=numpy.uint8)
    thread.on_frame(frame)

    assert states[-1]["status"] == "streaming"
    assert controller._server.store.get_blocking(timeout=0.1) is not None


def test_repeated_frames_do_not_republish_streaming_state(monkeypatch) -> None:
    import numpy

    controller, bus, states = _controller(monkeypatch)
    bus.publish("ptz.stream", "rtsp://cam/stream")
    thread = _FakeThread.instances[0]
    frame = numpy.zeros((4, 4, 3), dtype=numpy.uint8)

    before = len(states)
    thread.on_frame(frame)
    thread.on_frame(frame)
    thread.on_frame(frame)

    # "connecting" -> "streaming" es un único cambio; los frames
    # siguientes no deben inundar el bus con el mismo estado.
    assert len(states) == before + 1


def test_on_error_publishes_error_state(monkeypatch) -> None:
    controller, bus, states = _controller(monkeypatch)
    bus.publish("ptz.stream", "rtsp://cam/stream")
    thread = _FakeThread.instances[0]

    thread.on_error("no se pudo abrir el stream")

    assert states[-1]["status"] == "error"
    assert states[-1]["message"] == "no se pudo abrir el stream"


def test_stop_clears_store_and_stops_thread(monkeypatch) -> None:
    controller, bus, states = _controller(monkeypatch)
    bus.publish("ptz.stream", "rtsp://cam/stream")
    thread = _FakeThread.instances[0]
    controller._server.store.set(b"algo")

    controller.stop()

    assert thread.stopped is True
    assert controller._server.store.get_blocking(timeout=0.05) is None
