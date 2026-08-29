"""Tests de gui_web/api.py (sin abrir ninguna ventana pywebview).

pywebview resuelve cada llamada JS a un método de ``Api`` como una
Promise; aquí se prueba directamente la clase Python, que es donde vive
toda la lógica (equivalente a lo que antes cubrían los tests manuales de
gui/connection_dialog.py, pero sin depender de una ventana real).
"""

import gui_web.api as api_module
from camera.discovery import DiscoveredDevice
from config.settings import Settings
from core.event_bus import EventBus
from gui_web.api import Api


def _api_with_bus() -> tuple[Api, Settings, list[str]]:
    bus = EventBus()
    sent: list[str] = []
    bus.subscribe("command.connect", lambda _cmd: sent.append("connect"))
    bus.subscribe("command.quit", lambda _cmd: sent.append("quit"))
    settings = Settings.defaults()
    return Api(bus, settings), settings, sent


def test_connect_sends_connect_command() -> None:
    api, _settings, sent = _api_with_bus()

    result = api.connect()

    assert result == {"ok": True}
    assert sent == ["connect"]


def test_quit_sends_quit_command() -> None:
    api, _settings, sent = _api_with_bus()

    api.quit()

    assert sent == ["quit"]


def test_apply_connection_settings_updates_camera() -> None:
    api, settings, _sent = _api_with_bus()

    result = api.apply_connection_settings(
        {
            "ip": " 10.0.0.9 ",
            "port": 8081,
            "username": "operador",
            "password": "secreta",
            "mock": False,
        }
    )

    assert result == {"ok": True}
    assert settings.camera.ip == "10.0.0.9"
    assert settings.camera.port == 8081
    assert settings.camera.username == "operador"
    assert settings.camera.password == "secreta"
    assert settings.camera.mock is False


def test_apply_connection_settings_ignores_missing_keys() -> None:
    api, settings, _sent = _api_with_bus()
    original_ip = settings.camera.ip

    api.apply_connection_settings({})

    assert settings.camera.ip == original_ip


def test_get_settings_matches_settings_to_dict() -> None:
    api, settings, _sent = _api_with_bus()

    assert api.get_settings() == settings.to_dict()


def test_discover_returns_json_safe_devices(monkeypatch) -> None:
    device = DiscoveredDevice(
        host="10.0.0.5",
        port=80,
        xaddrs=("http://10.0.0.5/onvif/device_service",),
        scopes=(),
        types=(),
    )
    monkeypatch.setattr(api_module, "discover_devices", lambda timeout: [device])
    api, _settings, _sent = _api_with_bus()

    devices = api.discover()

    assert devices == [
        {
            "host": "10.0.0.5",
            "port": 80,
            "xaddrs": ["http://10.0.0.5/onvif/device_service"],
            "scopes": [],
            "types": [],
        }
    ]


def test_discover_returns_empty_list_on_error(monkeypatch) -> None:
    def boom(timeout: float) -> list[DiscoveredDevice]:
        raise OSError("sin red")

    monkeypatch.setattr(api_module, "discover_devices", boom)
    api, _settings, _sent = _api_with_bus()

    assert api.discover() == []
