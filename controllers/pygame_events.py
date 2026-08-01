"""Bucle de eventos SDL compartido (pygame) para el controlador de joystick.

Inicializa pygame con el driver de video dummy (sin ventana adicional) y
pump de eventos en un hilo propio. Otros componentes pueden suscribirse a
tipos de evento concretos (ejes, botones, hotplug) sin conocer los
entresijos de SDL.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from typing import Any, Callable

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame

EventHandler = Callable[[Any], None]


class PyGameEventBroker:
    """Broker de eventos pygame que expone joysticks y distribuye eventos.

    Compatible con Linux y Windows. Cualquier mando SDL (DualShock 4/5,
    Xbox, genéricos USB) se detecta automáticamente y se gestiona el
    hotplug.
    """

    def __init__(self, poll_rate: int = 30) -> None:
        self._poll_interval = 1.0 / max(1, poll_rate)
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._handlers: dict[int, list[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._by_instance: dict[int, pygame.joystick.Joystick] = {}

    # -- Ciclo de vida ----------------------------------------------------

    def start(self) -> None:
        """Inicializa pygame y arranca el hilo de eventos."""
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        if not pygame.get_init():
            pygame.init()
        pygame.joystick.init()
        self._refresh_devices()
        self._running.set()
        self._thread = threading.Thread(
            target=self._run,
            name="pygame-events",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo de eventos y libera pygame."""
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._handlers.clear()
            self._by_instance.clear()
        if pygame.get_init():
            pygame.quit()

    # -- Suscripción ------------------------------------------------------

    def subscribe(self, event_type: int, handler: EventHandler) -> None:
        """Registra un handler para un tipo de evento pygame."""
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: int, handler: EventHandler) -> None:
        """Elimina un handler previamente registrado."""
        with self._lock:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    # -- Acceso a joysticks ----------------------------------------------

    @property
    def instance_ids(self) -> list[int]:
        with self._lock:
            return list(self._by_instance)

    def joystick_by_instance(self, instance_id: int) -> pygame.joystick.Joystick | None:
        with self._lock:
            return self._by_instance.get(instance_id)

    # -- Internos ---------------------------------------------------------

    def _run(self) -> None:
        while self._running.is_set():
            for event in pygame.event.get():
                self._dispatch(event)
            self._refresh_devices()
            time.sleep(self._poll_interval)

    def _dispatch(self, event: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event.type, ()))
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - un handler no debe romper el bucle
                import logging

                logging.getLogger("ptz_controller.controllers.pygame_events").exception(
                    "Error en handler de evento pygame %s", event.type
                )

    def _refresh_devices(self) -> None:
        try:
            active: set[int] = set()
            for index in range(pygame.joystick.get_count()):
                joystick = pygame.joystick.Joystick(index)
                joystick.init()
                active.add(joystick.get_instance_id())
                with self._lock:
                    self._by_instance.setdefault(joystick.get_instance_id(), joystick)
            with self._lock:
                for instance_id in list(self._by_instance):
                    if instance_id not in active:
                        self._by_instance.pop(instance_id, None)
        except pygame.error:
            pass
