"""Cliente ONVIF: envoltorio fino sobre ``onvif`` (onvif-zeep).

Encapsula los servicios Media, PTZ y Device. Traduce los errores de
SOAP/zeep a excepciones propias (``CameraError``) y expone los vectores
en coordenadas normalizadas -1..1, igual que la interfaz ``PTZController``.
"""

from __future__ import annotations

import os
import zlib
from pathlib import Path
from typing import Any

import onvif
from onvif import ONVIFCamera  # onvif-zeep (módulo ``onvif``)

from models.commands import PresetInfo
from utils.logger import get_logger

log = get_logger(__name__)

STREAM_SETUP = {
    "Stream": "RTP-Unicast",
    "Transport": {"Protocol": "RTSP"},
}


def _resolve_wsdl_dir() -> str:
    """Localiza el directorio WSDL de onvif-zeep en el entorno.

    onvif-zeep 0.2.12 empaqueta los ficheros WSDL con una ruta ``data``
    dirigida a Python 3.14, por lo que según el instalador pueden acabar en
    ``lib/python3.14/site-packages/wsdl`` mientras que el código los busca
    en ``site-packages/wsdl``. Se comprueba la ubicación canónica y, si no
    existe, se busca en los site-packages de todas las versiones de Python
    del venv actual.
    """
    onvif_pkg = Path(getattr(onvif, "__file__", "")).resolve().parent
    site = onvif_pkg.parent  # .../lib/pythonX.Y/site-packages
    expected = site / "wsdl"
    if expected.is_dir():
        return str(expected)
    lib_dir = site.parent.parent  # .../lib
    for py_dir in sorted(lib_dir.iterdir()):
        candidate = py_dir / "site-packages" / "wsdl"
        if candidate.is_dir():
            return str(candidate)
    return str(expected)


class CameraError(Exception):
    """Error producido al interactuar con una cámara ONVIF."""


