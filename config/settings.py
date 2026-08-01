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
    """Comportamiento del movimiento PTZ."""

    speed: float = 0.5
    speeds: list[float] = field(default_factory=lambda: [0.2, 0.5, 0.8])
    deadzone: float = 0.08


@dataclass
class KeyboardConfig:
    """Mapeo de teclas (nombres en minúsculas: 'w', 'space', 'esc', ...).

    ``backend`` acepta:
      - 'auto': intenta pynput (teclado global) y cae a 'qt' si no arranca.
      - 'pynput': teclado global (requiere X11 o permisos del grupo input).
      - 'qt': eventos de teclado de la propia ventana PySide6 (fiable en
        Wayland y Windows).
    """

    backend: str = "auto"
    up: str = "w"
    down: str = "s"
    left: str = "a"
    right: str = "d"
    zoom_in: str = "e"
    zoom_out: str = "q"
    preset_hotkeys: dict[str, int] = field(
        default_factory=lambda: {"1": 1, "2": 2, "3": 3}
    )
    stop: str = "space"
    quit: str = "esc"


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
        if self.keyboard.backend not in ("auto", "pynput", "qt"):
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
