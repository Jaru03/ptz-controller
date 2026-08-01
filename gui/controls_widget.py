"""Widget de referencia rápida de los controles de teclado y mando.

Muestra en una pestaña las teclas y botones/ejes configurados en
``config.yaml`` (secciones ``keyboard`` y ``joystick``). Es una vista de
solo lectura: para cambiar los controles se edita el YAML o se usan los
``device_overrides`` del joystick.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from config.settings import KeyboardConfig, JoystickConfig

_STYLE_INFO = (
    "background-color: #1e1e2e; color: #a6adc8; padding: 6px;"
    "border: 1px solid #313244; border-radius: 4px;"
)


def _key_label(name: str) -> str:
    """Convierte un nombre canónico de tecla a una etiqueta legible."""
    aliases = {
        "esc": "ESC",
        "space": "Espacio",
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
        "shift": "Shift",
        "ctrl": "Ctrl",
        "alt": "Alt",
    }
    if name in aliases:
        return aliases[name]
    return name.upper()


class ControlsWidget(QWidget):
    """Pestaña con el resumen de controles de teclado y mando."""

    def __init__(
        self,
        keyboard: KeyboardConfig,
        joystick: JoystickConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._keyboard = keyboard
        self._joystick = joystick

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        layout.addWidget(self._build_keyboard_group())
        layout.addWidget(self._build_joystick_group())

        note = QLabel(
            "Los controles pueden personalizarse en config.yaml "
            "(secciones keyboard y joystick)."
        )
        note.setWordWrap(True)
        note.setStyleSheet(_STYLE_INFO)
        layout.addWidget(note)
        layout.addStretch(1)

    # -- Grupos -----------------------------------------------------------

    def _build_keyboard_group(self) -> QGroupBox:
        config = self._keyboard
        group = QGroupBox("Teclado")
        form = QFormLayout(group)

        movement = _key_label(config.up)
        for extra in (config.down, config.left, config.right):
            movement += f" / {_key_label(extra)}"
        self._add_row(form, "Movimiento", movement)
        self._add_row(
            form,
            "Zoom",
            f"{_key_label(config.zoom_in)} (zoom +) / "
            f"{_key_label(config.zoom_out)} (zoom −)",
        )
        self._add_row(
            form,
            "Escenas (presets)",
            " · ".join(
                f"{_key_label(key)} → preset {preset_id}"
                for key, preset_id in config.preset_hotkeys.items()
            )
            or "—",
        )
        self._add_row(form, "Detener", _key_label(config.stop))
        self._add_row(form, "Salir", _key_label(config.quit))
        return group

    def _build_joystick_group(self) -> QGroupBox:
        config = self._joystick
        group = QGroupBox("Mando (joystick)")
        form = QFormLayout(group)

        tilt = "invertido" if config.invert_tilt else "normal"
        self._add_row(
            form,
            "Movimiento",
            f"Stick izquierdo (pan: eje {config.pan_axis}, "
            f"tilt: eje {config.tilt_axis}, {tilt})",
        )
        self._add_row(
            form,
            "Zoom",
            f"Eje {config.zoom_in_axis} (zoom +) / eje {config.zoom_out_axis} (zoom −)",
        )
        self._add_row(
            form,
            "Velocidad",
            f"Botón {config.speed_up_button} (+1) / "
            f"Botón {config.speed_down_button} (−1)",
        )
        self._add_row(form, "Home", f"Botón {config.home_button}")
        presets = ", ".join(
            f"{i + 1} → botón {button}"
            for i, button in enumerate(config.preset_buttons)
        )
        self._add_row(form, "Presets", presets)
        return group

    @staticmethod
    def _add_row(form: QFormLayout, label: str, value: str) -> None:
        value_label = QLabel(value)
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow(label, value_label)
