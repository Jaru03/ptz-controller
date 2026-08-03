"""Modelos de dominio: comandos, estado PTZ y tipos compartidos.

Este paquete define el "lenguaje" que los controladores de entrada
(teclado/joystick) publican en el bus de eventos y que la capa de control
PTZ interpreta. Mantener estos tipos desacoplados de ONVIF y de PySide6
permite sustituir la implementación real por el mock sin tocar la GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "Command",
    "MoveCommand",
    "StopCommand",
    "SetSpeedCommand",
    "GotoPresetCommand",
    "SetPresetCommand",
    "RenamePresetCommand",
    "RemovePresetCommand",
    "HomeCommand",
    "ConnectCommand",
    "DisconnectCommand",
    "QuitCommand",
    "PTZStatus",
    "PresetInfo",
    "Vector2",
    "SpeedLevel",
]


class SpeedLevel(Enum):
    """Niveles de velocidad predefinidos seleccionables desde el teclado."""

    SLOW = 1
    MEDIUM = 2
    FAST = 3


@dataclass(frozen=True)
class Vector2:
    """Vector bidimensional normalizado (valores en el rango -1.0..1.0)."""

    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(max(-1.0, min(1.0, self.x))))
        object.__setattr__(self, "y", float(max(-1.0, min(1.0, self.y))))

    @property
    def is_zero(self) -> bool:
        return self.x == 0.0 and self.y == 0.0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vector2):
            return NotImplemented
        return abs(self.x - other.x) < 1e-9 and abs(self.y - other.y) < 1e-9


@dataclass(frozen=True)
class Command:
    """Base inmutable de todos los comandos que circulan por el bus."""


@dataclass(frozen=True)
class MoveCommand(Command):
    """Orden de movimiento continuo con vectores normalizados -1..1.

    ``pan``/``tilt``/``zoom`` indican dirección e intensidad; ``speed``
    es el factor global de velocidad (0..1).
    """

    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0
    speed: float = 0.5

    @property
    def is_neutral(self) -> bool:
        return (
            abs(self.pan) < 1e-9
            and abs(self.tilt) < 1e-9
            and abs(self.zoom) < 1e-9
        )


@dataclass(frozen=True)
class StopCommand(Command):
    """Detiene cualquier movimiento en curso."""


@dataclass(frozen=True)
class SetSpeedCommand(Command):
    """Cambia la velocidad global de movimiento (0..1)."""

    speed: float = 0.5


@dataclass(frozen=True)
class GotoPresetCommand(Command):
    """Ordena desplazarse a un preset guardado (token ONVIF)."""

    token: str = ""


@dataclass(frozen=True)
class SetPresetCommand(Command):
    """Guarda la posición actual como preset con un nombre opcional."""

    token: str = ""
    name: str = ""


@dataclass(frozen=True)
class RenamePresetCommand(Command):
    """Cambia el nombre de un preset existente."""

    token: str = ""
    name: str = ""


@dataclass(frozen=True)
class RemovePresetCommand(Command):
    """Elimina un preset."""

    token: str = ""


@dataclass(frozen=True)
class HomeCommand(Command):
    """Vuelve a la posición de inicio (home)."""


@dataclass(frozen=True)
class ConnectCommand(Command):
    """Solicita conectar con la cámara."""


@dataclass(frozen=True)
class DisconnectCommand(Command):
    """Solicita desconectar la cámara."""


@dataclass(frozen=True)
class QuitCommand(Command):
    """Solicita el cierre ordenado de la aplicación."""


@dataclass(frozen=True)
class PresetInfo:
    """Información de un preset de posición.

    ``token`` es el identificador real del preset en la cámara y es
    opaco a propósito: ONVIF permite tokens no numéricos ('PresetA',
    UUIDs...), así que ninguna capa debe asumir que es un número.
    """

    token: str
    name: str = ""


@dataclass(frozen=True)
class PTZStatus:
    """Instantánea del estado de la cámara (independiente del protocolo)."""

    connected: bool = False
    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0
    speed: float = 0.5
    device_name: str = ""
    ip: str = ""
    input_active: str = ""
    presets: tuple[PresetInfo, ...] = field(default_factory=tuple)
