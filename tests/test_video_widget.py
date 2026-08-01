"""Pruebas del widget de vídeo RTSP."""

import logging
import os

from gui.video_widget import (
    VideoStreamThread,
    build_ffmpeg_loglevel,
    build_ffmpeg_options,
)
from utils.logger import APP_LOGGER_NAME


def test_ffmpeg_options_default_to_tcp() -> None:
    opts = build_ffmpeg_options("tcp")
    assert "rtsp_transport;tcp" in opts
    assert "stimeout;" in opts
    assert "|" in opts


def test_ffmpeg_options_udp_only_transport() -> None:
    opts = build_ffmpeg_options("udp")
    assert opts == "rtsp_transport;udp"


def test_ffmpeg_options_allow_multiple_parsers() -> None:
    parts = build_ffmpeg_options("tcp").split("|")
    assert {p.split(";")[0] for p in parts} >= {"rtsp_transport", "stimeout"}


def test_ffmpeg_loglevel_silenced_outside_debug(monkeypatch) -> None:
    monkeypatch.setattr(logging.getLogger(APP_LOGGER_NAME), "level", logging.INFO)
    assert build_ffmpeg_loglevel() == "0"


def test_ffmpeg_loglevel_verbose_in_debug(monkeypatch) -> None:
    monkeypatch.setattr(logging.getLogger(APP_LOGGER_NAME), "level", logging.DEBUG)
    assert build_ffmpeg_loglevel() == "32"


def test_open_capture_sets_ffmpeg_options(monkeypatch) -> None:
    import cv2

    opened: list[str] = []

    class FakeCapture:
        def __init__(self, url, api):
            opened.append(url)

        def isOpened(self):
            return True

    monkeypatch.setattr(cv2, "VideoCapture", FakeCapture)
    thread = VideoStreamThread("rtsp://cam/stream", transport="udp")
    thread._open_capture()
    assert opened == ["rtsp://cam/stream"]
    assert os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;udp"
    assert "OPENCV_FFMPEG_LOGLEVEL" in os.environ
