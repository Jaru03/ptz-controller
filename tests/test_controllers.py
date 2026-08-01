"""Tests del estado de movimiento y del controlador de teclado."""

import os
import time

from config.settings import KeyboardConfig
from controllers.base import MovementState
from controllers.keyboard_controller import (
    KeyboardController,
    QtKeyboardController,
    create_keyboard_controller,
    qt_key_name,
)
from core.event_bus import EventBus
from models.commands import (
    GotoPresetCommand,
    MoveCommand,
    QuitCommand,
    SetSpeedCommand,
    StopCommand,
)


def _capture(bus: EventBus) -> list:
    received: list = []
    bus.subscribe("command.move", lambda c: received.append(c))
    bus.subscribe("command.stop", lambda c: received.append(c))
    bus.subscribe("command.setSpeed", lambda c: received.append(c))
    bus.subscribe("command.home", lambda c: received.append(c))
    bus.subscribe("command.gotoPreset", lambda c: received.append(c))
    bus.subscribe("command.quit", lambda c: received.append(c))
    return received


def test_movement_state_publishes_stop_when_neutral() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.0, publish=bus.send)
    state.update(1.0, 0.0, 0.0)
    state.update(0.0, 0.0, 0.0)
    assert isinstance(received[0], MoveCommand)
    assert isinstance(received[1], StopCommand)


def test_movement_state_skips_duplicate_directions() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.0, publish=bus.send)
    state.update(1.0, 0.0, 0.0)
    state.update(1.0, 0.0, 0.0)
    state.update(1.0, 0.0, 0.0)
    assert len(received) == 1
    assert isinstance(received[0], MoveCommand)


def test_movement_state_publishes_only_on_direction_change() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.0, publish=bus.send)
    state.update(1.0, 0.0, 0.0)   # derecha
    state.update(1.0, 1.0, 0.0)   # diagonal -> cambio
    state.update(1.0, 1.0, 0.0)   # sin cambio
    state.update(-1.0, 1.0, 0.0)  # otra diagonal -> cambio
    assert [type(c) for c in received] == [MoveCommand, MoveCommand, MoveCommand]


def test_deadzone_zeroes_small_inputs() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.2, publish=bus.send)
    state.update(0.1, 0.0, 0.0)
    assert received == []  # dentro de la zona muerta -> nada


def test_deadzone_resscales_proportional() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.2, publish=bus.send)
    state.update(0.6, 0.0, 0.0)
    command = received[0]
    assert isinstance(command, MoveCommand)
    assert abs(command.pan - 0.5) < 1e-6  # (0.6-0.2)/(1-0.2)


def test_set_speed_reemits_current_direction() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(deadzone=0.0, publish=bus.send)
    state.update(1.0, 0.0, 0.0)
    state.set_speed(1.0)
    assert len(received) == 2
    assert received[1].speed == 1.0  # type: ignore[union-attr]


def test_movement_state_repeats_while_held() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(
        deadzone=0.0, publish=bus.send, repeat_interval=0.02
    )
    state.update(1.0, 0.0, 0.0)
    time.sleep(0.09)
    moves = [c for c in received if isinstance(c, MoveCommand)]
    assert len(moves) >= 2
    state.update(0.0, 0.0, 0.0)
    assert isinstance(received[-1], StopCommand)


def test_movement_state_stops_repeating_after_neutral() -> None:
    bus = EventBus()
    received = _capture(bus)
    state = MovementState(
        deadzone=0.0, publish=bus.send, repeat_interval=0.02
    )
    state.update(1.0, 0.0, 0.0)
    time.sleep(0.06)
    assert sum(isinstance(c, MoveCommand) for c in received) >= 2
    state.update(0.0, 0.0, 0.0)
    time.sleep(0.06)
    moves_after_stop = sum(isinstance(c, MoveCommand) for c in received)
    assert isinstance(received[-1], StopCommand)
    time.sleep(0.06)
    assert sum(isinstance(c, MoveCommand) for c in received) == moves_after_stop


def test_keyboard_wasd_movement() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("w")
    controller.on_key_down("d")
    assert len(received) == 2  # 'w' y 'd' son independientes pero publican en cambio
    last = received[-1]
    assert isinstance(last, MoveCommand)
    assert last.tilt == 1.0
    assert last.pan == 1.0
    controller.on_key_up("d")
    assert isinstance(received[-1], MoveCommand)
    assert received[-1].pan == 0.0
    controller.on_key_up("w")
    assert isinstance(received[-1], StopCommand)


def test_keyboard_zoom_and_hold_still() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("e")
    controller.on_key_down("e")
    assert len(received) == 1  # tecla repetida no reenvía
    assert received[0].zoom == 1.0  # type: ignore[union-attr]


def test_keyboard_preset_hotkeys_goto_scenes() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("1")
    controller.on_key_down("3")
    gotos = [c for c in received if isinstance(c, GotoPresetCommand)]
    assert [c.preset_id for c in gotos] == [1, 3]
    assert not any(isinstance(c, SetSpeedCommand) for c in received)


def test_keyboard_preset_hotkey_stops_movement() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("w")
    controller.on_key_down("1")
    assert isinstance(received[-1], GotoPresetCommand)


def test_keyboard_esc_publishes_quit() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("esc")
    assert any(isinstance(c, QuitCommand) for c in received)


def test_keyboard_space_publishes_stop() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("w")
    controller.on_key_down("space")
    assert isinstance(received[-1], StopCommand)


def test_qt_key_name_conversion() -> None:
    # No se construye un QKeyEvent real aquí: probamos la lógica del mapeo
    # con un objeto que simule la interfaz mínima.
    class FakeEvent:
        def __init__(self, text, key):
            self._text = text
            self._key = key

        def text(self):
            return self._text

        def key(self):
            return self._key

    from PySide6.QtCore import Qt

    assert qt_key_name(FakeEvent("W", 0)) == "w"
    assert qt_key_name(FakeEvent(" ", Qt.Key_Space)) == "space"
    assert qt_key_name(FakeEvent("", Qt.Key_Escape)) == "esc"
    assert qt_key_name(FakeEvent("", 123456)) == ""


def test_preset_command_not_published_by_keyboard() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("q")
    assert not any(isinstance(c, GotoPresetCommand) for c in received)


def test_create_keyboard_controller_prefers_qt_on_wayland(
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    bus = EventBus()
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = create_keyboard_controller(config, state, bus)
    assert isinstance(controller, QtKeyboardController)


def test_create_keyboard_controller_uses_pynput_off_wayland(
    monkeypatch,
) -> None:
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    bus = EventBus()
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = create_keyboard_controller(config, state, bus)
    try:
        assert not isinstance(controller, QtKeyboardController)
    finally:
        controller.stop()
