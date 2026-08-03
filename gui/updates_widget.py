"""Pestaña de búsqueda de actualizaciones.

Muestra la versión instalada y consulta la API de releases de GitHub para
avisar de versiones nuevas. La petición de red se ejecuta en un hilo en
segundo plano para no bloquear la GUI; el resultado llega por una señal
Qt (mismas reglas que el resto de la aplicación: nada de red en el hilo
de la interfaz).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.version import RELEASES_PAGE, UpdateResult, check_for_updates, get_version
from utils.logger import get_logger

log = get_logger(__name__)

_STYLE_INFO = (
    "background-color: #1e1e2e; color: #a6adc8; padding: 6px;"
    "border: 1px solid #313244; border-radius: 4px;"
)
_STYLE_OK = "color: #a6e3a1;"
_STYLE_WARN = "color: #f9e2af;"
_STYLE_ERR = "color: #f38ba8;"


class UpdatesWidget(QWidget):
    """Pestaña con la versión instalada y la comprobación de updates."""

    check_done = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._version = get_version()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        layout.addWidget(self._build_version_group())
        layout.addWidget(self._build_check_group())

        note = QLabel(
            "La comprobación consulta la API pública de GitHub y no "
            "envía ningún dato de su cámara ni de su configuración."
        )
        note.setWordWrap(True)
        note.setStyleSheet(_STYLE_INFO)
        layout.addWidget(note)
        layout.addStretch(1)

        self.check_done.connect(self._on_check_done)

    # -- Construcción -----------------------------------------------------

    def _build_version_group(self) -> QGroupBox:
        group = QGroupBox("Versión instalada")
        form = QFormLayout(group)
        self._version_label = QLabel(self._version)
        self._version_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("ptz-controller:", self._version_label)
        return group

    def _build_check_group(self) -> QGroupBox:
        group = QGroupBox("Buscar actualizaciones")
        layout = QVBoxLayout(group)

        self._status_label = QLabel("Pulse el botón para comprobar si hay una versión nueva.")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        buttons = QHBoxLayout()
        self._check_button = QPushButton("Buscar actualizaciones")
        self._check_button.clicked.connect(self._start_check)
        self._open_button = QPushButton("Abrir página de releases")
        self._open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(RELEASES_PAGE))
        )
        buttons.addWidget(self._check_button)
        buttons.addWidget(self._open_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return group

    # -- Comprobación -----------------------------------------------------

    def _start_check(self) -> None:
        self._check_button.setEnabled(False)
        self._status_label.setStyleSheet("")
        self._status_label.setText("Comprobando…")
        thread = threading.Thread(target=self._check_worker, daemon=True)
        thread.start()

    def _check_worker(self) -> None:
        try:
            result = check_for_updates()
        except Exception as exc:  # noqa: BLE001 - nunca debe romper la GUI
            log.error("Error al comprobar actualizaciones: %s", exc)
            result = UpdateResult(ok=False, error=str(exc))
        self.check_done.emit(result)

    def _on_check_done(self, result: object) -> None:
        self._check_button.setEnabled(True)
        if not getattr(result, "ok", False):
            self._status_label.setStyleSheet(_STYLE_ERR)
            self._status_label.setText(
                f"No se pudo comprobar: {getattr(result, 'error', 'error desconocido')}"
            )
            return
        current = getattr(result, "current", self._version)
        if getattr(result, "up_to_date", True):
            self._status_label.setStyleSheet(_STYLE_OK)
            self._status_label.setText(
                f"Está al día: la versión instalada es la más reciente (v{current})."
            )
            return
        latest = getattr(result, "latest", "?")
        self._status_label.setStyleSheet(_STYLE_WARN)
        self._status_label.setText(
            f"Nueva versión disponible: {latest} (tiene v{current}). "
            "Abra la página de releases para descargarla."
        )