class OnvifClient:
    """Cliente ONVIF para una cámara concreta.

    La creación del cliente zeep descarga los WSDL la primera vez; la
    conexión real (autenticación + lectura de perfiles) ocurre en
    :meth:`connect`.
    """

    def __init__(
        self,
        ip: str,
        port: int,
        username: str,
        password: str,
        timeout: int = 5,
    ) -> None:
        self.ip = ip
        self.port = port
        self._username = username
        self._password = password
        self._timeout = timeout
        self._camera: ONVIFCamera | None = None
        self._media: Any = None
        self._ptz: Any = None
        self._device: Any = None
        self.profile_token: str | None = None
        self._stream_uri: str = ""
        self._preset_tokens: dict[int, str] = {}

    # -- Ciclo de vida ----------------------------------------------------

    def connect(self) -> None:
        """Crea los servicios ONVIF y selecciona el primer perfil PTZ."""
        try:
            self._camera = ONVIFCamera(
                self.ip,
                self.port,
                self._username,
                self._password,
                wsdl_dir=_resolve_wsdl_dir(),
                no_cache=True,
            )
        except Exception as exc:  # noqa: BLE001 - errores de red/soap variados
            raise CameraError(f"No se pudo crear el cliente ONVIF: {exc}") from exc

        try:
            self._device = self._camera.create_devicemgmt_service()
            self._media = self._camera.create_media_service()
            self._ptz = self._camera.create_ptz_service()
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"No se pudieron crear los servicios ONVIF: {exc}") from exc

        profiles = self.profiles()
        self.select_ptz_profile(profiles)

    def disconnect(self) -> None:
        self._camera = None
        self._media = None
        self._ptz = None
        self._device = None
        self.profile_token = None
        self._stream_uri = ""
        self._preset_tokens = {}

    # -- Información del dispositivo -------------------------------------

    def device_info(self) -> dict[str, str]:
        """Devuelve la información del dispositivo (GetDeviceInformation)."""
        if self._device is None:
            raise CameraError("Cliente no conectado")
        try:
            raw = self._device.GetDeviceInformation()
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GetDeviceInformation falló: {exc}") from exc
        return {
            "Manufacturer": _getattr(raw, "Manufacturer"),
            "Model": _getattr(raw, "Model"),
            "FirmwareVersion": _getattr(raw, "FirmwareVersion"),
            "SerialNumber": _getattr(raw, "SerialNumber"),
        }

    def profiles(self) -> list[Any]:
        """Devuelve los perfiles Media de la cámara (GetProfiles)."""
        if self._media is None:
            raise CameraError("Cliente no conectado")
        try:
            return list(self._media.GetProfiles())
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GetProfiles falló: {exc}") from exc

    def select_ptz_profile(self, profiles: list[Any]) -> None:
        """Elige el primer perfil con capacidad PTZ."""
        if not profiles:
            raise CameraError("La cámara no expone perfiles Media")
        candidate = next(
            (p for p in profiles if getattr(p, "PTZConfiguration", None) is not None),
            profiles[0],
        )
        self.profile_token = str(_getattr(candidate, "token"))
        log.debug("Perfil PTZ seleccionado: %s", self.profile_token)

    def stream_uri(self) -> str:
        """Devuelve la URL RTSP de la cámara (GetStreamUri)."""
        if self._media is None or self.profile_token is None:
            raise CameraError("Cliente no conectado o sin perfil")
        if not self._stream_uri:
            try:
                result = self._media.GetStreamUri(
                    {
                        "ProfileToken": self.profile_token,
                        "StreamSetup": STREAM_SETUP,
                    }
                )
                self._stream_uri = str(_getattr(result, "Uri"))
            except Exception as exc:  # noqa: BLE001
                raise CameraError(f"GetStreamUri falló: {exc}") from exc
        return self._stream_uri

    # -- Control PTZ ------------------------------------------------------

    def continuous_move(
        self, pan: float, tilt: float, zoom: float, speed: float
    ) -> None:
        """Envía un ContinuousMove con velocidades normalizadas."""
        self._require_ptz()
        velocity = {
            "PanTilt": {"x": _clamp(pan * speed), "y": _clamp(tilt * speed)},
            "Zoom": {"x": _clamp(zoom * speed)},
        }
        try:
            self._ptz.ContinuousMove(
                {"ProfileToken": self.profile_token, "Velocity": velocity}
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"ContinuousMove falló: {exc}") from exc

    def stop(self) -> None:
        """Detiene el movimiento (Stop con pan/tilt y zoom)."""
        self._require_ptz()
        try:
            self._ptz.Stop(
                {
                    "ProfileToken": self.profile_token,
                    "PanTilt": True,
                    "Zoom": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"Stop falló: {exc}") from exc

    def absolute_move(self, pan: float, tilt: float, zoom: float) -> None:
        """Desplaza a una posición absoluta normalizada (AbsoluteMove)."""
        self._require_ptz()
        try:
            self._ptz.AbsoluteMove(
                {
                    "ProfileToken": self.profile_token,
                    "Position": {"PanTilt": {"x": _clamp(pan), "y": _clamp(tilt)}, "Zoom": {"x": _clamp(zoom)}},
                    "Speed": {"PanTilt": {"x": 1.0, "y": 1.0}, "Zoom": {"x": 1.0}},
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"AbsoluteMove falló: {exc}") from exc

    def relative_move(self, pan: float, tilt: float, zoom: float) -> None:
        """Desplazamiento relativo (RelativeMove)."""
        self._require_ptz()
        try:
            self._ptz.RelativeMove(
                {
                    "ProfileToken": self.profile_token,
                    "Translation": {"PanTilt": {"x": _clamp(pan), "y": _clamp(tilt)}, "Zoom": {"x": _clamp(zoom)}},
                    "Speed": {"PanTilt": {"x": 1.0, "y": 1.0}, "Zoom": {"x": 1.0}},
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"RelativeMove falló: {exc}") from exc

    def home(self) -> None:
        """Vuelve a la posición inicial (preset 'home' o coordenada 0)."""
        self._require_ptz()
        try:
            presets = self.get_presets()
        except CameraError:
            presets = []
        home_preset = next(
            (p for p in presets if p.name.lower() in ("home", "inicio")), None
        )
        if home_preset is not None:
            self.goto_preset(home_preset.preset_id)
            return
        try:
            self._ptz.AbsoluteMove(
                {
                    "ProfileToken": self.profile_token,
                    "Position": {"PanTilt": {"x": 0.0, "y": 0.0}, "Zoom": {"x": 0.0}},
                    "Speed": {"PanTilt": {"x": 1.0, "y": 1.0}, "Zoom": {"x": 1.0}},
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"home falló: {exc}") from exc

    def goto_preset(self, preset_id: int) -> None:
        """Desplaza la cámara a un preset (GotoPreset).

        Usa el token ONVIF real de la cámara (ver :meth:`get_presets`), de
        modo que funcionan presets cuyo token no es un número.
        """
        self._require_ptz()
        try:
            self._ptz.GotoPreset(
                {
                    "ProfileToken": self.profile_token,
                    "PresetToken": self._preset_token(preset_id),
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GotoPreset falló: {exc}") from exc

    def set_preset(self, preset_id: int, name: str = "") -> None:
        """Guarda la posición actual como preset (SetPreset).

        Si ``name`` no está vacío, se asigna ese nombre al preset. El
        estándar ONVIF no ofrece un comando de renombrado propio: si el
        ``PresetToken`` ya existe y solo se envía un nombre, la mayoría de
        cámaras actualizan el nombre conservando la posición guardada.
        """
        self._require_ptz()
        request = {
            "ProfileToken": self.profile_token,
            "PresetToken": str(preset_id),
        }
        if name:
            request["Name"] = name
        try:
            self._ptz.SetPreset(request)
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"SetPreset falló: {exc}") from exc

    def rename_preset(self, preset_id: int, name: str) -> None:
        """Cambia el nombre de un preset (SetPreset con token y Name).

        ONVIF no define ``RenamePreset``; se reutiliza SetPreset sobre el
        token existente. En la mayoría de cámaras solo se actualiza el
        nombre; algunas pueden recalibrar la posición con la actual.
        """
        self._require_ptz()
        if not name:
            raise CameraError("No se puede renombrar un preset sin nombre")
        try:
            self._ptz.SetPreset(
                {
                    "ProfileToken": self.profile_token,
                    "PresetToken": self._preset_token(preset_id),
                    "Name": name,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"SetPreset (renombrar) falló: {exc}") from exc

    def remove_preset(self, preset_id: int) -> None:
        """Elimina un preset (RemovePreset)."""
        self._require_ptz()
        try:
            self._ptz.RemovePreset(
                {
                    "ProfileToken": self.profile_token,
                    "PresetToken": self._preset_token(preset_id),
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"RemovePreset falló: {exc}") from exc

    def get_presets(self) -> list[PresetInfo]:
        """Devuelve la lista de presets (GetPresets).

        Los presets de la cámara pueden usar tokens no numéricos (p. ej.
        'PresetA' o UUIDs). Se conserva el token real y se genera un
        ``preset_id`` numérico estable solo para la interfaz.
        """
        self._require_ptz()
        try:
            raw_presets = list(self._ptz.GetPresets({"ProfileToken": self.profile_token}))
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GetPresets falló: {exc}") from exc
        presets: list[PresetInfo] = []
        self._preset_tokens = {}
        for preset in raw_presets:
            token = str(_getattr(preset, "token") or "").strip()
            if not token:
                continue
            name = str(_getattr(preset, "Name") or "").strip() or f"Preset {token}"
            preset_id = self._preset_id_for_token(token)
            self._preset_tokens[preset_id] = token
            presets.append(PresetInfo(preset_id=preset_id, name=name, token=token))
        return presets

    def get_position(self) -> dict[str, float]:
        """Devuelve la posición actual normalizada (GetStatus)."""
        self._require_ptz()
        try:
            raw = self._ptz.GetStatus({"ProfileToken": self.profile_token})
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GetStatus falló: {exc}") from exc
        position = _getattr(raw, "Position")
        pan_tilt = _getattr(position, "PanTilt")
        zoom = _getattr(position, "Zoom")
        return {
            "pan": float(_getattr(pan_tilt, "x", 0.0) or 0.0),
            "tilt": float(_getattr(pan_tilt, "y", 0.0) or 0.0),
            "zoom": float(_getattr(zoom, "x", 0.0) or 0.0),
        }

    # -- Internos ---------------------------------------------------------

    def _require_ptz(self) -> None:
        if self._ptz is None or self.profile_token is None:
            raise CameraError("Cliente ONVIF no conectado o sin perfil PTZ")

    def _preset_token(self, preset_id: int) -> str:
        """Devuelve el token ONVIF real del preset (o su número como texto)."""
        return self._preset_tokens.get(preset_id, str(preset_id))

    @staticmethod
    def _preset_id_for_token(token: str) -> int:
        """Convierte un token ONVIF a un id numérico estable para la GUI.

        Si el token es numérico se usa tal cual; si no, se deriva un
        entero determinista (los tokens de la cámara no cambian).
        """
        try:
            return int(token)
        except ValueError:
            return zlib.crc32(token.encode("utf-8")) & 0x7FFFFFFF


def _getattr(obj: Any, name: str, default: Any = "") -> Any:
    """Lee un atributo tolerando objetos zeep/None."""
    if obj is None:
        return default
    value = getattr(obj, name, default)
    if value is None:
        return default
    return value


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, float(value)))
