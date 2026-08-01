"""Controladores de entrada: teclado y joystick."""

import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from controllers.base import InputController, MovementState
from controllers.joystick_controller import JoystickController
from controllers.keyboard_controller import (
    BackendUnavailable,
    KeyboardController,
    PynputKeyboardController,
    QtKeyboardController,
    create_keyboard_controller,
    pynput_key_name,
    qt_key_name,
)
from controllers.pygame_events import PyGameEventBroker

__all__ = [
    "BackendUnavailable",
    "InputController",
    "JoystickController",
    "KeyboardController",
    "MovementState",
    "PyGameEventBroker",
    "PynputKeyboardController",
    "QtKeyboardController",
    "create_keyboard_controller",
    "pynput_key_name",
    "qt_key_name",
]
