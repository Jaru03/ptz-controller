"""Cliente ONVIF: envoltorio fino sobre ``onvif`` (onvif-zeep).

Encapsula los servicios Media, PTZ y Device. Traduce los errores de
SOAP/zeep a excepciones propias (``CameraError``) y expone los vectores
en coordenadas normalizadas -1..1, igual que la interfaz ``PTZController``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import onvif
from onvif import ONVIFCamera  # onvif-zeep (módulo ``onvif``)
from zeep.transports import Transport

from models.commands import PresetInfo
from utils.logger import get_logger
from utils.paths import resource_dir

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

    En un ejecutable empaquetado los WSDL viajan dentro del bundle, así
    que esa copia tiene prioridad: sin ella la conexión ONVIF falla al
    crear el cliente zeep.
    """
    bundled = resource_dir() / "wsdl"
    if bundled.is_dir():
        return str(bundled)
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
        self._moving_pan_tilt = False
        self._moving_zoom = False

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
                transport=self._build_transport(),
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
        self._moving_pan_tilt = False
        self._moving_zoom = False

    def _build_transport(self) -> Transport:
        """Transporte zeep con timeouts explícitos.

        Sin ellos, ``requests`` espera indefinidamente (``connect
        timeout=None``): una cámara que deja de responder bloquea el hilo
        que hace la llamada durante minutos.
        """
        return Transport(timeout=self._timeout, operation_timeout=self._timeout)

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
        """Envía un ContinuousMove con velocidades normalizadas.

        Solo se incluyen los ejes con velocidad distinta de cero: algunas
        cámaras ignoran el zoom si reciben un ``PanTilt`` vacío a la vez,
        y el estándar ONVIF permite omitir los componentes inactivos.

        Omitir un eje **no lo detiene**: la cámara mantiene la última
        velocidad recibida para él. Por eso, cuando un eje que estaba
        activo deja de estarlo, se envía antes un ``Stop`` de ese eje.
        """
        self._require_ptz()
        velocity: dict[str, Any] = {}
        if pan or tilt:
            velocity["PanTilt"] = {"x": _clamp(pan * speed), "y": _clamp(tilt * speed)}
        if zoom:
            velocity["Zoom"] = {"x": _clamp(zoom * speed)}
        if not velocity:
            self.stop()
            return

        self.stop_inactive_axes(
            pan_tilt="PanTilt" in velocity, zoom="Zoom" in velocity
        )
        try:
            self._ptz.ContinuousMove(
                {"ProfileToken": self.profile_token, "Velocity": velocity}
            )
            log.debug("ContinuousMove enviado: %s", velocity)
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"ContinuousMove falló: {exc}") from exc
        self._moving_pan_tilt = "PanTilt" in velocity
        self._moving_zoom = "Zoom" in velocity

    def stop(self, pan_tilt: bool = True, zoom: bool = True) -> None:
        """Detiene el movimiento de los ejes indicados (Stop)."""
        self._require_ptz()
        if not pan_tilt and not zoom:
            return
        try:
            self._ptz.Stop(
                {
                    "ProfileToken": self.profile_token,
                    "PanTilt": pan_tilt,
                    "Zoom": zoom,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"Stop falló: {exc}") from exc
        if pan_tilt:
            self._moving_pan_tilt = False
        if zoom:
            self._moving_zoom = False

    def stop_inactive_axes(self, pan_tilt: bool, zoom: bool) -> None:
        """Detiene los ejes que estaban en marcha y ya no se envían.

        No se envía nada si no había ningún eje en marcha, de modo que
        puede llamarse en cada repetición sin generar tráfico inútil.
        """
        stop_pan_tilt = self._moving_pan_tilt and not pan_tilt
        stop_zoom = self._moving_zoom and not zoom
        if stop_pan_tilt or stop_zoom:
            self.stop(pan_tilt=stop_pan_tilt, zoom=stop_zoom)

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
        """Desplazamiento relativo (RelativeMove) de los ejes activos.

        Igual que en ``continuous_move``, se omiten los ejes a cero para
        que la cámara no reciba una traslación vacía junto a la útil.
        """
        self._require_ptz()
        translation: dict[str, Any] = {}
        speed: dict[str, Any] = {}
        if pan or tilt:
            translation["PanTilt"] = {"x": _clamp(pan), "y": _clamp(tilt)}
            speed["PanTilt"] = {"x": 1.0, "y": 1.0}
        if zoom:
            translation["Zoom"] = {"x": _clamp(zoom)}
            speed["Zoom"] = {"x": 1.0}
        if not translation:
            return
        try:
            self._ptz.RelativeMove(
                {
                    "ProfileToken": self.profile_token,
                    "Translation": translation,
                    "Speed": speed,
                }
            )
            log.debug("RelativeMove enviado: %s", translation)
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
            self.goto_preset(home_preset.token)
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

    def goto_preset(self, token: str) -> None:
        """Desplaza la cámara al preset con el token ONVIF indicado."""
        self._require_ptz()
        try:
            self._ptz.GotoPreset(
                {"ProfileToken": self.profile_token, "PresetToken": str(token)}
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GotoPreset falló: {exc}") from exc

    def set_preset(self, token: str = "", name: str = "") -> None:
        """Guarda la posición actual como preset (SetPreset).

        Con ``token`` vacío la cámara crea un preset nuevo y elige ella el
        token; con un token existente se sobrescribe ese preset. Si
        ``name`` no está vacío se asigna ese nombre.
        """
        self._require_ptz()
        request: dict[str, Any] = {"ProfileToken": self.profile_token}
        if token:
            request["PresetToken"] = str(token)
        if name:
            request["Name"] = name
        try:
            self._ptz.SetPreset(request)
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"SetPreset falló: {exc}") from exc

    def rename_preset(self, token: str, name: str) -> None:
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
                    "PresetToken": str(token),
                    "Name": name,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"SetPreset (renombrar) falló: {exc}") from exc

    def remove_preset(self, token: str) -> None:
        """Elimina un preset (RemovePreset)."""
        self._require_ptz()
        try:
            self._ptz.RemovePreset(
                {"ProfileToken": self.profile_token, "PresetToken": str(token)}
            )
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"RemovePreset falló: {exc}") from exc

    def get_presets(self) -> list[PresetInfo]:
        """Devuelve la lista de presets (GetPresets) en el orden de la cámara.

        Los tokens se conservan tal cual: ONVIF permite que no sean
        numéricos ('PresetA', UUIDs...) y cualquier conversión perdería
        presets por el camino.
        """
        self._require_ptz()
        try:
            raw_presets = list(self._ptz.GetPresets({"ProfileToken": self.profile_token}))
        except Exception as exc:  # noqa: BLE001
            raise CameraError(f"GetPresets falló: {exc}") from exc
        presets: list[PresetInfo] = []
        for preset in raw_presets:
            token = str(_getattr(preset, "token") or "").strip()
            if not token:
                continue
            name = str(_getattr(preset, "Name") or "").strip() or f"Preset {token}"
            presets.append(PresetInfo(token=token, name=name))
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
