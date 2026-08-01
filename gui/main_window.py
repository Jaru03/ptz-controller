"""Ventana principal de la aplicación.

Compone la vista de cámara (simulación / vídeo), el panel de control
(conexión, estado, presets, configuración) y el panel de logs. Toda la
comunicación con el resto de la aplicación ocurre a través del
``EventBus``: la ventana publica comandos y recibe instantáneas de estado
(marshalled al hilo de la GUI mediante ``QtEventBridge``).
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from camera.discovery import DiscoveredDevice, discover_devices
from config.settings import Settings
from controllers.keyboard_controller import KeyboardController, qt_key_name
from core.event_bus import EventBus
from core.ref import Ref
from gui.camera_widget import CameraWidget
from gui.controls_widget import ControlsWidget
from gui.settings_dialog import SettingsDialog
from gui.video_widget import VideoWidget
from models.commands import (
    ConnectCommand,
    DisconnectCommand,
    GotoPresetCommand,
    PTZStatus,
    QuitCommand,
    RemovePresetCommand,
    RenamePresetCommand,
    SetPresetCommand,
    SetSpeedCommand,
)
from utils.logger import get_logger

log = get_logger(__name__)

_CONNECTED_COLOR = "#a6e3a1"
_DISCONNECTED_COLOR = "#f38ba8"
_NEUTRAL_COLOR = "#cdd6f4"

_TEXT_INPUT_WIDGETS = (
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QComboBox,
    QAbstractSpinBox,
)


class QtEventBridge(QObject):
    """Puente bus -> señales Qt (marshalling entre hilos).

    Los handlers del bus pueden ejecutarse en cualquier hilo; emitir una
    señal Qt desde otro hilo encola la actualización hacia el hilo de la
    GUI de forma segura.
    """

    status = Signal(object)
    keyboard = Signal(dict)
    joystick = Signal(dict)
    speed = Signal(object)
    presets = Signal(object)
    discovery = Signal(object)
    discovery_done = Signal()
    error = Signal(str)
    quit_request = Signal(object)
    log_message = Signal(str)

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        bus.subscribe("ptz.status", self.status.emit)
        bus.subscribe("input.keyboard", self.keyboard.emit)
        bus.subscribe("input.joystick", self.joystick.emit)
        bus.subscribe("command.setSpeed", self.speed.emit)
        bus.subscribe("ptz.presets", self.presets.emit)
        bus.subscribe("gui.discovery", self.discovery.emit)
        bus.subscribe("gui.error", self.error.emit)
        bus.subscribe("command.quit", self.quit_request.emit)


class MainWindow(QMainWindow):
    """Ventana principal de ptz-controller."""

    def __init__(
        self,
        controller_ref: Ref,
        bus: EventBus,
        settings: Settings,
        keyboard_controller: KeyboardController | None,
        config_path: str,
        poll_interval_ms: int,
    ) -> None:
        super().__init__()
        self._ref = controller_ref
        self._bus = bus
        self._settings = settings
        self._keyboard = keyboard_controller
        self._config_path = config_path
        self._quitting = False
        self._updating_speed = False
        self._video_url = ""

        self._bridge = QtEventBridge(bus)

        self.setWindowTitle("Controlador de cámaras PTZ ONVIF")
        self.resize(1024, 720)

        self._build_ui()
        self._wire_bridge()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(max(30, poll_interval_ms))
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start()

        self._bus.publish("ptz.status", self._ref.value.get_status())
        self._publish_presets()

    # -- Construcción de la interfaz --------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._camera_widget = CameraWidget()
        self._video_widget = VideoWidget(fps=self._settings.gui.video_fps)
        self._controls_widget = ControlsWidget(
            self._settings.keyboard, self._settings.joystick
        )
        tabs = QTabWidget()
        tabs.addTab(self._camera_widget, "Simulación")
        tabs.addTab(self._video_widget, "Vista previa")
        tabs.addTab(self._controls_widget, "Controles")
        tabs.setCurrentIndex(0)

        controls = self._build_controls_panel()

        splitter.addWidget(tabs)
        splitter.addWidget(controls)
        splitter.setSizes([620, 380])
        root.addWidget(splitter, 1)

        root.addWidget(self._build_log_panel())
        central.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        central.setFocus()
        self.setCentralWidget(central)

    def _build_controls_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._build_connection_group())
        layout.addWidget(self._build_status_group())
        layout.addWidget(self._build_presets_group())

        self._config_button = QPushButton("Configuración…")
        self._config_button.clicked.connect(self._open_settings_dialog)
        layout.addWidget(self._config_button)
        layout.addStretch(1)
        return panel

    def _build_connection_group(self) -> QGroupBox:
        camera = self._settings.camera
        group = QGroupBox("Conexión")
        form = QFormLayout(group)

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
        self._connect_button = QPushButton("Conectar")
        self._connect_button.clicked.connect(self._toggle_connect)

        buttons = QHBoxLayout()
        buttons.addWidget(self._discover_button)
        buttons.addWidget(self._connect_button)
        form.addRow(buttons)

        self._conn_label = QLabel()
        self._conn_label.setStyleSheet("font-weight: bold;")
        self._conn_label.setWordWrap(True)
        form.addRow(self._conn_label)
        return group

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Estado")
        form = QFormLayout(group)

        self._device_label = QLabel("—")
        self._ip_label = QLabel("—")
        self._joystick_label = QLabel("Sin mando")
        self._keyboard_label = QLabel("—")

        form.addRow("Dispositivo:", self._device_label)
        form.addRow("IP:", self._ip_label)
        form.addRow("Joystick:", self._joystick_label)
        form.addRow("Teclado:", self._keyboard_label)

        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(0, 100)
        self._speed_slider.setValue(int(self._settings.movement.speed * 100))
        self._speed_slider.valueChanged.connect(self._on_slider_moved)
        self._speed_value = QLabel("50 %")
        speed_row = QHBoxLayout()
        speed_row.addWidget(self._speed_slider, 1)
        speed_row.addWidget(self._speed_value)
        form.addRow("Velocidad:", speed_row)
        return group

    def _build_presets_group(self) -> QGroupBox:
        group = QGroupBox("Presets")
        layout = QVBoxLayout(group)

        self._preset_list = QListWidget()
        self._preset_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._preset_list.itemDoubleClicked.connect(self._preset_go_action)
        layout.addWidget(self._preset_list)

        buttons = QHBoxLayout()
        self._preset_go = QPushButton("Ir")
        self._preset_save = QPushButton("Guardar")
        self._preset_rename = QPushButton("Renombrar")
        self._preset_delete = QPushButton("Borrar")
        self._preset_go.clicked.connect(self._preset_go_action)
        self._preset_save.clicked.connect(self._preset_save_action)
        self._preset_rename.clicked.connect(self._preset_rename_action)
        self._preset_delete.clicked.connect(self._preset_delete_action)
        buttons.addWidget(self._preset_go)
        buttons.addWidget(self._preset_save)
        buttons.addWidget(self._preset_rename)
        buttons.addWidget(self._preset_delete)
        layout.addLayout(buttons)
        return group

    def _build_log_panel(self) -> QGroupBox:
        group = QGroupBox("Logs")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 4, 4, 4)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumBlockCount(5000)
        self._log_edit.setStyleSheet(
            "background-color: #15151f; color: #cdd6f4; font-family: monospace;"
        )
        layout.addWidget(self._log_edit)
        group.setMaximumHeight(220)
        return group

    # -- Puente de eventos ------------------------------------------------

    def _wire_bridge(self) -> None:
        bridge = self._bridge
        bridge.status.connect(self._on_status)
        bridge.keyboard.connect(self._on_keyboard_state)
        bridge.joystick.connect(self._on_joystick_state)
        bridge.speed.connect(self._on_speed_command)
        bridge.presets.connect(self._on_presets)
        bridge.discovery.connect(self._on_discovery)
        bridge.discovery_done.connect(self._on_discovery_done)
        bridge.error.connect(self._on_gui_error)
        bridge.quit_request.connect(self.close)
        bridge.log_message.connect(self._append_log)

    # -- Slots de estado --------------------------------------------------

    def _poll_status(self) -> None:
        self._bus.publish("ptz.status", self._ref.value.get_status())

    def _on_status(self, status: PTZStatus) -> None:
        self._camera_widget.update_status(status)

        if status.connected:
            self._conn_label.setText(
                f'<span style="color:{_CONNECTED_COLOR}">● Conectada</span> '
                f"— {status.device_name}"
            )
            self._connect_button.setText("Desconectar")
            self._device_label.setText(status.device_name)
            self._ip_label.setText(status.ip)
            self._start_video_if_available()
        else:
            self._conn_label.setText(
                f'<span style="color:{_DISCONNECTED_COLOR}">● Desconectada</span>'
            )
            self._connect_button.setText("Conectar")
            self._device_label.setText("—")
            self._ip_label.setText("—")
            self._video_widget.show_placeholder(
                "Sin señal\n(conéctese una cámara real para ver el stream RTSP)"
            )
            self._video_url = ""

    def _on_keyboard_state(self, payload: dict) -> None:
        backend = payload.get("backend", "?")
        active = payload.get("active", False)
        if active:
            self._keyboard_label.setText(f"Activo (backend: {backend})")
        else:
            self._keyboard_label.setText(f"Inactivo (backend: {backend})")

    def _on_joystick_state(self, payload: dict) -> None:
        if payload.get("connected"):
            self._joystick_label.setText(f"{payload.get('name', 'Mando')} (conectado)")
        else:
            self._joystick_label.setText("Sin mando")

    def _on_speed_command(self, command: object) -> None:
        speed = getattr(command, "speed", None)
        if speed is None:
            return
        self._updating_speed = True
        self._speed_slider.setValue(int(speed * 100))
        self._updating_speed = False
        self._speed_value.setText(f"{speed * 100:.0f} %")

    def _on_presets(self, presets: object) -> None:
        self._preset_list.clear()
        for preset in presets or ():
            preset_id = getattr(preset, "preset_id", None)
            name = getattr(preset, "name", "") or f"Preset {preset_id}"
            item = QListWidgetItem(f"{name}  [{preset_id}]")
            item.setData(Qt.ItemDataRole.UserRole, preset_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self._preset_list.addItem(item)

    def _on_gui_error(self, message: str) -> None:
        QMessageBox.warning(self, "Error", message)

    # -- Conexión ---------------------------------------------------------

    def _toggle_connect(self) -> None:
        status = self._ref.value.get_status()
        if status.connected:
            self._bus.send(DisconnectCommand())
        else:
            self._apply_connection_form_to_settings()
            self._bus.send(ConnectCommand())

    def _apply_connection_form_to_settings(self) -> None:
        camera = self._settings.camera
        camera.ip = self._ip_field.text().strip()
        camera.port = self._port_field.value()
        camera.username = self._user_field.text()
        camera.password = self._pass_field.text()
        camera.mock = self._mock_check.isChecked()

    def _start_video_if_available(self) -> None:
        if self._video_url:
            return
        configured = self._settings.camera.rtsp_url.strip()
        url = configured or self._ref.value.stream_uri()
        if url:
            self._video_url = url
            self._video_widget.start(url)

    # -- Presets ----------------------------------------------------------

    def _selected_preset_id(self) -> int | None:
        item = self._preset_list.currentItem()
        if item is None:
            return None
        return int(item.data(Qt.ItemDataRole.UserRole))

    def _preset_go_action(self) -> None:
        preset_id = self._selected_preset_id()
        if preset_id is None:
            return
        self._bus.send(GotoPresetCommand(preset_id))

    def _preset_save_action(self) -> None:
        next_id = 1
        if self._preset_list.count():
            ids = [
                int(self._preset_list.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(self._preset_list.count())
            ]
            next_id = max(ids) + 1
        result = self._prompt_preset(f"Guardar preset {next_id}", "", next_id)
        if result is None:
            return
        preset_id, name = result
        self._bus.send(SetPresetCommand(preset_id, name))
        self._publish_presets()

    def _preset_rename_action(self) -> None:
        item = self._preset_list.currentItem()
        if item is None:
            return
        preset_id = int(item.data(Qt.ItemDataRole.UserRole))
        current_name = str(item.data(Qt.ItemDataRole.UserRole + 1))
        result = self._prompt_preset(f"Renombrar preset {preset_id}", current_name, preset_id)
        if result is None:
            return
        new_id, new_name = result
        if new_id != preset_id:
            self._bus.send(RemovePresetCommand(preset_id))
            self._bus.send(SetPresetCommand(new_id, new_name))
        else:
            self._bus.send(RenamePresetCommand(preset_id, new_name))
        self._publish_presets()

    def _prompt_preset(self, title: str, default_name: str, default_id: int) -> tuple[int, str] | None:
        """Pide nombre y número de preset; devuelve (id, nombre) o None."""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)

        name_field = QLineEdit(default_name)
        name_field.setPlaceholderText("Nombre del preset (ej. Entrada principal)")
        id_field = QSpinBox()
        id_field.setRange(1, 999)
        id_field.setValue(default_id)

        form.addRow("Nombre:", name_field)
        form.addRow("Número:", id_field)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        name_field.selectAll()
        name_field.setFocus()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        name = name_field.text().strip()
        if not name:
            name = f"Preset {id_field.value()}"
        return id_field.value(), name

    def _preset_delete_action(self) -> None:
        preset_id = self._selected_preset_id()
        if preset_id is None:
            return
        self._bus.send(RemovePresetCommand(preset_id))
        self._publish_presets()

    def _publish_presets(self) -> None:
        self._bus.publish("ptz.presets", self._ref.value.list_presets())

    # -- Velocidad --------------------------------------------------------

    def _on_slider_moved(self, value: int) -> None:
        if self._updating_speed:
            return
        speed = value / 100.0
        self._speed_value.setText(f"{value} %")
        self._bus.send(SetSpeedCommand(speed))

    # -- Descubrimiento de cámaras ----------------------------------------

    def _start_discovery(self) -> None:
        self._discover_button.setEnabled(False)
        self._discover_button.setText("Buscando…")
        threading.Thread(target=self._discovery_worker, daemon=True).start()

    def _discovery_worker(self) -> None:
        try:
            devices = discover_devices(timeout=4)
            self._bridge.discovery.emit(devices)
        except Exception as exc:  # noqa: BLE001
            log.error("Error en el descubrimiento: %s", exc)
            self._bridge.error.emit(f"Error al buscar cámaras: {exc}")
        finally:
            self._bridge.discovery_done.emit()

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
        names = [
            f"{device.host}:{device.port}" for device in devices
        ]
        dialog.setComboBoxItems(names)
        if dialog.exec() and dialog.textValue():
            host = dialog.textValue().split(":")[0]
            self._ip_field.setText(host)

    def _on_discovery_done(self) -> None:
        self._discover_button.setEnabled(True)
        self._discover_button.setText("Buscar cámaras…")

    # -- Configuración ----------------------------------------------------

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            self._settings = dialog.result_settings()
            self._settings.save(self._config_path)
            self._apply_settings_to_ui()
            log.info("Configuración guardada en %s", self._config_path)

    def _apply_settings_to_ui(self) -> None:
        camera = self._settings.camera
        self._ip_field.setText(camera.ip)
        self._port_field.setValue(camera.port)
        self._user_field.setText(camera.username)
        self._pass_field.setText(camera.password)
        self._mock_check.setChecked(camera.mock)
        self._on_speed_command(SimpleNamespace(speed=self._settings.movement.speed))

    # -- Logs -------------------------------------------------------------

    def append_log(self, message: str) -> None:
        """Punto de entrada para el handler de logging (cualquier hilo)."""
        self._bridge.log_message.emit(message)

    def _append_log(self, message: str) -> None:
        self._log_edit.appendPlainText(message)

    # -- Teclado ----------------------------------------------------------

    def eventFilter(self, watched: QObject, event) -> bool:  # noqa: N802 - API Qt
        """Captura el teclado a nivel de aplicación.

        El backend Qt recibe las teclas estén donde esté el foco dentro de
        la ventana principal (los widgets hijos roban el foco). Se ignoran
        las teclas escritas en campos de texto y las de otras ventanas
        (ajustes, diálogos).
        """
        if self._keyboard is not None and self._keyboard.requires_window_events:
            etype = event.type()
            if etype in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                active = QApplication.activeWindow()
                focused = QApplication.focusWidget()
                if (active is None or active is self) and not isinstance(
                    focused, _TEXT_INPUT_WIDGETS
                ):
                    if (
                        etype == QEvent.Type.KeyRelease
                        and event.isAutoRepeat()
                    ):
                        return super().eventFilter(watched, event)
                    name = qt_key_name(event)
                    if name:
                        if etype == QEvent.Type.KeyPress:
                            self._keyboard.on_key_down(name)
                        else:
                            self._keyboard.on_key_up(name)
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - API Qt
        if self._keyboard is not None and self._keyboard.requires_window_events:
            name = qt_key_name(event)
            if name:
                self._keyboard.on_key_down(name)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - API Qt
        if self._keyboard is not None and self._keyboard.requires_window_events:
            name = qt_key_name(event)
            if name:
                self._keyboard.on_key_up(name)
        super().keyReleaseEvent(event)

    # -- Cierre -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        if not self._quitting:
            self._quitting = True
            self._bus.send(QuitCommand())
            event.ignore()
        else:
            event.accept()
