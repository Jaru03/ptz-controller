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

from camera.discovery import discover_devices
from config.settings import Settings
from core.event_bus import EventBus
from gui_web.serialize import to_json_safe
from models.commands import ConnectCommand, QuitCommand
from utils.logger import get_logger

log = get_logger(__name__)


class Api:
    """Métodos invocables desde JS vía ``window.pywebview.api``."""

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self._bus = bus
        self._settings = settings

    # -- Conexión -----------------------------------------------------

    def connect(self) -> dict:
        """Aplica los datos de conexión recibidos y pide conectar."""
        self._bus.send(ConnectCommand())
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

    def get_settings(self) -> dict:
        """Devuelve el ``Settings`` completo, ya en forma JSON."""
        return self._settings.to_dict()

    def quit(self) -> dict:
        self._bus.send(QuitCommand())
        return {"ok": True}
