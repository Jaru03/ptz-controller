"""Bus de eventos (pub/sub) que desacopla entrada, control PTZ y GUI.

Principio utilizado: los componentes no se conocen entre sí; solo conocen
los *topics* del bus. El publicador publica un payload y cualquier
suscriptor registrado lo recibe, sin que exista referencia directa entre
ambos (mediador).
"""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable

from models.commands import Command

Handler = Callable[[Any], None]


class EventBus:
    """Bus de eventos seguro para hilos.

    Los handlers se invocan de forma síncrona en el hilo del publicador,
    por lo que la GUI debe encolar las actualizaciones de interfaz hacia su
    propio hilo (ver ``gui.main_window.QtEventBridge``).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> None:
        """Registra un handler para un topic concreto."""
        if not callable(handler):
            raise TypeError("El handler debe ser invocable")
        with self._lock:
            if handler not in self._handlers[topic]:
                self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        """Elimina un handler previamente registrado."""
        with self._lock:
            try:
                self._handlers[topic].remove(handler)
            except ValueError:
                pass

    def publish(self, topic: str, payload: Any = None) -> None:
        """Distribuye un payload a todos los handlers del topic."""
        with self._lock:
            handlers = list(self._handlers.get(topic, ()))
        for handler in handlers:
            handler(payload)

    def send(self, command: Command) -> None:
        """Publica un comando en su topic por tipo (conveniencia)."""
        self.publish(_command_topic(command), command)

    def clear(self) -> None:
        """Elimina todos los suscriptores."""
        with self._lock:
            self._handlers.clear()

    def has_subscribers(self, topic: str) -> bool:
        with self._lock:
            return bool(self._handlers.get(topic))


def _command_topic(command: Command) -> str:
    """Deriva el topic de un comando a partir de su nombre de clase."""
    name = type(command).__name__
    if name.endswith("Command"):
        name = name[: -len("Command")]
    return f"command.{name[0].lower()}{name[1:]}"
