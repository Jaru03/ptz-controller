"""Tests de gui_web/video_server.py (sin abrir ningún socket real)."""

import threading
import time

from gui_web.video_server import LatestFrameStore, VideoHttpServer


def test_latest_frame_store_returns_last_set_value() -> None:
    store = LatestFrameStore()
    store.set(b"frame1")
    store.set(b"frame2")

    assert store.get_blocking(timeout=0.1) == b"frame2"


def test_latest_frame_store_times_out_when_empty() -> None:
    store = LatestFrameStore()

    assert store.get_blocking(timeout=0.05) is None


def test_latest_frame_store_clear_removes_current_frame() -> None:
    store = LatestFrameStore()
    store.set(b"frame1")

    store.clear()

    assert store.get_blocking(timeout=0.05) is None


def test_latest_frame_store_wakes_waiters_on_set() -> None:
    """Un get_blocking() en curso debe recibir el frame en cuanto llega."""
    store = LatestFrameStore()
    result: list[bytes | None] = []

    def waiter() -> None:
        result.append(store.get_blocking(timeout=2.0))

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.05)  # asegura que el hilo ya está esperando
    store.set(b"nuevo-frame")
    thread.join(timeout=1.0)

    assert result == [b"nuevo-frame"]


def test_video_http_server_serves_the_latest_frame_over_http() -> None:
    import urllib.request

    server = VideoHttpServer()
    server.start()
    try:
        server.store.set(b"\xff\xd8fake-jpeg")
        url = f"http://127.0.0.1:{server.port}/stream"
        with urllib.request.urlopen(url, timeout=2.0) as response:
            assert response.status == 200
            assert "multipart/x-mixed-replace" in response.headers["Content-Type"]
            chunk = response.read(200)
            assert b"--frame" in chunk
            assert b"fake-jpeg" in chunk
    finally:
        server.stop()


def test_video_http_server_returns_404_for_other_paths() -> None:
    import urllib.error
    import urllib.request

    server = VideoHttpServer()
    server.start()
    try:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/otra-ruta", timeout=2.0)
            raise AssertionError("se esperaba HTTPError 404")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.stop()
