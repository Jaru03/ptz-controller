"""Carga y persistencia de la configuración en YAML.

Toda la configuración de la aplicación vive en un archivo YAML. Este
módulo define las dataclasses tipadas que la representan, aplica valores
por defecto (nada hardcodeado fuera de aquí) y hace un *deep merge* sobre
los defaults para que añadir claves nuevas no rompa configuraciones
existentes.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Mapping, TypeVar, Union

import yaml

DEFAULT_CONFIG_FILENAME = "config.yaml"

T = TypeVar("T")


@dataclass
class CameraConfig:
    """Parámetros de conexión con la cámara ONVIF."""

    ip: str = "192.168.1.100"
    port: int = 80
    username: str = "admin"
    password: str = ""
    rtsp_url: str = ""
    mock: bool = True


@dataclass
class MovementConfig:
    """Comportamiento del movimiento PTZ.

    ``zoom_mode`` decide cómo se traduce el eje de zoom a ONVIF:
      - 'continuous': ``ContinuousMove`` + ``Stop`` (como el pan/tilt). Es
        el modo por defecto: lo soportan prácticamente todas las cámaras.
      - 'step': cada repetición envía un ``RelativeMove`` de ``zoom_step``,
        de modo que el zoom avanza a saltos y se puede parar en puntos
        intermedios. Algunas cámaras aceptan el ``RelativeMove`` de zoom
        sin dar error pero sin moverlo realmente; si el zoom deja de
        responder con este modo, vuelva a 'continuous'.
      - 'auto': intenta 'step' y cae a 'continuous' solo si la cámara
        rechaza el ``RelativeMove`` con un error (no detecta el caso
        anterior, en el que la cámara lo acepta pero no mueve el zoom).
    """

    speed: float = 0.5
    speeds: list[float] = field(default_factory=lambda: [0.2, 0.5, 0.8])
    deadzone: float = 0.08
    repeat_interval_ms: int = 150
    zoom_mode: str = "continuous"
    zoom_step: float = 0.06


@dataclass
class KeyboardConfig:
    """Mapeo de teclas (nombres en minúsculas: 'w', 'space', 'esc', ...).

    ``backend`` acepta:
      - 'auto': intenta pynput (teclado global) y cae a 'window' si no
        arranca.
      - 'pynput': teclado global (requiere X11 o permisos del grupo input).
      - 'window': eventos de teclado de la propia ventana (fiable en
        Wayland y Windows sin permisos especiales). Antes se llamaba
        'qt'; un ``config.yaml`` con ese valor se sigue aceptando y se
        normaliza a 'window' en cuanto se carga.

    Presets: ``preset_keys`` asigna teclas **por posición** a los presets
    que devuelve la cámara (la 1ª tecla va al 1er preset, etc.), de modo
    que funcionan sea cual sea su token ONVIF. ``preset_hotkeys`` permite
    fijar una tecla a un token concreto ('f1': 'PresetA') y tiene
    prioridad. Las teclas del pad numérico se nombran 'kp_1'...'kp_0' y,
    si no están mapeadas, caen a su dígito equivalente.
    """

    backend: str = "auto"
    up: str = "w"
    down: str = "s"
    left: str = "a"
    right: str = "d"
    zoom_in: str = "e"
    zoom_out: str = "q"
    preset_keys: list[str] = field(
        default_factory=lambda: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
    )
    preset_hotkeys: dict[str, str] = field(default_factory=dict)
    stop: str = "space"
    quit: str = "esc"

    def __post_init__(self) -> None:
        """Normaliza los mapeos de presets cargados del YAML.

        Los tokens ONVIF son cadenas; una configuración antigua podía
        guardarlos como enteros ({'1': 1}), así que se convierten aquí.
        También se renombra aquí el backend 'qt' (nombre anterior de
        'window', desde la migración a pywebview) para que un
        ``config.yaml`` ya existente no falle la validación tras
        actualizar.
        """
        if self.backend == "qt":
            self.backend = "window"
        self.preset_keys = [str(key).lower() for key in self.preset_keys]
        self.preset_hotkeys = {
            str(key).lower(): str(token)
            for key, token in dict(self.preset_hotkeys).items()
        }


@dataclass
class JoystickConfig:
    """Mapeo de ejes y botones del mando (por defecto para mandos genéricos).

    ``device_overrides`` permite redefinir estos valores por mando usando
    como clave un fragmento del GUID o del nombre devuelto por SDL, p. ej.:
        device_overrides:
            "DualShock 4":
                home_button: 16
    """

    poll_rate: int = 30
    deadzone: float = 0.08
    pan_axis: int = 0
    tilt_axis: int = 1
    invert_tilt: bool = True
    zoom_out_axis: int = 4
    zoom_in_axis: int = 5
    speed_down_button: int = 5
    speed_up_button: int = 4
    home_button: int = 12
    preset_buttons: list[int] = field(default_factory=lambda: [0, 1, 2, 3])
    device_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class GuiConfig:
    """Parámetros de la interfaz gráfica."""

    poll_interval_ms: int = 33
    video_fps: int = 15
    rtsp_transport: str = "tcp"


@dataclass
class LoggingConfig:
    """Configuración del sistema de logs."""

    level: str = "INFO"
    directory: str = "logs"


@dataclass
class Settings:
    """Configuración completa de la aplicación."""

    camera: CameraConfig = field(default_factory=CameraConfig)
    movement: MovementConfig = field(default_factory=MovementConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)
    joystick: JoystickConfig = field(default_factory=JoystickConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # -- Serialización ---------------------------------------------------

    @classmethod
    def defaults(cls) -> "Settings":
        return cls()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Settings":
        """Construye Settings desde un diccionario (merge sobre defaults)."""
        merged = _deep_merge(asdict(cls.defaults()), dict(data))
        return cls(
            camera=_build(CameraConfig, merged.get("camera", {})),
            movement=_build(MovementConfig, merged.get("movement", {})),
            keyboard=_build(KeyboardConfig, merged.get("keyboard", {})),
            joystick=_build(JoystickConfig, merged.get("joystick", {})),
            gui=_build(GuiConfig, merged.get("gui", {})),
            logging=_build(LoggingConfig, merged.get("logging", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # -- Fichero ----------------------------------------------------------

    @classmethod
    def load(cls, path: Union[str, os.PathLike[str]]) -> "Settings":
        """Carga un YAML y lo fusiona con los valores por defecto.

        Si el archivo no existe o está vacío se devuelven los defaults
        (sin escribir nada).
        """
        path = Path(path)
        if path.is_file():
            with path.open("r", encoding="utf-8") as stream:
                data = yaml.safe_load(stream) or {}
            return cls.from_dict(data)
        return cls.defaults()

    def save(self, path: Union[str, os.PathLike[str]]) -> None:
        """Escribe la configuración actual en formato YAML legible."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(
                self.to_dict(),
                stream,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )

    @classmethod
    def ensure_default_config(cls, path: Union[str, os.PathLike[str]]) -> "Settings":
        """Devuelve la config cargada y crea el YAML por defecto si falta."""
        path = Path(path)
        settings = cls.load(path)
        if not path.is_file():
            settings.save(path)
        return settings

    def validate(self) -> list[str]:
        """Devuelve una lista de avisos/errores de validación (vacía si ok)."""
        warnings: list[str] = []
        movement = self.movement
        if not (0.0 <= movement.deadzone < 1.0):
            warnings.append("movement.deadzone debe estar entre 0 y 1")
        if not (0.0 <= movement.speed <= 1.0):
            warnings.append("movement.speed debe estar entre 0 y 1")
        if movement.zoom_mode not in ("auto", "step", "continuous"):
            warnings.append(
                f"movement.zoom_mode '{movement.zoom_mode}' no es válido"
            )
        if not (0.0 < movement.zoom_step <= 1.0):
            warnings.append("movement.zoom_step debe estar entre 0 y 1")
        if self.keyboard.backend not in ("auto", "pynput", "window"):
            warnings.append(
                f"keyboard.backend '{self.keyboard.backend}' no es válido"
            )
        if self.camera.port < 0 or self.camera.port > 65535:
            warnings.append("camera.port debe estar entre 0 y 65535")
        return warnings


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusiona ``override`` sobre ``base`` recursivamente."""
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(result[key], dict(value))
        else:
            result[key] = value
    return result


def _build(dataclass_type: type[T], data: Mapping[str, Any]) -> T:
    """Construye una dataclass desde un mapping filtrando claves extrañas."""
    fields = {f.name for f in dataclass_type.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in data.items() if k in fields}
    return dataclass_type(**kwargs)
