"""Diálogo de conexión mostrado antes de abrir la ventana principal.

Pide los datos de la cámara (IP, puerto, credenciales, modo simulado) al
arrancar la aplicación, de modo que la interfaz principal aparece ya
intentando conectar en vez de arrancar vacía a la espera de que el
usuario rellene el panel de conexión a mano.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from camera.discovery import discover_devices
from config.settings import Settings
from utils.logger import get_logger

log = get_logger(__name__)


class _DiscoveryBridge(QObject):
    """Puente hilo de descubrimiento -> señales Qt (marshalling)."""

    found = Signal(object)
    error = Signal(str)
    done = Signal()


class ConnectionDialog(QDialog):
    """Recoge los datos de la cámara antes de mostrar la ventana principal."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("Conectar con la cámara")
        self.setMinimumWidth(360)
        self._settings = settings

        self._bridge = _DiscoveryBridge()
        self._bridge.found.connect(self._on_discovery)
        self._bridge.error.connect(self._on_discovery_error)
        self._bridge.done.connect(self._on_discovery_done)

        camera = settings.camera
        form = QFormLayout()

        self._ip_field = QLineEdit(camera.ip)
        self._port_field = QSpinBox()
        self._port_field.setRange(1, 65535)
        self._port_field.setValue(camera.port)
        self._user_field = QLineEdit(camera.username)
        self._pass_field = QLineEdit(camera.password)
        self._pass_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._mock_check = QCheckBox("Cámara simulada (Mock)")
        self._mock_check.setChecked(camera.mock)
        self._mock_check.setToolTip(
            "Usa una cámara virtual para probar sin hardware."
        )

        form.addRow("IP:", self._ip_field)
        form.addRow("Puerto:", self._port_field)
        form.addRow("Usuario:", self._user_field)
        form.addRow("Contraseña:", self._pass_field)
        form.addRow("", self._mock_check)

        self._discover_button = QPushButton("Buscar cámaras…")
        self._discover_button.clicked.connect(self._start_discovery)
        form.addRow(self._discover_button)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Conectar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if camera.ip:
            self._pass_field.setFocus()
        else:
            self._ip_field.setFocus()

    def apply_to_settings(self) -> None:
        """Vuelca los campos del formulario sobre ``settings.camera``."""
        camera = self._settings.camera
        camera.ip = self._ip_field.text().strip()
        camera.port = self._port_field.value()
        camera.username = self._user_field.text()
        camera.password = self._pass_field.text()
        camera.mock = self._mock_check.isChecked()

    # -- Descubrimiento de cámaras ----------------------------------------

    def _start_discovery(self) -> None:
        self._discover_button.setEnabled(False)
        self._discover_button.setText("Buscando…")
        threading.Thread(target=self._discovery_worker, daemon=True).start()

    def _discovery_worker(self) -> None:
        try:
            devices = discover_devices(timeout=4)
            self._bridge.found.emit(devices)
        except Exception as exc:  # noqa: BLE001
            log.error("Error en el descubrimiento: %s", exc)
            self._bridge.error.emit(f"Error al buscar cámaras: {exc}")
        finally:
            self._bridge.done.emit()

    def _on_discovery(self, devices: object) -> None:
        devices = devices or []
        if not devices:
            QMessageBox.information(
                self, "Descubrimiento", "No se encontraron cámaras ONVIF."
            )
            return
        if len(devices) == 1:
            self._ip_field.setText(devices[0].host)
            self._port_field.setValue(devices[0].port)
            return
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Cámaras encontradas")
        dialog.setLabelText("Seleccione una cámara:")
        names = [f"{device.host}:{device.port}" for device in devices]
        dialog.setComboBoxItems(names)
        if dialog.exec() and dialog.textValue():
            host = dialog.textValue().split(":")[0]
            self._ip_field.setText(host)

    def _on_discovery_error(self, message: str) -> None:
        QMessageBox.warning(self, "Error", message)

    def _on_discovery_done(self) -> None:
        self._discover_button.setEnabled(True)
        self._discover_button.setText("Buscar cámaras…")
