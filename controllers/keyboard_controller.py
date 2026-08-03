"""Control de la cámara mediante teclado.

Soporta múltiples teclas simultáneas (W+D -> diagonal) y solo publica
comandos cuando la dirección cambia (delegado en ``MovementState``).

Dos implementaciones con la misma lógica:
  * ``PynputKeyboardController``: teclado global (pynput).
  * ``QtKeyboardController``: eventos de la ventana PySide6 (fiable en
    Wayland y Windows sin permisos especiales).

La factoría ``create_keyboard_controller`` elige el backend según la
configuración y, en modo 'auto', cae a Qt si pynput no puede arrancar.

Nombres canónicos de tecla: minúsculas ('w', 'space', 'esc', '1'), teclas
de función ('f1'...'f12') y pad numérico ('kp_0'...'kp_9', 'kp_enter',
'kp_plus'...). El pad numérico se distingue del teclado principal para
poder asignarle atajos propios, pero si no tiene ninguno asignado cae a
su dígito equivalente.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from config.settings import KeyboardConfig
from controllers.base import InputController, MovementState, PresetRegistry
from core.event_bus import EventBus
from models.commands import GotoPresetCommand, QuitCommand, StopCommand
from utils.logger import get_logger

log = get_logger(__name__)

KEYBOARD_TOPIC = "input.keyboard"

_KEYPAD_PREFIX = "kp_"


def key_aliases(key_name: str) -> tuple[str, ...]:
    """Nombres bajo los que buscar una tecla en la configuración.

    Una tecla del pad numérico se busca primero por su nombre propio
    ('kp_1') y después por su dígito ('1'), de modo que el pad funciona
    con la configuración por defecto sin duplicar entradas.
    """
    if key_name.startswith(_KEYPAD_PREFIX):
        suffix = key_name[len(_KEYPAD_PREFIX):]
        if suffix.isdigit():
            return (key_name, suffix)
    return (key_name,)


def hotkey_for_preset(
    config: KeyboardConfig, index: int, token: str
) -> str:
    """Tecla asignada al preset en la posición ``index`` (o cadena vacía).

    Tiene prioridad un atajo explícito al token; si no lo hay, se usa la
    asignación posicional de ``preset_keys``.
    """
    for key, mapped in config.preset_hotkeys.items():
        if mapped == token:
            return key
    if 0 <= index < len(config.preset_keys):
        return config.preset_keys[index]
    return ""


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
        presets: PresetRegistry | None = None,
    ) -> None:
        self._config = config
        self._movement = movement
        self._bus = bus
        self._backend = backend
        self._presets = presets if presets is not None else PresetRegistry(bus)
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
        if self._is_preset_key(key_name):
            token = self._preset_token_for_key(key_name)
            if token is None:
                log.info("Teclado: la tecla %s no tiene ningún preset", key_name)
                return False
            with self._lock:
                for movement_key in self._movement_keys():
                    self._pressed.discard(movement_key)
            self._bus.send(GotoPresetCommand(token))
            log.info("Teclado: GotoPreset %s (tecla %s)", token, key_name)
            return False
        return True

    def _is_preset_key(self, key_name: str) -> bool:
        """Indica si la tecla está reservada para presets."""
        config = self._config
        return any(
            alias in config.preset_hotkeys or alias in config.preset_keys
            for alias in key_aliases(key_name)
        )

    def _preset_token_for_key(self, key_name: str) -> str | None:
        """Traduce una tecla al token ONVIF del preset correspondiente.

        Un atajo explícito ``preset_hotkeys`` gana; si no, la tecla se
        resuelve por su posición en ``preset_keys`` contra la lista de
        presets que la cámara haya publicado.
        """
        config = self._config
        aliases = key_aliases(key_name)
        for alias in aliases:
            token = config.preset_hotkeys.get(alias)
            if token:
                return token
        for alias in aliases:
            if alias in config.preset_keys:
                return self._presets.token_at(config.preset_keys.index(alias))
        return None

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
        presets: PresetRegistry | None = None,
    ) -> None:
        super().__init__(config, movement, bus, backend="pynput", presets=presets)
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
        presets: PresetRegistry | None = None,
    ) -> None:
        super().__init__(config, movement, bus, backend="qt", presets=presets)

    def start(self) -> None:
        super().start()
        log.info("Teclado por ventana activo (qt)")


_PYNPUT_KEYPAD_VK = {
    # Keysyms X11 del pad numérico con Bloq Num activado (KP_0..KP_9).
    **{0xFFB0 + digit: f"kp_{digit}" for digit in range(10)},
    0xFF9C: "kp_1",  # KP_End
    0xFF99: "kp_2",  # KP_Down
    0xFF9B: "kp_3",  # KP_Next
    0xFF96: "kp_4",  # KP_Left
    0xFF9D: "kp_5",  # KP_Begin
    0xFF98: "kp_6",  # KP_Right
    0xFF95: "kp_7",  # KP_Home
    0xFF97: "kp_8",  # KP_Up
    0xFF9A: "kp_9",  # KP_Prior
    0xFF9E: "kp_0",  # KP_Insert
    0xFF8D: "kp_enter",
    0xFFAB: "kp_plus",
    0xFFAD: "kp_minus",
    0xFFAA: "kp_multiply",
    0xFFAF: "kp_divide",
}


def pynput_key_name(key: Any) -> str:
    """Convierte una tecla pynput a nombre canónico ('w', 'esc', 'kp_1')."""
    try:
        from pynput.keyboard import Key, KeyCode
    except ImportError:
        return str(key).lower()
    if isinstance(key, KeyCode):
        keypad = _PYNPUT_KEYPAD_VK.get(key.vk)
        if keypad is not None:
            return keypad
        if key.char:
            return key.char.lower()
        return f"<{key.vk}>"
    if isinstance(key, Key):
        return key.name.lower()
    return str(key).lower()


def _qt_keypad_name(key: int) -> str:
    """Nombre canónico de una tecla del pad numérico (Qt)."""
    from PySide6.QtCore import Qt

    if Qt.Key_0 <= key <= Qt.Key_9:
        return f"kp_{key - int(Qt.Key_0)}"
    # Con Bloq Num desactivado el pad emite las teclas de navegación.
    navigation = {
        Qt.Key_Insert: "kp_0",
        Qt.Key_End: "kp_1",
        Qt.Key_Down: "kp_2",
        Qt.Key_PageDown: "kp_3",
        Qt.Key_Left: "kp_4",
        Qt.Key_Clear: "kp_5",
        Qt.Key_Right: "kp_6",
        Qt.Key_Home: "kp_7",
        Qt.Key_Up: "kp_8",
        Qt.Key_PageUp: "kp_9",
        Qt.Key_Delete: "kp_decimal",
        Qt.Key_Enter: "kp_enter",
        Qt.Key_Return: "kp_enter",
        Qt.Key_Plus: "kp_plus",
        Qt.Key_Minus: "kp_minus",
        Qt.Key_Asterisk: "kp_multiply",
        Qt.Key_Slash: "kp_divide",
        Qt.Key_Period: "kp_decimal",
        Qt.Key_Comma: "kp_decimal",
    }
    return navigation.get(key, "")


def _qt_is_keypad(event: Any) -> bool:
    """Indica si el evento viene del pad numérico."""
    from PySide6.QtCore import Qt

    modifiers = getattr(event, "modifiers", None)
    if modifiers is None:
        return False
    try:
        return bool(modifiers() & Qt.KeyboardModifier.KeypadModifier)
    except TypeError:  # pragma: no cover - eventos simulados en tests
        return False


def qt_key_name(event: Any) -> str:
    """Convierte un QKeyEvent a nombre canónico ('w', 'esc', 'kp_1', 'f1').

    El pad numérico se identifica por ``KeypadModifier`` y **antes** de
    mirar el texto: con Bloq Num activado escribe los mismos caracteres
    que la fila de dígitos y, sin él, no escribe nada.
    """
    from PySide6.QtCore import Qt

    key = event.key()
    if _qt_is_keypad(event):
        return _qt_keypad_name(key)

    text = event.text()
    if text:
        if text == " ":
            return "space"
        if text.isprintable() and text.strip():
            return text.lower()

    if Qt.Key_F1 <= key <= Qt.Key_F12:
        return f"f{key - int(Qt.Key_F1) + 1}"
    mapping = {
        Qt.Key_Escape: "esc",
        Qt.Key_Space: "space",
        Qt.Key_Up: "up",
        Qt.Key_Down: "down",
        Qt.Key_Left: "left",
        Qt.Key_Right: "right",
        Qt.Key_Home: "home",
        Qt.Key_End: "end",
        Qt.Key_PageUp: "pageup",
        Qt.Key_PageDown: "pagedown",
        Qt.Key_Insert: "insert",
        Qt.Key_Delete: "delete",
        Qt.Key_Tab: "tab",
        Qt.Key_Backspace: "backspace",
        Qt.Key_Return: "enter",
        Qt.Key_Enter: "enter",
    }
    return mapping.get(key, "")


def _is_wayland_session() -> bool:
    """Detecta sesión Wayland (donde pynput no captura eventos de Qt)."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def create_keyboard_controller(
    config: KeyboardConfig,
    movement: MovementState,
    bus: EventBus,
    presets: PresetRegistry | None = None,
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
        controller = PynputKeyboardController(config, movement, bus, presets=presets)
        controller.start()
        return controller
    if backend == "qt":
        return QtKeyboardController(config, movement, bus, presets=presets)

    # auto: probar pynput y caer a Qt
    if _is_wayland_session():
        log.warning("Sesión Wayland detectada: usando teclado de ventana Qt")
        return QtKeyboardController(config, movement, bus, presets=presets)
    try:
        controller = PynputKeyboardController(config, movement, bus, presets=presets)
        controller.start()
        return controller
    except BackendUnavailable as exc:
        log.warning("pynput no disponible, usando teclado de ventana Qt: %s", exc)
        return QtKeyboardController(config, movement, bus, presets=presets)
