"""Diálogo de configuración de la aplicación.

Permite editar los parámetros de conexión de la cámara y el movimiento
(velocidad, deadzone) y guardarlos en el archivo YAML de configuración.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.settings import Settings

_ZOOM_MODES = ("continuous", "step", "auto")
_ZOOM_MODE_LABELS = {
    "continuous": "Continuo (recomendado, compatible con casi cualquier cámara)",
    "step": "A saltos (para intermedio, puede no mover el zoom en algunas cámaras)",
    "auto": "Automático (a saltos, y si falla con error, continuo)",
}


class SettingsDialog(QDialog):
    """Diálogo modal de edición de la configuración."""

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(360)
        self._settings = settings

        form = QFormLayout()

        camera = settings.camera
        self._ip = QLineEdit(camera.ip)
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(camera.port)
        self._username = QLineEdit(camera.username)
        self._password = QLineEdit(camera.password)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._rtsp_url = QLineEdit(camera.rtsp_url)
        self._rtsp_url.setPlaceholderText("Automática vía ONVIF si se deja vacío")
        self._mock = QCheckBox("Usar cámara simulada (Mock)")
        self._mock.setChecked(camera.mock)

        form.addRow("IP de la cámara:", self._ip)
        form.addRow("Puerto:", self._port)
        form.addRow("Usuario:", self._username)
        form.addRow("Contraseña:", self._password)
        form.addRow("URL RTSP:", self._rtsp_url)
        form.addRow("", self._mock)

        movement = settings.movement
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.0, 1.0)
        self._speed.setSingleStep(0.05)
        self._speed.setValue(movement.speed)
        self._deadzone = QDoubleSpinBox()
        self._deadzone.setRange(0.0, 0.5)
        self._deadzone.setSingleStep(0.01)
        self._deadzone.setValue(movement.deadzone)
        self._zoom_mode = QComboBox()
        for mode in _ZOOM_MODES:
            self._zoom_mode.addItem(_ZOOM_MODE_LABELS[mode], mode)
        if movement.zoom_mode in _ZOOM_MODES:
            self._zoom_mode.setCurrentIndex(_ZOOM_MODES.index(movement.zoom_mode))
        self._zoom_mode.setToolTip(
            "Si el zoom no se mueve con la cámara real, pruebe 'Continuo'."
        )

        form.addRow("Velocidad:", self._speed)
        form.addRow("Zona muerta:", self._deadzone)
        form.addRow("Modo de zoom:", self._zoom_mode)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_settings(self) -> Settings:
        """Devuelve la configuración resultante de la edición."""
        settings = Settings.from_dict(self._settings.to_dict())
        settings.camera.ip = self._ip.text().strip()
        settings.camera.port = self._port.value()
        settings.camera.username = self._username.text()
        settings.camera.password = self._password.text()
        settings.camera.rtsp_url = self._rtsp_url.text().strip()
        settings.camera.mock = self._mock.isChecked()
        settings.movement.speed = self._speed.value()
        settings.movement.deadzone = self._deadzone.value()
        settings.movement.zoom_mode = self._zoom_mode.currentData()
        return settings
