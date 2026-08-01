"""Base común de los controladores de entrada.

Contiene el estado de movimiento compartido por teclado y joystick
(``MovementState``) que implementa la zona muerta (deadzone) y, sobre
todo, la regla de "solo enviar comandos cuando la dirección cambia"
para no saturar la cámara con órdenes redundantes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from models.commands import Command, MoveCommand, StopCommand

EPS = 1e-6


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _rescale(value: float, deadzone: float) -> float:
    """Aplica deadzone y re-escala el valor a la salida proporcional.

    Un valor dentro de la zona muerta produce 0; a partir del borde crece
    de forma lineal hasta 1.0 (20% de stick -> 20% de velocidad).
    """
    if deadzone <= 0.0:
        return float(value)
    if abs(value) <= deadzone:
        return 0.0
    scaled = (abs(value) - deadzone) / (1.0 - deadzone)
    return (1.0 if value > 0 else -1.0) * min(1.0, scaled)


class MovementState:
    """Normaliza la entrada bruta y solo publica cambios de dirección.

    Se usa igual desde el teclado (valores 0/±1) y desde el joystick
    (valores proporcionales), de modo que la lógica de "no enviar
    comandos innecesarios" vive en un único sitio (DRY).
    """

    def __init__(
        self,
        deadzone: float,
        publish: Callable[[Command], None],
        initial_speed: float = 0.5,
    ) -> None:
        self._deadzone = max(0.0, min(0.5, float(deadzone)))
        self._publish = publish
        self._speed = _clamp01(initial_speed)
        self._raw = (0.0, 0.0, 0.0)
        self._last: MoveCommand | None = None

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        """Cambia la velocidad global y reemite si el movimiento sigue activo."""
        new_speed = _clamp01(speed)
        if abs(new_speed - self._speed) < EPS:
            return
        self._speed = new_speed
        self._recompute()

    def update(self, pan: float, tilt: float, zoom: float) -> None:
        """Recibe el vector bruto de entrada y publica si cambió algo."""
        self._raw = (pan, tilt, zoom)
        self._recompute()

    def _recompute(self) -> None:
        pan = _rescale(self._raw[0], self._deadzone)
        tilt = _rescale(self._raw[1], self._deadzone)
        zoom = _rescale(self._raw[2], self._deadzone)

        if abs(pan) < EPS and abs(tilt) < EPS and abs(zoom) < EPS:
            if self._last is not None:
                self._publish(StopCommand())
                self._last = None
            return

        command = MoveCommand(pan=pan, tilt=tilt, zoom=zoom, speed=self._speed)
        if self._last is None or self._different(self._last, command):
            self._publish(command)
            self._last = command

    @staticmethod
    def _different(first: MoveCommand, second: MoveCommand) -> bool:
        return any(
            abs(a - b) > EPS
            for a, b in (
                (first.pan, second.pan),
                (first.tilt, second.tilt),
                (first.zoom, second.zoom),
                (first.speed, second.speed),
            )
        )


class InputController(ABC):
    """Contrato de un controlador de entrada (teclado o mando)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre legible del controlador ('teclado', 'joystick')."""

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Indica si el usuario está usando este controlador ahora."""

    @abstractmethod
    def start(self) -> None:
        """Arranca la captura de entrada."""

    @abstractmethod
    def stop(self) -> None:
        """Detiene la captura de entrada."""
