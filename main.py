"""Punto de entrada del controlador de cámaras PTZ ONVIF.

Compone las capas (configuración, cámara, entrada, GUI) y las une a
través del bus de eventos. Uso:

    uv run python main.py                 # modo simulado (Mock)
    uv run python main.py --real          # cámara ONVIF real (config.yaml)
    uv run python main.py --config ruta   # configuración alternativa
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from camera.ptz_controller import OnvifPTZController, PTZController
from camera.mock_ptz import MockPTZController
from config.settings import Settings
from controllers.base import MovementState
from controllers.joystick_controller import JoystickController
from controllers.keyboard_controller import create_keyboard_controller
from controllers.pygame_events import PyGameEventBroker
from core.event_bus import EventBus
from core.ref import Ref
from gui.main_window import MainWindow
from models.commands import PTZStatus
from utils.logger import attach_gui_handler, get_logger, setup_logging

log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controlador universal de cámaras PTZ ONVIF"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help="Ruta del archivo de configuración YAML",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Forzar el modo simulado (Mock), sin cámara física",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Forzar el modo cámara real (ONVIF)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging (por defecto el de la configuración)",
    )
    parser.add_argument(
        "--no-joystick",
        action="store_true",
        help="No iniciar el controlador de joystick",
    )
    return parser.parse_args(argv)


def create_ptz_controller(settings: Settings, mock: bool) -> PTZController:
    """Crea el controlador PTZ según el modo elegido."""
    camera = settings.camera
    if mock:
        controller: PTZController = MockPTZController(
            ip=camera.ip,
            port=camera.port,
            username=camera.username,
            password=camera.password,
        )
        log.info("Modo simulado (Mock): no se usa ninguna cámara física")
        return controller
    controller = OnvifPTZController(
        ip=camera.ip,
        port=camera.port,
        username=camera.username,
        password=camera.password,
    )
    log.info("Modo cámara real (ONVIF) configurado para %s:%s", camera.ip, camera.port)
    return controller


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config_path = Path(args.config)
    settings = Settings.ensure_default_config(config_path)
    for warning in settings.validate():
        log.warning("Configuración: %s", warning)

    level = args.log_level or settings.logging.level
    setup_logging(level=level, log_dir=settings.logging.directory)

    mock = args.mock or (settings.camera.mock and not args.real)

    bus = EventBus()
    ref = Ref(create_ptz_controller(settings, mock))

    movement = MovementState(
        deadzone=settings.movement.deadzone,
        publish=bus.send,
        initial_speed=settings.movement.speed,
        repeat_interval=settings.movement.repeat_interval_ms / 1000.0,
    )

    # -- Entrada ----------------------------------------------------------

    keyboard = create_keyboard_controller(settings.keyboard, movement, bus)

    broker = PyGameEventBroker(poll_rate=settings.joystick.poll_rate)
    joystick: JoystickController | None = None
    if not args.no_joystick:
        joystick = JoystickController(settings.joystick, broker, movement, bus)
        broker.start()
        joystick.start()

    # -- Enrutado de comandos ---------------------------------------------

    def handle_connect() -> None:
        try:
            ref.value.disconnect()
        except Exception:  # noqa: BLE001 - conexión previa inexistente
            pass
        if mock:
            ref.value = create_ptz_controller(settings, mock=True)
        else:
            ref.value = create_ptz_controller(settings, mock=False)
        try:
            ref.value.connect()
        except Exception as exc:  # noqa: BLE001 - errores de conexión variados
            log.error("No se pudo conectar: %s", exc)
            bus.publish("gui.error", f"No se pudo conectar con la cámara:\n{exc}")
        bus.publish("ptz.status", ref.value.get_status())
        bus.publish("ptz.presets", ref.value.list_presets())

    def handle_disconnect() -> None:
        ref.value.stop()
        try:
            ref.value.disconnect()
        except Exception as exc:  # noqa: BLE001
            log.error("Error al desconectar: %s", exc)
        bus.publish("ptz.status", ref.value.get_status())
        bus.publish("ptz.presets", [])

    bus.subscribe("command.connect", lambda _cmd: handle_connect())
    bus.subscribe("command.disconnect", lambda _cmd: handle_disconnect())
    bus.subscribe(
        "command.move",
        lambda cmd: ref.value.move(cmd.pan, cmd.tilt, cmd.zoom, cmd.speed),
    )
    bus.subscribe("command.stop", lambda _cmd: ref.value.stop())
    bus.subscribe("command.home", lambda _cmd: ref.value.home())
    bus.subscribe(
        "command.gotoPreset", lambda cmd: ref.value.goto_preset(cmd.preset_id)
    )
    bus.subscribe(
        "command.setPreset", lambda cmd: ref.value.set_preset(cmd.preset_id, cmd.name)
    )
    bus.subscribe(
        "command.renamePreset",
        lambda cmd: ref.value.rename_preset(cmd.preset_id, cmd.name),
    )
    bus.subscribe(
        "command.removePreset", lambda cmd: ref.value.remove_preset(cmd.preset_id)
    )
    bus.subscribe("command.setSpeed", lambda cmd: movement.set_speed(cmd.speed))

    # -- GUI --------------------------------------------------------------

    app = QApplication(sys.argv[:1])
    app.setApplicationName("ptz-controller")

    poll_interval = settings.gui.poll_interval_ms if mock else 500
    window = MainWindow(
        controller_ref=ref,
        bus=bus,
        settings=settings,
        keyboard_controller=keyboard,
        config_path=str(config_path),
        poll_interval_ms=poll_interval,
    )
    attach_gui_handler(log, window.append_log)
    window.show()
    log.info("Aplicación iniciada (modo: %s)", "mock" if mock else "real")

    # -- Cierre ordenado --------------------------------------------------

    quit_guard = {"done": False}

    def on_quit() -> None:
        if quit_guard["done"]:
            return
        quit_guard["done"] = True
        log.info("Cerrando aplicación…")
        keyboard.stop()
        if joystick is not None:
            joystick.stop()
        broker.stop()
        try:
            ref.value.stop()
            ref.value.disconnect()
        except Exception:  # noqa: BLE001 - cierre tolerante a errores
            pass
        try:
            settings.save(config_path)
        except OSError as exc:
            log.error("No se pudo guardar la configuración: %s", exc)
        app.quit()

    bus.subscribe("command.quit", lambda _cmd: on_quit())

    exit_code = app.exec()
    log.info("Aplicación finalizada")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
