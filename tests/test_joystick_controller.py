"""Tests de JoystickController (sin hardware SDL real)."""

from config.settings import JoystickConfig
from controllers.base import MovementState
from controllers.joystick_controller import JoystickController
from core.event_bus import EventBus


class _FakeJoystick:
    def __init__(self, name: str = "Mando de prueba") -> None:
        self._name = name

    def get_name(self) -> str:
        return self._name

    def get_guid(self) -> str:
        return "fake-guid"


class _FakeBroker:
    """Sustituye a PyGameEventBroker: sin SDL real, solo lo que usa el controller."""

    def __init__(self, joysticks: dict[int, _FakeJoystick]) -> None:
        self._joysticks = joysticks

    def subscribe(self, event_type, handler) -> None:  # noqa: ANN001 - firma de PyGameEventBroker
        pass

    def unsubscribe(self, event_type, handler) -> None:  # noqa: ANN001
        pass

    @property
    def instance_ids(self) -> list[int]:
        return list(self._joysticks.keys())

    def joystick_by_instance(self, instance_id: int) -> _FakeJoystick | None:
        return self._joysticks.get(instance_id)


def _controller() -> tuple[JoystickController, list[dict]]:
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe("input.joystick", received.append)
    config = JoystickConfig()
    movement = MovementState(deadzone=0.0, publish=bus.send)
    broker = _FakeBroker({0: _FakeJoystick()})
    controller = JoystickController(config, broker, movement, bus)
    controller._axes[0] = {config.pan_axis: 0.0, config.tilt_axis: 0.0}
    return controller, received


def test_resting_stick_within_deadzone_is_not_moving() -> None:
    controller, received = _controller()

    controller._recompute(0)

    # Dentro de la zona muerta: "moving" no cambia respecto al inicial
    # (False), así que no se publica nada todavía.
    assert received == []


def test_stick_past_deadzone_publishes_moving_true() -> None:
    controller, received = _controller()
    controller._axes[0][JoystickConfig().pan_axis] = 0.9

    controller._recompute(0)

    assert received[-1] == {"connected": True, "name": "Mando de prueba", "moving": True}


def test_returning_to_neutral_publishes_moving_false() -> None:
    controller, received = _controller()
    pan_axis = JoystickConfig().pan_axis
    controller._axes[0][pan_axis] = 0.9
    controller._recompute(0)

    controller._axes[0][pan_axis] = 0.0
    controller._recompute(0)

    assert received[-1] == {"connected": True, "name": "Mando de prueba", "moving": False}


def test_repeated_motion_past_deadzone_does_not_republish() -> None:
    """Movimientos pequeños del eje mientras se mantiene inclinado no deben
    inundar el bus: solo se publica cuando "moving" cambia de valor."""
    controller, received = _controller()
    pan_axis = JoystickConfig().pan_axis

    controller._axes[0][pan_axis] = 0.9
    controller._recompute(0)
    before = len(received)

    controller._axes[0][pan_axis] = 0.95
    controller._recompute(0)
    controller._axes[0][pan_axis] = 0.85
    controller._recompute(0)

    assert len(received) == before


def test_disconnecting_while_moving_resets_to_not_moving() -> None:
    controller, received = _controller()
    controller._axes[0][JoystickConfig().pan_axis] = 0.9
    controller._recompute(0)
    assert received[-1]["moving"] is True

    controller._on_device_removed(type("Event", (), {"instance_id": 0})())

    assert received[-1] == {"connected": False, "name": "", "moving": False}
