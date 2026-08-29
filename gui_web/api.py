"""API expuesta al frontend como ``window.pywebview.api`` (``js_api``).

Cada método corresponde a una acción que hoy dispara algún widget de
``gui/`` (PySide6). Los comandos del EventBus se envían con ``bus.send``
igual que hace la GUI actual: la API nunca toca ``CommandWorker`` ni el
controlador PTZ directamente, así el ``EventBus`` sigue siendo la única
fuente de verdad. pywebview resuelve cada llamada JS a estos métodos como
una Promise, incluidas las que tardan (como ``discover``), sin necesitar
un puente de hilo propio (a diferencia de ``_DiscoveryBridge`` en
``gui/connection_dialog.py``, pensado para marshalling hacia el hilo Qt).
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

from camera.discovery import discover_devices
from config.settings import Settings
from core.event_bus import EventBus
from gui_web.serialize import to_json_safe
from models.commands import (
    ConnectCommand,
    DisconnectCommand,
    GotoPresetCommand,
    QuitCommand,
    RemovePresetCommand,
    RenamePresetCommand,
    SetPresetCommand,
    SetSpeedCommand,
)
from models.version import RELEASES_PAGE, check_for_updates, get_version
from utils.logger import get_logger

log = get_logger(__name__)


class Api:
    """Métodos invocables desde JS vía ``window.pywebview.api``."""

    def __init__(self, bus: EventBus, settings: Settings, config_path: Path) -> None:
        self._bus = bus
        self._settings = settings
        self._config_path = config_path

    # -- Conexión -----------------------------------------------------

    def connect(self) -> dict:
        """Aplica los datos de conexión recibidos y pide conectar."""
        self._bus.send(ConnectCommand())
        return {"ok": True}

    def disconnect(self) -> dict:
        self._bus.send(DisconnectCommand())
        return {"ok": True}

    def apply_connection_settings(self, patch: dict) -> dict:
        """Actualiza ``settings.camera`` con el formulario de conexión."""
        camera = self._settings.camera
        if "ip" in patch:
            camera.ip = str(patch["ip"]).strip()
        if "port" in patch:
            camera.port = int(patch["port"])
        if "username" in patch:
            camera.username = str(patch["username"])
        if "password" in patch:
            camera.password = str(patch["password"])
        if "mock" in patch:
            camera.mock = bool(patch["mock"])
        return {"ok": True}

    def discover(self) -> list[dict]:
        """Busca cámaras ONVIF en la red local (WS-Discovery, ~4s)."""
        try:
            devices = discover_devices(timeout=4)
        except Exception as exc:  # noqa: BLE001 - se reporta al frontend
            log.error("Error en el descubrimiento: %s", exc)
            return []
        return [to_json_safe(device) for device in devices]

    # -- Presets --------------------------------------------------------

    def goto_preset(self, token: str) -> dict:
        self._bus.send(GotoPresetCommand(token))
        return {"ok": True}

    def set_preset(self, token: str, name: str) -> dict:
        self._bus.send(SetPresetCommand(token, name))
        return {"ok": True}

    def rename_preset(self, token: str, name: str) -> dict:
        self._bus.send(RenamePresetCommand(token, name))
        return {"ok": True}

    def remove_preset(self, token: str) -> dict:
        self._bus.send(RemovePresetCommand(token))
        return {"ok": True}

    # -- Velocidad --------------------------------------------------------

    def set_speed(self, speed: float) -> dict:
        self._bus.send(SetSpeedCommand(float(speed)))
        return {"ok": True}

    # -- Ajustes ----------------------------------------------------------

    def get_settings(self) -> dict:
        """Devuelve el ``Settings`` completo, ya en forma JSON."""
        return self._settings.to_dict()

    def save_settings(self, patch: dict) -> dict:
        """Aplica un parche de ajustes (cámara + movimiento) y lo persiste.

        Muta los campos del ``Settings`` vivo en vez de sustituirlo por
        una instancia nueva: otras partes de la app (los closures de
        ``main.py``, ``MovementState``...) guardan una referencia directa
        a este mismo objeto, así que reemplazarlo las dejaría leyendo
        datos obsoletos sin que nadie se entere.
        """
        camera_patch = patch.get("camera") or {}
        movement_patch = patch.get("movement") or {}

        camera = self._settings.camera
        if "ip" in camera_patch:
            camera.ip = str(camera_patch["ip"]).strip()
        if "port" in camera_patch:
            camera.port = int(camera_patch["port"])
        if "username" in camera_patch:
            camera.username = str(camera_patch["username"])
        if "password" in camera_patch:
            camera.password = str(camera_patch["password"])
        if "rtsp_url" in camera_patch:
            camera.rtsp_url = str(camera_patch["rtsp_url"]).strip()
        if "mock" in camera_patch:
            camera.mock = bool(camera_patch["mock"])

        movement = self._settings.movement
        if "speed" in movement_patch:
            movement.speed = float(movement_patch["speed"])
        if "deadzone" in movement_patch:
            movement.deadzone = float(movement_patch["deadzone"])
        if "zoom_mode" in movement_patch:
            movement.zoom_mode = str(movement_patch["zoom_mode"])

        self._settings.save(self._config_path)
        return self._settings.to_dict()

    # -- Controles (referencia de solo lectura) ------------------------------

    def get_controls_info(self) -> dict:
        """Vinculaciones de teclado/mando, para el panel de Controles.

        Devuelve la configuración cruda (``KeyboardConfig``/
        ``JoystickConfig``); el formateo a etiquetas legibles ('↑', 'Num
        1'...) vive en el frontend (``lib/keymap.ts::keyLabel``), igual
        que ``gui/controls_widget.py::_key_label`` vive en la GUI y no en
        ``config/settings.py``.
        """
        return {
            "keyboard": to_json_safe(self._settings.keyboard),
            "joystick": to_json_safe(self._settings.joystick),
        }

    # -- Actualizaciones ----------------------------------------------------

    def get_version(self) -> str:
        return get_version()

    def check_for_updates(self) -> dict:
        return to_json_safe(check_for_updates())

    def open_releases_page(self) -> dict:
        """Abre la página de releases en el navegador del sistema.

        Equivalente a ``QDesktopServices.openUrl`` en
        gui/updates_widget.py: pywebview no navega la propia ventana
        (eso la sacaría de la app), así que se delega al navegador
        externo del sistema operativo vía ``webbrowser``.
        """
        webbrowser.open(RELEASES_PAGE)
        return {"ok": True}

    # -- Ciclo de vida ------------------------------------------------------

    def quit(self) -> dict:
        self._bus.send(QuitCommand())
        return {"ok": True}
