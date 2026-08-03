"""Tests del controlador ONVIF y del recorrido completo teclado -> cámara."""

import time

from camera.client import CameraError
from camera.ptz_controller import OnvifPTZController
from config.settings import KeyboardConfig
from controllers.base import MovementState, PresetRegistry
from controllers.keyboard_controller import KeyboardController
from core.command_worker import CommandWorker
from core.event_bus import EventBus
from camera.mock_ptz import MockPTZController
from models.commands import PTZStatus


class _FakeClient:
    """Cliente ONVIF de mentira que anota las llamadas recibidas."""

    def __init__(self, relative_fails: bool = False) -> None:
        self.calls: list[tuple] = []
        self.relative_fails = relative_fails

    def continuous_move(self, pan, tilt, zoom, speed) -> None:
        self.calls.append(("continuous", pan, tilt, zoom, speed))

    def relative_move(self, pan, tilt, zoom) -> None:
        if self.relative_fails:
            raise CameraError("RelativeMove no soportado")
        self.calls.append(("relative", pan, tilt, round(zoom, 6)))

    def stop(self, pan_tilt: bool = True, zoom: bool = True) -> None:
        self.calls.append(("stop", pan_tilt, zoom))

    def stop_inactive_axes(self, pan_tilt: bool, zoom: bool) -> None:
        self.calls.append(("stop_inactive", pan_tilt, zoom))


def _controller(zoom_mode: str, relative_fails: bool = False) -> OnvifPTZController:
    controller = OnvifPTZController("1.2.3.4", 80, "admin", "", zoom_mode=zoom_mode)
    controller._client = _FakeClient(relative_fails=relative_fails)
    controller._status = PTZStatus(connected=True)
    return controller


def test_zoom_step_mode_uses_relative_move() -> None:
    controller = _controller("step")
    controller.move(pan=0.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert controller._client.calls == [
        ("stop_inactive", False, False),
        ("relative", 0.0, 0.0, 0.06),
    ]


def test_zoom_step_alone_never_sends_a_continuous_move() -> None:
    # Un ContinuousMove con todos los ejes a cero se traduce en un Stop
    # que llegaría entre pasos y abortaría el zoom anterior.
    controller = _controller("step")
    for _ in range(4):
        controller.move(pan=0.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert not any(call[0] == "continuous" for call in controller._client.calls)
    assert sum(call[0] == "relative" for call in controller._client.calls) == 4


def test_zoom_step_scales_with_speed() -> None:
    controller = _controller("step")
    controller.move(pan=0.0, tilt=0.0, zoom=-1.0, speed=0.5)
    assert controller._client.calls[-1] == ("relative", 0.0, 0.0, -0.03)


def test_zoom_step_keeps_pan_tilt_continuous() -> None:
    controller = _controller("step")
    controller.move(pan=1.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert controller._client.calls[0] == ("continuous", 1.0, 0.0, 0.0, 1.0)


def test_zoom_continuous_mode_never_uses_relative_move() -> None:
    controller = _controller("continuous")
    controller.move(pan=0.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert controller._client.calls == [("continuous", 0.0, 0.0, 1.0, 1.0)]


def test_zoom_auto_falls_back_to_continuous() -> None:
    controller = _controller("auto", relative_fails=True)
    controller.move(pan=0.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert controller._client.calls[-1] == ("continuous", 0.0, 0.0, 1.0, 1.0)

    # El fallback es permanente: no se reintenta en cada pulsación.
    controller._client.calls.clear()
    controller.move(pan=0.0, tilt=0.0, zoom=1.0, speed=1.0)
    assert controller._client.calls == [("continuous", 0.0, 0.0, 1.0, 1.0)]


def test_move_without_zoom_is_always_continuous() -> None:
    controller = _controller("step")
    controller.move(pan=1.0, tilt=-1.0, zoom=0.0, speed=0.8)
    assert controller._client.calls == [("continuous", 1.0, -1.0, 0.0, 0.8)]


# -- Recorrido completo: tecla -> bus -> worker -> cámara --------------------


def _wire_app(mock: MockPTZController) -> tuple[EventBus, CommandWorker, KeyboardController]:
    """Reproduce el cableado de main.py sin GUI."""
    bus = EventBus()
    worker = CommandWorker(name="test-ptz")
    worker.start()
    bus.subscribe(
        "command.gotoPreset",
        lambda cmd: worker.submit(lambda: mock.goto_preset(cmd.token)),
    )
    presets = PresetRegistry(bus)
    movement = MovementState(deadzone=0.0, publish=bus.send)
    keyboard = KeyboardController(KeyboardConfig(), movement, bus, presets=presets)
    bus.publish("ptz.presets", mock.list_presets())
    return bus, worker, keyboard


def _mock_with_scenes(tokens: dict[str, float]) -> MockPTZController:
    """Cámara simulada con una escena por token, cada una en un pan distinto."""
    mock = MockPTZController()
    mock.connect()
    for token, pan in tokens.items():
        mock.move(pan=1.0, tilt=0.0, zoom=0.0, speed=1.0)
        mock._advance(pan)
        mock.stop()
        mock.set_preset(token, f"Escena {token}")
        mock.home()
    return mock


def _pan_of_scene(mock: MockPTZController, position: int, pans: dict[str, float]) -> float:
    """Pan guardado en la escena que ocupa esa posición en la lista."""
    return pans[mock.list_presets()[position].token]


def test_number_key_reaches_the_scene_in_that_position() -> None:
    pans = {"PresetA": 0.1, "zona-norte": 0.2, "7": 0.3, "PresetD": 0.4}
    mock = _mock_with_scenes(pans)
    expected = _pan_of_scene(mock, 3, pans)  # la 4ª escena, token no numérico

    bus, worker, keyboard = _wire_app(mock)
    try:
        keyboard.on_key_down("4")
        time.sleep(0.2)
        assert round(mock.get_status().pan, 6) == expected
    finally:
        worker.stop()


def test_numpad_key_reaches_the_scene_in_that_position() -> None:
    pans = {"escena-a": 0.5, "escena-b": 0.7}
    mock = _mock_with_scenes(pans)
    expected = _pan_of_scene(mock, 1, pans)

    bus, worker, keyboard = _wire_app(mock)
    try:
        keyboard.on_key_down("kp_2")
        time.sleep(0.2)
        assert round(mock.get_status().pan, 6) == expected
    finally:
        worker.stop()


def test_keys_beyond_the_third_are_not_ignored() -> None:
    pans = {f"escena-{index}": index / 10 for index in range(1, 9)}
    mock = _mock_with_scenes(pans)

    bus, worker, keyboard = _wire_app(mock)
    try:
        for key in ("4", "5", "6", "7", "8"):
            expected = _pan_of_scene(mock, int(key) - 1, pans)
            keyboard.on_key_down(key)
            keyboard.on_key_up(key)
            time.sleep(0.1)
            assert round(mock.get_status().pan, 6) == expected
    finally:
        worker.stop()
