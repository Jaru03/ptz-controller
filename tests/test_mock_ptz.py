"""Tests del controlador PTZ simulado (Mock)."""

import time

from camera.mock_ptz import MockPTZController


def test_initial_state_disconnected() -> None:
    mock = MockPTZController()
    assert not mock.connected
    status = mock.get_status()
    assert status.pan == 0.0
    assert status.tilt == 0.0
    assert status.zoom == 0.0


def test_connect_sets_connected() -> None:
    mock = MockPTZController()
    mock.connect()
    assert mock.connected
    assert mock.get_status().device_name == "Cámara simulada (Mock)"
    mock.disconnect()
    assert not mock.connected


def test_move_integrates_position() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=0.5)
    mock._advance(1.0)
    status = mock.get_status()
    assert status.pan == 0.5
    assert status.tilt == 0.0


def test_move_is_scaled_by_speed() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=1.0, tilt=-1.0, zoom=0.0, speed=1.0)
    mock._advance(0.25)
    status = mock.get_status()
    assert status.pan == 0.25
    assert status.tilt == -0.25


def test_position_clamped_to_unit_range() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(5.0)
    assert mock.get_status().pan == 1.0


def test_stop_freezes_movement() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(0.2)
    mock.stop()
    mock._advance(1.0)
    status = mock.get_status()
    assert status.pan == 0.2


def test_home_returns_to_center() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=1.0, tilt=1.0, zoom=1.0, speed=1.0)
    mock._advance(0.5)
    mock.home()
    status = mock.get_status()
    assert status.pan == 0.0
    assert status.tilt == 0.0
    assert status.zoom == 0.0


def test_presets_roundtrip() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=0.4, tilt=-0.3, zoom=0.1, speed=1.0)
    mock._advance(1.0)
    mock.set_preset("1")
    assert [p.token for p in mock.list_presets()] == ["1"]

    mock.move(pan=-1.0, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(1.0)
    mock.goto_preset("1")
    status = mock.get_status()
    assert status.pan == 0.4
    assert status.tilt == -0.3
    assert status.zoom == 0.1

    mock.remove_preset("1")
    assert mock.list_presets() == []


def test_goto_missing_preset_is_noop() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.goto_preset("99")
    assert mock.get_status().pan == 0.0


def test_set_preset_with_name_and_rename() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.move(pan=0.4, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(1.0)
    mock.set_preset("1", "Entrada principal")
    presets = mock.list_presets()
    assert presets[0].name == "Entrada principal"

    mock.rename_preset("1", "Patio")
    assert mock.list_presets()[0].name == "Patio"
    mock.goto_preset("1")
    assert mock.get_status().pan == 0.4

    mock.rename_preset("99", "Fantasma")
    assert [p.token for p in mock.list_presets()] == ["1"]


def test_preset_default_name_when_unnamed() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.set_preset("3")
    assert mock.list_presets()[0].name == "Preset 3"


def test_set_preset_without_token_assigns_the_next_free_one() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.set_preset(name="Primera")
    mock.set_preset(name="Segunda")
    assert [p.token for p in mock.list_presets()] == ["1", "2"]


def test_presets_keep_non_numeric_tokens() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.set_preset("PresetA", "Patio")
    mock.goto_preset("PresetA")
    assert [p.token for p in mock.list_presets()] == ["PresetA"]


def test_preset_name_survives_status() -> None:
    mock = MockPTZController()
    mock.connect()
    mock.set_preset("1", "Escena A")
    status = mock.get_status()
    assert status.presets[0].name == "Escena A"


def test_status_callback_receives_updates() -> None:
    received: list[object] = []

    def callback(status: object) -> None:
        received.append(status)

    mock = MockPTZController(status_callback=callback)
    mock.connect()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(0.5)
    assert len(received) > 0
    assert received[-1].pan == 0.5  # type: ignore[union-attr]


def test_move_ignored_when_disconnected() -> None:
    mock = MockPTZController()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
    mock._advance(1.0)
    assert mock.get_status().pan == 0.0


def test_background_thread_advances_position() -> None:
    mock = MockPTZController(tick_rate=50)
    mock.connect()
    mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
    time.sleep(0.3)
    status = mock.get_status()
    assert status.pan > 0.0
    mock.disconnect()
