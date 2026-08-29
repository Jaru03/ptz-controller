"""Punto de entrada del controlador de cámaras PTZ ONVIF.

Compone las capas (configuración, cámara, entrada, GUI) y las une a
través del bus de eventos. Uso:

    uv run python main.py                 # modo simulado (Mock)
    uv run python main.py --real          # cámara ONVIF real (config.yaml)
    uv run python main.py --config ruta   # configuración alternativa
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import QApplication, QDialog

from camera.ptz_controller import OnvifPTZController, PTZController
from camera.mock_ptz import MockPTZController
from config.settings import Settings
from controllers.base import MovementState, PresetRegistry
from controllers.joystick_controller import JoystickController
from controllers.keyboard_controller import create_keyboard_controller
from controllers.pygame_events import PyGameEventBroker
from core.command_worker import CommandWorker
from core.event_bus import EventBus
from core.ref import Ref
from gui.connection_dialog import ConnectionDialog
from gui.main_window import MainWindow
from gui_web.api import Api
from gui_web.bridge import EventBridge
from gui_web.poller import StatusPoller
from gui_web.video_controller import VideoController
from gui_web.video_server import VideoHttpServer
from models.commands import ConnectCommand, PTZStatus, QuitCommand
from utils.logger import get_logger, setup_logging
from utils.paths import (
    bundled_file,
    default_config_path,
    default_log_dir,
    frontend_index_html,
    is_frozen,
)

log = get_logger(__name__)

DEFAULT_CONFIG_PATH = default_config_path()


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
    parser.add_argument(
        "--web-gui",
        action="store_true",
        help=(
            "Usar el frontend web (React/pywebview) en vez de la GUI "
            "PySide6. Temporal, mientras dura la migración a pywebview."
        ),
    )
    return parser.parse_args(argv)


def prepare_config(path: Path) -> Settings:
    """Carga la configuración, creándola la primera vez si no existe.

    Si el programa lleva empaquetado un ``config.yaml.example`` se usa
    como plantilla: así el usuario encuentra el archivo comentado en vez
    de un volcado de valores por defecto.
    """
    if not path.exists():
        template = bundled_file("config.yaml.example")
        if template is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, path)
            log.info("Configuración inicial creada en %s", path)
    return Settings.ensure_default_config(path)


def resolve_mock(args: argparse.Namespace, settings: Settings) -> bool:
    """Decide si se usa el modo simulado (Mock).

    Precedencia: ``--mock`` y ``--real`` explicitos y, si no se indica
    nada, la configuración en desarrollo. El ejecutable empaquetado
    (PyInstaller, ``sys.frozen``) arranca en modo real por defecto:
    así el binario publicado controla la cámara ONVIF sin más
    argumentos y ``--mock`` queda reservado para pruebas de humo.
    """
    if args.mock:
        return True
    if args.real:
        return False
    return False if sys.frozen else settings.camera.mock


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
        zoom_mode=settings.movement.zoom_mode,
        zoom_step=settings.movement.zoom_step,
    )
    log.info("Modo cámara real (ONVIF) configurado para %s:%s", camera.ip, camera.port)
    return controller


def _run_web_gui(
    *,
    bus: EventBus,
    settings: Settings,
    config_path: Path,
    keyboard: Any,
    joystick: JoystickController | None,
    broker: PyGameEventBroker,
    worker: CommandWorker,
    ref: Ref,
    poll_status: Callable[[], None],
) -> int:
    """Arranca el frontend web (React) dentro de una ventana pywebview.

    Fase de migración: mientras ``gui_web``/``frontend`` no cubran todo lo
    que hace ``gui/`` (PySide6), esto es un camino alternativo detrás de
    ``--web-gui`` — ``MainWindow`` sigue siendo la GUI por defecto.
    """
    import webview

    index_html = frontend_index_html()
    if not index_html.is_file():
        log.error(
            "No se encuentra %s: compile el frontend antes de usar "
            "--web-gui ('cd frontend && npm install && npm run build')",
            index_html,
        )
        return 1

    api = Api(bus, settings)
    window_ref: dict[str, Any] = {"window": None}
    EventBridge(bus, lambda: window_ref["window"])
    # settings.camera.mock puede cambiar en caliente (ConnectionScreen),
    # así que el intervalo se recalcula en cada ciclo (ver StatusPoller).
    poller = StatusPoller(
        poll_status,
        interval_ms=lambda: (
            settings.gui.poll_interval_ms if settings.camera.mock else 500
        ),
    )

    video_server = VideoHttpServer()
    video_server.start()
    video_controller = VideoController(
        bus,
        video_server,
        fps=settings.gui.video_fps,
        transport=settings.gui.rtsp_transport,
    )

    quit_guard = {"done": False}

    def on_quit() -> None:
        if quit_guard["done"]:
            return
        quit_guard["done"] = True
        log.info("Cerrando aplicación…")
        poller.stop()
        video_controller.stop()
        video_server.stop()
        keyboard.stop()
        if joystick is not None:
            joystick.stop()
        broker.stop()
        worker.stop()
        try:
            ref.value.stop()
            ref.value.disconnect()
        except Exception:  # noqa: BLE001 - cierre tolerante a errores
            pass
        try:
            settings.save(config_path)
        except OSError as exc:
            log.error("No se pudo guardar la configuración: %s", exc)

    bus.subscribe("command.quit", lambda _cmd: on_quit())

    window = webview.create_window(
        "Controlador de cámaras PTZ ONVIF",
        url=f"{index_html.as_uri()}?videoPort={video_server.port}",
        js_api=api,
        width=1100,
        height=720,
    )
    window_ref["window"] = window
    window.events.closed += lambda: bus.send(QuitCommand())

    def on_started() -> None:
        # Estado inicial, igual que MainWindow.__init__: así el frontend
        # no arranca vacío a la espera del primer tick del poller.
        #
        # Tiene que ir en el callback de arranque de webview.start(), NO
        # justo tras create_window: publicar antes de que el bucle de
        # eventos de GTK esté corriendo hace que EventBridge llame a
        # evaluate_js() sobre una ventana que aún no puede atenderlo, y
        # evaluate_js() se queda bloqueado para siempre (confirmado con
        # un script de prueba aislado: colgaba justo ahí, de forma no
        # determinista según el timing).
        bus.publish("ptz.status", ref.value.get_status())
        bus.publish("ptz.presets", ref.value.list_presets())
        poller.start()

    log.info("Aplicación iniciada (web-gui)")
    webview.start(on_started, debug=not is_frozen())
    on_quit()
    log.info("Aplicación finalizada")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    config_path = Path(args.config)
    settings = prepare_config(config_path)
    for warning in settings.validate():
        log.warning("Configuración: %s", warning)

    level = args.log_level or settings.logging.level
    setup_logging(level=level, log_dir=default_log_dir(settings.logging.directory))

    mock = resolve_mock(args, settings)

    bus = EventBus()
    ref = Ref(create_ptz_controller(settings, mock))

    movement = MovementState(
        deadzone=settings.movement.deadzone,
        publish=bus.send,
        initial_speed=settings.movement.speed,
        repeat_interval=settings.movement.repeat_interval_ms / 1000.0,
    )

    # -- Entrada ----------------------------------------------------------

    presets = PresetRegistry(bus)
    keyboard = create_keyboard_controller(settings.keyboard, movement, bus, presets)

    broker = PyGameEventBroker(poll_rate=settings.joystick.poll_rate)
    joystick: JoystickController | None = None
    if not args.no_joystick:
        joystick = JoystickController(
            settings.joystick, broker, movement, bus, presets=presets
        )
        broker.start()
        joystick.start()

    # -- Enrutado de comandos ---------------------------------------------
    #
    # Todo el trabajo de la cámara (peticiones SOAP por red) se ejecuta en
    # el hilo del worker: si se hiciera en el hilo que publica el comando
    # bloquearía la GUI, que es quien recibe las teclas y pinta el vídeo.

    worker = CommandWorker()
    worker.start()

    def publish_status() -> None:
        bus.publish("ptz.status", ref.value.get_status())

    def publish_presets() -> None:
        bus.publish("ptz.presets", ref.value.list_presets())

    def publish_stream_uri() -> None:
        url = settings.camera.rtsp_url.strip() or ref.value.stream_uri()
        bus.publish("ptz.stream", url)

    def with_presets(action: Callable[[], None]) -> Callable[[], None]:
        """Envuelve una acción sobre presets para republicar la lista."""

        def job() -> None:
            action()
            publish_presets()

        return job

    def handle_connect() -> None:
        try:
            ref.value.disconnect()
        except Exception:  # noqa: BLE001 - conexión previa inexistente
            pass
        ref.value = create_ptz_controller(settings, mock=mock)
        try:
            ref.value.connect()
        except Exception as exc:  # noqa: BLE001 - errores de conexión variados
            log.error("No se pudo conectar: %s", exc)
            bus.publish("gui.error", f"No se pudo conectar con la cámara:\n{exc}")
        publish_status()
        publish_presets()
        publish_stream_uri()

    def handle_disconnect() -> None:
        ref.value.stop()
        try:
            ref.value.disconnect()
        except Exception as exc:  # noqa: BLE001
            log.error("Error al desconectar: %s", exc)
        publish_status()
        bus.publish("ptz.presets", [])
        bus.publish("ptz.stream", "")

    bus.subscribe("command.connect", lambda _cmd: worker.submit(handle_connect))
    bus.subscribe("command.disconnect", lambda _cmd: worker.submit(handle_disconnect))
    bus.subscribe(
        "command.move",
        lambda cmd: worker.submit(
            lambda: ref.value.move(cmd.pan, cmd.tilt, cmd.zoom, cmd.speed),
            key="move",
        ),
    )
    bus.subscribe(
        "command.stop",
        lambda _cmd: worker.submit(
            lambda: ref.value.stop(), key="stop", cancels=("move",)
        ),
    )
    bus.subscribe("command.home", lambda _cmd: worker.submit(lambda: ref.value.home()))
    bus.subscribe(
        "command.gotoPreset",
        lambda cmd: worker.submit(lambda: ref.value.goto_preset(cmd.token)),
    )
    bus.subscribe(
        "command.setPreset",
        lambda cmd: worker.submit(
            with_presets(lambda: ref.value.set_preset(cmd.token, cmd.name))
        ),
    )
    bus.subscribe(
        "command.renamePreset",
        lambda cmd: worker.submit(
            with_presets(lambda: ref.value.rename_preset(cmd.token, cmd.name))
        ),
    )
    bus.subscribe(
        "command.removePreset",
        lambda cmd: worker.submit(
            with_presets(lambda: ref.value.remove_preset(cmd.token))
        ),
    )
    bus.subscribe("command.setSpeed", lambda cmd: movement.set_speed(cmd.speed))

    # -- GUI --------------------------------------------------------------

    if args.web_gui:
        return _run_web_gui(
            bus=bus,
            settings=settings,
            config_path=config_path,
            keyboard=keyboard,
            joystick=joystick,
            broker=broker,
            worker=worker,
            ref=ref,
            poll_status=lambda: worker.submit(publish_status, key="status"),
        )

    app = QApplication(sys.argv[:1])
    app.setApplicationName("ptz-controller")

    connection_dialog = ConnectionDialog(settings)
    if connection_dialog.exec() != QDialog.DialogCode.Accepted:
        log.info("Conexión cancelada por el usuario; cerrando aplicación")
        keyboard.stop()
        if joystick is not None:
            joystick.stop()
        broker.stop()
        worker.stop()
        return 0
    connection_dialog.apply_to_settings()
    mock = resolve_mock(args, settings)

    poll_interval = settings.gui.poll_interval_ms if mock else 500
    window = MainWindow(
        controller_ref=ref,
        bus=bus,
        settings=settings,
        keyboard_controller=keyboard,
        config_path=str(config_path),
        poll_interval_ms=poll_interval,
        poll_status=lambda: worker.submit(publish_status, key="status"),
    )
    window.show()
    log.info("Aplicación iniciada (modo: %s)", "mock" if mock else "real")
    bus.send(ConnectCommand())

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
        worker.stop()
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
