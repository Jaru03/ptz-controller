"""Tests del estado de movimiento y del controlador de teclado."""

import time

from config.settings import KeyboardConfig
from controllers.base import MovementState
from controllers.keyboard_controller import (
    KeyboardController,
    WindowKeyboardController,
    create_keyboard_controller,
    hotkey_for_preset,
    key_aliases,
)
from core.event_bus import EventBus
from models.commands import (
    GotoPresetCommand,
    MoveCommand,
    PresetInfo,
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


def _controller_with_presets(bus: EventBus, tokens: list[str]):
    """Controlador de teclado con una lista de presets ya publicada."""
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    bus.publish("ptz.presets", [PresetInfo(token=token) for token in tokens])
    return config, controller


def test_keyboard_preset_keys_resolve_by_position() -> None:
    bus = EventBus()
    received = _capture(bus)
    _controller_with_presets(bus, ["PresetA", "12", "zona-norte"])[1].on_key_down("1")
    gotos = [c for c in received if isinstance(c, GotoPresetCommand)]
    assert [c.token for c in gotos] == ["PresetA"]


def test_keyboard_preset_keys_reach_beyond_the_first_three() -> None:
    bus = EventBus()
    received = _capture(bus)
    _, controller = _controller_with_presets(
        bus, [f"p{index}" for index in range(1, 11)]
    )
    for key in ("4", "7", "0"):
        controller.on_key_down(key)
        controller.on_key_up(key)
    gotos = [c for c in received if isinstance(c, GotoPresetCommand)]
    assert [c.token for c in gotos] == ["p4", "p7", "p10"]


def test_keyboard_numpad_falls_back_to_its_digit() -> None:
    bus = EventBus()
    received = _capture(bus)
    _, controller = _controller_with_presets(bus, ["PresetA", "PresetB"])
    controller.on_key_down("kp_2")
    gotos = [c for c in received if isinstance(c, GotoPresetCommand)]
    assert [c.token for c in gotos] == ["PresetB"]


def test_keyboard_explicit_hotkey_wins_over_position() -> None:
    bus = EventBus()
    received = _capture(bus)
    config, controller = _controller_with_presets(bus, ["PresetA", "PresetB"])
    config.preset_hotkeys = {"kp_1": "zona-norte", "f1": "PresetB"}
    controller.on_key_down("kp_1")
    controller.on_key_down("f1")
    gotos = [c for c in received if isinstance(c, GotoPresetCommand)]
    assert [c.token for c in gotos] == ["zona-norte", "PresetB"]


def test_keyboard_preset_key_without_preset_does_nothing() -> None:
    bus = EventBus()
    received = _capture(bus)
    _, controller = _controller_with_presets(bus, ["PresetA"])
    controller.on_key_down("5")
    assert not any(isinstance(c, GotoPresetCommand) for c in received)
    assert not any(isinstance(c, SetSpeedCommand) for c in received)


def test_keyboard_preset_hotkey_stops_movement() -> None:
    bus = EventBus()
    received = _capture(bus)
    _, controller = _controller_with_presets(bus, ["PresetA"])
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


def test_key_aliases_fall_back_from_numpad_to_digit() -> None:
    assert key_aliases("kp_3") == ("kp_3", "3")
    assert key_aliases("kp_enter") == ("kp_enter",)
    assert key_aliases("w") == ("w",)


def test_preset_command_not_published_by_keyboard() -> None:
    bus = EventBus()
    received = _capture(bus)
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = KeyboardController(config, state, bus)
    controller.on_key_down("q")
    assert not any(isinstance(c, GotoPresetCommand) for c in received)


def test_hotkey_for_preset_uses_position_and_explicit_map() -> None:
    config = KeyboardConfig()
    assert hotkey_for_preset(config, 0, "PresetA") == "1"
    assert hotkey_for_preset(config, 9, "PresetJ") == "0"
    assert hotkey_for_preset(config, 12, "PresetM") == ""

    config.preset_hotkeys = {"f1": "PresetM"}
    assert hotkey_for_preset(config, 12, "PresetM") == "f1"


def test_hotkey_for_preset_prefers_exact_token_match_over_position() -> None:
    # El token "7" es en sí una tecla válida de preset_keys: debe ganar a
    # la posición, aunque esa posición (5, o sea "6") corresponda a otra
    # tecla distinta.
    config = KeyboardConfig()
    assert hotkey_for_preset(config, 5, "7") == "7"


def test_create_keyboard_controller_prefers_window_on_wayland(
    monkeypatch,
) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    bus = EventBus()
    config = KeyboardConfig()
    state = MovementState(deadzone=0.0, publish=bus.send)
    controller = create_keyboard_controller(config, state, bus)
    assert isinstance(controller, WindowKeyboardController)


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
        assert not isinstance(controller, WindowKeyboardController)
    finally:
        controller.stop()
