"""Interfaz de control PTZ independiente del protocolo.

``PTZController`` define el contrato que usan el resto de capas
(entrada, GUI, servicio). ``OnvifPTZController`` lo implementa sobre
ONVIF; ``MockPTZController`` (en ``camera.mock_ptz``) lo hace sobre un
estado virtual. Esto permite probar y desarrollar sin hardware y, en el
futuro, sustituir ONVIF por otro protocolo sin tocar el resto del
sistema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.commands import PTZStatus, PresetInfo
from utils.logger import get_logger

from camera.client import CameraError, OnvifClient

log = get_logger(__name__)


class PTZController(ABC):
    """Contrato mínimo de un controlador PTZ.

    Todos los vectores (pan/tilt/zoom) usan valores normalizados en el
    rango -1.0..1.0. La velocidad global se expresa en 0.0..1.0.
    """

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Indica si el controlador tiene una conexión activa."""

    @abstractmethod
    def connect(self) -> None:
        """Establece la conexión con la cámara.

        Raises:
            CameraError: si no se puede conectar.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Cierra la conexión de forma ordenada."""

    @abstractmethod
    def move(self, pan: float, tilt: float, zoom: float, speed: float) -> None:
        """Mueve la cámara de forma continua (velocidades normalizadas)."""

    @abstractmethod
    def stop(self) -> None:
        """Detiene el movimiento en curso."""

    @abstractmethod
    def home(self) -> None:
        """Vuelve a la posición de inicio."""

    @abstractmethod
    def goto_preset(self, preset_id: int) -> None:
        """Desplaza la cámara hasta un preset guardado."""

    @abstractmethod
    def set_preset(self, preset_id: int, name: str = "") -> None:
        """Guarda la posición actual con el identificador y nombre dados."""

    @abstractmethod
    def rename_preset(self, preset_id: int, name: str) -> None:
        """Cambia el nombre de un preset existente."""

    @abstractmethod
    def remove_preset(self, preset_id: int) -> None:
        """Elimina un preset."""

    @abstractmethod
    def list_presets(self) -> list[PresetInfo]:
        """Devuelve los presets disponibles."""

    @abstractmethod
    def get_status(self) -> PTZStatus:
        """Devuelve la instantánea actual del estado de la cámara."""

    def stream_uri(self) -> str:
        """URL RTSP del stream principal (vacío si no está disponible).

        No abstracta a propósito: el mock (y cualquier controlador sin
        vídeo) hereda el comportamiento de devolver cadena vacía.
        """
        return ""


class OnvifPTZController(PTZController):
    """Implementación de ``PTZController`` sobre el protocolo ONVIF."""

    def __init__(self, ip: str, port: int, username: str, password: str) -> None:
        self._client = OnvifClient(ip, port, username, password)
        self._device_name = ""
        self._status = PTZStatus(connected=False, ip=ip)

    @property
    def connected(self) -> bool:
        return self._status.connected

    @property
    def client(self) -> OnvifClient:
        return self._client

    def connect(self) -> None:
        log.info("Conectando con la cámara ONVIF %s:%s ...", self._client.ip, self._client.port)
        try:
            self._client.connect()
        except CameraError as exc:
            log.error("Fallo de conexión ONVIF: %s", exc)
            raise
        info = self._client.device_info()
        self._device_name = info.get("Manufacturer", "") or "ONVIF"
        profiles = self._client.profiles()
        self._client.select_ptz_profile(profiles)
        self._status = PTZStatus(
            connected=True,
            device_name=self._device_name,
            ip=self._client.ip,
        )
        log.info("Conectado: %s (perfil PTZ: %s)", self._device_name, self._client.profile_token)

    def disconnect(self) -> None:
        self._client.disconnect()
        self._status = self._status.__class__(
            connected=False,
            device_name=self._device_name,
            ip=self._client.ip,
        )
        log.info("Cámara desconectada")

    def move(self, pan: float, tilt: float, zoom: float, speed: float) -> None:
        if not self.connected:
            log.warning("move() ignorado: cámara no conectada")
            return
        try:
            self._client.continuous_move(pan, tilt, zoom, speed)
        except CameraError as exc:
            log.error("Error en ContinuousMove: %s", exc)

    def stop(self) -> None:
        if not self.connected:
            return
        try:
            self._client.stop()
        except CameraError as exc:
            log.error("Error en Stop: %s", exc)

    def home(self) -> None:
        if not self.connected:
            return
        try:
            self._client.home()
        except CameraError as exc:
            log.error("Error en home: %s", exc)

    def goto_preset(self, preset_id: int) -> None:
        if not self.connected:
            return
        try:
            self._client.goto_preset(preset_id)
            log.info("GotoPreset %s ejecutado", preset_id)
        except CameraError as exc:
            log.error("Error en GotoPreset %s: %s", preset_id, exc)

    def set_preset(self, preset_id: int, name: str = "") -> None:
        if not self.connected:
            return
        try:
            self._client.set_preset(preset_id, name)
            log.info(
                "SetPreset %s ejecutado%s", preset_id, f" (nombre: {name})" if name else ""
            )
        except CameraError as exc:
            log.error("Error en SetPreset %s: %s", preset_id, exc)

    def rename_preset(self, preset_id: int, name: str) -> None:
        if not self.connected:
            return
        try:
            self._client.rename_preset(preset_id, name)
            log.info("Preset %s renombrado a '%s'", preset_id, name)
        except CameraError as exc:
            log.error("Error al renombrar preset %s: %s", preset_id, exc)

    def remove_preset(self, preset_id: int) -> None:
        if not self.connected:
            return
        try:
            self._client.remove_preset(preset_id)
            log.info("RemovePreset %s ejecutado", preset_id)
        except CameraError as exc:
            log.error("Error en RemovePreset %s: %s", preset_id, exc)

    def list_presets(self) -> list[PresetInfo]:
        if not self.connected:
            return []
        try:
            return self._client.get_presets()
        except CameraError as exc:
            log.error("Error en GetPresets: %s", exc)
            return []

    def get_status(self) -> PTZStatus:
        if not self.connected:
            return self._status
        try:
            position = self._client.get_position()
            self._status = PTZStatus(
                connected=True,
                pan=position["pan"],
                tilt=position["tilt"],
                zoom=position["zoom"],
                device_name=self._device_name,
                ip=self._client.ip,
            )
        except CameraError as exc:
            log.error("Error en GetStatus: %s", exc)
        return self._status

    def stream_uri(self) -> str:
        if not self.connected:
            return ""
        try:
            return self._client.stream_uri()
        except CameraError as exc:
            log.error("Error al obtener la URL RTSP: %s", exc)
            return ""
