"""Control de la cámara mediante teclado.

Soporta múltiples teclas simultáneas (W+D -> diagonal) y solo publica
comandos cuando la dirección cambia (delegado en ``MovementState``).

Dos implementaciones con la misma lógica:
  * ``PynputKeyboardController``: teclado global (pynput).
  * ``QtKeyboardController``: eventos de la ventana PySide6 (fiable en
    Wayland y Windows sin permisos especiales).

La factoría ``create_keyboard_controller`` elige el backend según la
configuración y, en modo 'auto', cae a Qt si pynput no puede arrancar.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from config.settings import KeyboardConfig
from controllers.base import InputController, MovementState
from core.event_bus import EventBus
from models.commands import GotoPresetCommand, QuitCommand, StopCommand
from utils.logger import get_logger

log = get_logger(__name__)

KEYBOARD_TOPIC = "input.keyboard"


class BackendUnavailable(RuntimeError):
    """El backend de teclado elegido no pudo arrancar."""


class KeyboardController(InputController):
    """Lógica de teclado compartida por ambos backends.

    Las implementaciones concretas convierten sus eventos nativos a
    nombres canónicos (minúsculas: 'w', 'space', 'esc', '1', ...) y llaman
    a :meth:`on_key_down` / :meth:`on_key_up`.
    """

    requires_window_events = False

    def __init__(
        self,
        config: KeyboardConfig,
        movement: MovementState,
        bus: EventBus,
        backend: str = "auto",
    ) -> None:
        self._config = config
        self._movement = movement
        self._bus = bus
        self._backend = backend
        self._pressed: set[str] = set()
        self._active = False
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return "teclado"

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def start(self) -> None:
        self._notify_active()

    def stop(self) -> None:
        with self._lock:
            self._pressed.clear()
            self._active = False
        self._notify_active()

    # -- Entrada canónica -------------------------------------------------

    def on_key_down(self, key_name: str) -> None:
        self._handle_key(key_name, True)

    def on_key_up(self, key_name: str) -> None:
        self._handle_key(key_name, False)

    def _handle_key(self, key_name: str, pressed: bool) -> None:
        if not key_name:
            return
        with self._lock:
            if pressed:
                if key_name in self._pressed:
                    return
                self._pressed.add(key_name)
            else:
                if key_name not in self._pressed:
                    return
                self._pressed.discard(key_name)
            self._active = bool(self._pressed)

        if pressed:
            if self._handle_special_key(key_name) is False:
                return
        self._notify_active()
        self._recompute()

    # -- Lógica de mapeo --------------------------------------------------

    def _handle_special_key(self, key_name: str) -> bool:
        """Procesa teclas de acción y devuelve si se debe recomputar.

        ``False`` indica acción terminal (stop/quit/preset) que además
        limpia las teclas de movimiento para que la cámara no siga en
        movimiento continuo.
        """
        config = self._config
        if key_name == config.stop:
            with self._lock:
                for movement_key in self._movement_keys():
                    self._pressed.discard(movement_key)
            self._bus.send(StopCommand())
            log.debug("Teclado: stop")
            return False
        if key_name == config.quit:
            self._bus.send(QuitCommand())
            log.info("Teclado: solicitud de salida (ESC)")
            return False
        preset_id = config.preset_hotkeys.get(key_name)
        if preset_id is not None:
            with self._lock:
                for movement_key in self._movement_keys():
                    self._pressed.discard(movement_key)
            self._bus.send(GotoPresetCommand(preset_id))
            log.info("Teclado: GotoPreset %s (tecla %s)", preset_id, key_name)
            return False
        return True

    def _movement_keys(self) -> tuple[str, ...]:
        config = self._config
        return (
            config.up,
            config.down,
            config.left,
            config.right,
            config.zoom_in,
            config.zoom_out,
        )

    def _recompute(self) -> None:
        config = self._config
        with self._lock:
            pressed = set(self._pressed)
        pan = (1.0 if config.right in pressed else 0.0) - (
            1.0 if config.left in pressed else 0.0
        )
        tilt = (1.0 if config.up in pressed else 0.0) - (
            1.0 if config.down in pressed else 0.0
        )
        zoom = (1.0 if config.zoom_in in pressed else 0.0) - (
            1.0 if config.zoom_out in pressed else 0.0
        )
        self._movement.update(pan, tilt, zoom)

    def _notify_active(self) -> None:
        self._bus.publish(
            KEYBOARD_TOPIC,
            {"active": self.is_active, "backend": self._backend},
        )


class PynputKeyboardController(KeyboardController):
    """Teclado global mediante pynput (requiere X11 o permisos 'input')."""

    def __init__(
        self,
        config: KeyboardConfig,
        movement: MovementState,
        bus: EventBus,
        start_timeout: float = 1.0,
    ) -> None:
        super().__init__(config, movement, bus, backend="pynput")
        self._start_timeout = start_timeout
        self._listener: Any = None
    def start(self) -> None:
        from pynput.keyboard import Listener

        listener = Listener(
            on_press=lambda key: self.on_key_down(pynput_key_name(key)),
            on_release=lambda key: self.on_key_up(pynput_key_name(key)),
        )
        try:
            listener.start()
        except Exception as exc:  # noqa: BLE001 - fallos variados de X11/evdev
            raise BackendUnavailable(f"pynput no arrancó: {exc}") from exc

        time.sleep(min(0.2, self._start_timeout))
        if not listener.is_alive():
            raise BackendUnavailable(
                "pynput no pudo iniciar el listener global (¿Wayland sin X11?)"
            )
        self._listener = listener
        super().start()
        log.info("Teclado global activo (pynput)")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        super().stop()


class QtKeyboardController(KeyboardController):
    """Teclado capturado por la ventana PySide6 (fiable y sin permisos)."""

    requires_window_events = True

    def __init__(
        self,
        config: KeyboardConfig,
        movement: MovementState,
        bus: EventBus,
    ) -> None:
        super().__init__(config, movement, bus, backend="qt")

    def start(self) -> None:
        super().start()
        log.info("Teclado por ventana activo (qt)")


def pynput_key_name(key: Any) -> str:
    """Convierte una tecla pynput a nombre canónico ('w', 'esc', ...)."""
    try:
        from pynput.keyboard import Key, KeyCode
    except ImportError:
        return str(key).lower()
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.lower()
        return f"<{key.vk}>"
    if isinstance(key, Key):
        return key.name.lower()
    return str(key).lower()


def qt_key_name(event: Any) -> str:
    """Convierte un QKeyEvent a nombre canónico ('w', 'esc', 'space', ...)."""
    text = event.text()
    if text:
        if text == " ":
            return "space"
        if text.isprintable() and text.strip():
            return text.lower()
    from PySide6.QtCore import Qt

    key = event.key()
    mapping = {
        Qt.Key_Escape: "esc",
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
    }
    return mapping.get(key, "")


def _is_wayland_session() -> bool:
    """Detecta sesión Wayland (donde pynput no captura eventos de Qt)."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def create_keyboard_controller(
    config: KeyboardConfig,
    movement: MovementState,
    bus: EventBus,
) -> KeyboardController:
    """Crea y arranca el controlador de teclado según la configuración.

    En modo 'auto' intenta pynput (teclado global) y, si no puede
    arrancar, devuelve la implementación Qt (eventos de la ventana). En
    sesiones Wayland se usa directamente Qt: pynput depende de X11 y bajo
    Wayland su listener arranca pero no recibe las teclas de las ventanas
    Qt nativas.
    """
    backend = config.backend
    if backend == "pynput":
        controller = PynputKeyboardController(config, movement, bus)
        controller.start()
        return controller
    if backend == "qt":
        return QtKeyboardController(config, movement, bus)

    # auto: probar pynput y caer a Qt
    if _is_wayland_session():
        log.warning("Sesión Wayland detectada: usando teclado de ventana Qt")
        return QtKeyboardController(config, movement, bus)
    try:
        controller = PynputKeyboardController(config, movement, bus)
        controller.start()
        return controller
    except BackendUnavailable as exc:
        log.warning("pynput no disponible, usando teclado de ventana Qt: %s", exc)
        return QtKeyboardController(config, movement, bus)
