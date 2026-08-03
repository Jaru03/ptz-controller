"""Smoke tests de la interfaz gráfica (plataforma Qt 'offscreen')."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QGroupBox, QLineEdit

from camera.mock_ptz import MockPTZController
from config.settings import Settings
from controllers.base import MovementState
from controllers.keyboard_controller import QtKeyboardController
from core.event_bus import EventBus
from core.ref import Ref
from gui.main_window import MainWindow
from models.commands import MoveCommand, QuitCommand, SetSpeedCommand


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def _process(app: QApplication, ms: int = 100) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    QTimer.singleShot(ms + 10, loop.quit)
    loop.exec()


def _build_window(app: QApplication):
    bus = EventBus()
    mock = MockPTZController()
    ref = Ref(mock)
    settings = Settings.defaults()
    movement = MovementState(settings.movement.deadzone, bus.send)
    keyboard = QtKeyboardController(settings.keyboard, movement, bus)
    window = MainWindow(ref, bus, settings, keyboard, "config.yaml", poll_interval_ms=33)
    return bus, mock, window


def test_window_constructs(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    _process(qapp)
    assert window.windowTitle() == "Controlador de cámaras PTZ ONVIF"
    mock.disconnect()
    window.close()


def test_status_updates_camera_widget(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    mock.connect()
    mock.move(1.0, 0.5, 0.0, 1.0)
    _process(qapp)
    assert window._camera_widget._status.pan > 0.0
    assert "Conectada" in window._conn_label.text()
    mock.disconnect()
    window.close()


def test_move_command_updates_position(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    mock.connect()
    mock.move(1.0, 0.0, 0.0, 0.5)
    _process(qapp, ms=120)
    assert window._camera_widget._status.pan > 0.0
    mock.disconnect()
    window.close()


def test_speed_command_updates_slider(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    bus.send(SetSpeedCommand(0.75))
    _process(qapp)
    assert window._speed_slider.value() == 75
    assert window._speed_value.text() == "75 %"
    mock.disconnect()
    window.close()


def test_quit_request_closes_window(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    bus.send(QuitCommand())
    _process(qapp)
    assert window._quitting
    mock.disconnect()


def test_qt_backend_ignores_keys_in_text_fields(qapp: QApplication) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    bus, mock, window = _build_window(qapp)
    window.show()
    window._user_field.setFocus()
    _process(qapp)
    assert isinstance(QApplication.focusWidget(), QLineEdit)

    press = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_W,
        Qt.KeyboardModifier.NoModifier,
        "w",
    )
    window.eventFilter(window._user_field, press)
    _process(qapp)
    assert not window._keyboard.is_active
    mock.disconnect()
    window.close()


def test_controls_tab_lists_keyboard_and_joystick(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QTabWidget

    from gui.controls_widget import ControlsWidget

    bus, mock, window = _build_window(qapp)
    window.show()
    _process(qapp)

    tabs = window.findChild(QTabWidget)
    assert tabs is not None
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Simulación",
        "Vista previa",
        "Controles",
    ]
    controls = window.findChild(ControlsWidget)
    assert controls is not None
    labels = []
    for group in controls.findChildren(QGroupBox):
        labels.append(group.title())
    assert "Teclado" in labels
    assert "Mando (joystick)" in labels

    mock.disconnect()
    window.close()


def test_presets_list_reflects_mock(qapp: QApplication) -> None:
    bus, mock, window = _build_window(qapp)
    window.show()
    mock.connect()
    mock.move(0.4, 0.0, 0.0, 1.0)
    mock._advance(1.0)
    mock.set_preset("1", "Entrada principal")
    bus.publish("ptz.presets", mock.list_presets())
    _process(qapp)
    assert window._preset_list.count() == 1
    assert "Entrada principal" in window._preset_list.item(0).text()
    mock.disconnect()
    window.close()


def test_presets_rename_via_bus_updates_list(qapp: QApplication) -> None:
    from models.commands import RenamePresetCommand

    bus, mock, window = _build_window(qapp)
    window.show()
    mock.connect()
    mock.set_preset("1", "Entrada principal")
    bus.publish("ptz.presets", mock.list_presets())
    _process(qapp)

    bus.subscribe(
        "command.renamePreset",
        lambda cmd: mock.rename_preset(cmd.token, cmd.name),
    )
    bus.send(RenamePresetCommand(token="1", name="Patio trasero"))
    bus.publish("ptz.presets", mock.list_presets())
    _process(qapp)
    assert window._preset_list.count() == 1
    assert "Patio trasero" in window._preset_list.item(0).text()
    assert "Entrada principal" not in window._preset_list.item(0).text()
    mock.disconnect()
    window.close()


def test_qt_backend_forwards_key_events(qapp: QApplication) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    bus, mock, window = _build_window(qapp)
    window.show()
    assert window._keyboard.requires_window_events

    press = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_W,
        Qt.KeyboardModifier.NoModifier,
        "w",
    )
    window.keyPressEvent(press)
    _process(qapp)
    assert window._keyboard.is_active

    release = QKeyEvent(
        QEvent.Type.KeyRelease,
        Qt.Key.Key_W,
        Qt.KeyboardModifier.NoModifier,
        "w",
    )
    window.keyReleaseEvent(release)
    _process(qapp)
    assert not window._keyboard.is_active
    mock.disconnect()
    window.close()
