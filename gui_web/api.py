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
from controllers.keyboard_controller import KeyboardController
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

_KEYBOARD_ACTION_FIELDS = (
    "up",
    "down",
    "left",
    "right",
    "zoom_in",
    "zoom_out",
    "stop",
    "quit",
)


def _duplicate_keyboard_key(
    action_keys: dict[str, str], preset_keys: list[str], preset_hotkeys: dict[str, str]
) -> str | None:
    """Primera tecla usada en más de una acción, o ``None`` si no hay conflicto."""
    counts: dict[str, int] = {}
    for key in [*action_keys.values(), *preset_keys, *preset_hotkeys.keys()]:
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return next((key for key, count in counts.items() if count > 1), None)


class Api:
    """Métodos invocables desde JS vía ``window.pywebview.api``."""

    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        config_path: Path,
        keyboard: KeyboardController | None = None,
    ) -> None:
        self._bus = bus
        self._settings = settings
        self._config_path = config_path
        self._keyboard = keyboard

    # -- Conexión -----------------------------------------------------

    def connect(self) -> dict:
        """Aplica los datos de conexión recibidos y pide conectar."""
        self._bus.send(ConnectCommand())
        return {"ok": True}

    def disconnect(self) -> dict:
        self._bus.send(DisconnectCommand())
        return {"ok": True}

    def apply_connection_settings(self, patch: dict) -> dict:
        """Actualiza ``settings.camera`` con el formulario de conexión y lo persiste.

        Única fuente de verdad para los datos de identidad de la cámara
        (IP, credenciales, RTSP, mock): la usan tanto la pantalla inicial
        (``ConnectionScreen``) como el diálogo de reconexión
        (``ConnectionDialog``). ``SettingsDialog`` no toca estos campos,
        solo el comportamiento de movimiento (ver ``save_settings``).
        """
        camera = self._settings.camera
        if "ip" in patch:
            camera.ip = str(patch["ip"]).strip()
        if "port" in patch:
            camera.port = int(patch["port"])
        if "username" in patch:
            camera.username = str(patch["username"])
        if "password" in patch:
            camera.password = str(patch["password"])
        if "rtsp_url" in patch:
            camera.rtsp_url = str(patch["rtsp_url"]).strip()
        if "mock" in patch:
            camera.mock = bool(patch["mock"])
        self._settings.save(self._config_path)
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
        """Aplica un parche de ajustes de movimiento y lo persiste.

        Los datos de identidad de la cámara (IP, credenciales, RTSP,
        mock) no se tocan aquí: viven exclusivamente en
        ``apply_connection_settings``, para no duplicar el mismo
        formulario en dos diálogos con semánticas de guardado distintas.

        Muta los campos del ``Settings`` vivo en vez de sustituirlo por
        una instancia nueva: otras partes de la app (los closures de
        ``main.py``, ``MovementState``...) guardan una referencia directa
        a este mismo objeto, así que reemplazarlo las dejaría leyendo
        datos obsoletos sin que nadie se entere.
        """
        movement_patch = patch.get("movement") or {}

        movement = self._settings.movement
        if "speed" in movement_patch:
            movement.speed = float(movement_patch["speed"])
        if "deadzone" in movement_patch:
            movement.deadzone = float(movement_patch["deadzone"])
        if "zoom_mode" in movement_patch:
            movement.zoom_mode = str(movement_patch["zoom_mode"])

        self._settings.save(self._config_path)
        return self._settings.to_dict()

    def save_keyboard_settings(self, patch: dict) -> dict:
        """Aplica un parche de mapeo de teclado y lo persiste.

        Igual que ``save_settings``, muta ``self._settings.keyboard`` en
        vez de sustituirlo: es la misma instancia que sostiene el
        ``KeyboardController`` en marcha (ver ``main.py``), así que las
        reasignaciones de tecla se aplican en caliente, sin reiniciar
        nada.

        Antes de aplicar valida que ninguna tecla quede asignada a dos
        acciones a la vez (movimiento, detener, salir o una escena): si
        hay conflicto no se guarda nada y se devuelve el error para que
        la interfaz lo muestre sin perder la edición en curso.
        """
        keyboard = self._settings.keyboard

        action_keys = {field: getattr(keyboard, field) for field in _KEYBOARD_ACTION_FIELDS}
        for field in _KEYBOARD_ACTION_FIELDS:
            if field in patch:
                action_keys[field] = str(patch[field]).strip().lower()
        if any(not key for key in action_keys.values()):
            return {"ok": False, "error": "Ninguna acción puede quedarse sin tecla asignada"}

        preset_keys = list(keyboard.preset_keys)
        if "preset_keys" in patch:
            preset_keys = [str(key).strip().lower() for key in patch["preset_keys"]]

        preset_hotkeys = dict(keyboard.preset_hotkeys)
        if "preset_hotkeys" in patch:
            preset_hotkeys = {
                str(key).strip().lower(): str(token)
                for key, token in dict(patch["preset_hotkeys"]).items()
            }

        conflict = _duplicate_keyboard_key(action_keys, preset_keys, preset_hotkeys)
        if conflict:
            return {
                "ok": False,
                "error": f"La tecla '{conflict}' ya está asignada a otra acción",
            }

        for field, value in action_keys.items():
            setattr(keyboard, field, value)
        keyboard.preset_keys = preset_keys
        keyboard.preset_hotkeys = preset_hotkeys
        if "backend" in patch:
            keyboard.backend = str(patch["backend"])

        self._settings.save(self._config_path)
        return {"ok": True, "settings": self._settings.to_dict()}

    # -- Teclado (backend "window") ------------------------------------------

    def keyboard_requires_window_events(self) -> bool:
        """Indica si el controlador de teclado en marcha necesita que el
        frontend le reenvíe los ``keydown``/``keyup`` de JS.

        Se consulta el controlador en marcha, no ``settings.keyboard.
        backend``: con backend 'auto' el valor configurado no dice cuál
        de los dos (pynput o ventana) terminó arrancando en este intento
        concreto — es la misma comprobación que hacía
        ``MainWindow.eventFilter`` con ``self._keyboard.requires_window_events``.
        """
        return bool(self._keyboard and self._keyboard.requires_window_events)

    def key_down(self, name: str) -> None:
        if self._keyboard is not None and self._keyboard.requires_window_events:
            self._keyboard.on_key_down(name)

    def key_up(self, name: str) -> None:
        if self._keyboard is not None and self._keyboard.requires_window_events:
            self._keyboard.on_key_up(name)

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
