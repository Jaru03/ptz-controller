"""Tests de gui_web/api.py (sin abrir ninguna ventana pywebview).

pywebview resuelve cada llamada JS a un método de ``Api`` como una
Promise; aquí se prueba directamente la clase Python, que es donde vive
toda la lógica (equivalente a lo que antes cubrían los tests manuales de
gui/connection_dialog.py o gui/main_window.py, pero sin depender de una
ventana real).
"""

import gui_web.api as api_module
from camera.discovery import DiscoveredDevice
from config.settings import Settings
from core.event_bus import EventBus
from gui_web.api import Api


def _api_with_bus(tmp_path) -> tuple[Api, Settings, list[str]]:
    bus = EventBus()
    sent: list[str] = []
    for topic in (
        "command.connect",
        "command.disconnect",
        "command.quit",
        "command.gotoPreset",
        "command.setPreset",
        "command.renamePreset",
        "command.removePreset",
        "command.setSpeed",
    ):
        bus.subscribe(topic, lambda cmd, topic=topic: sent.append(topic))
    settings = Settings.defaults()
    return Api(bus, settings, tmp_path / "config.yaml"), settings, sent


def test_connect_sends_connect_command(tmp_path) -> None:
    api, _settings, sent = _api_with_bus(tmp_path)

    result = api.connect()

    assert result == {"ok": True}
    assert sent == ["command.connect"]


def test_disconnect_sends_disconnect_command(tmp_path) -> None:
    api, _settings, sent = _api_with_bus(tmp_path)

    api.disconnect()

    assert sent == ["command.disconnect"]


def test_quit_sends_quit_command(tmp_path) -> None:
    api, _settings, sent = _api_with_bus(tmp_path)

    api.quit()

    assert sent == ["command.quit"]


def test_preset_commands_go_through_the_bus(tmp_path) -> None:
    api, _settings, sent = _api_with_bus(tmp_path)

    api.goto_preset("1")
    api.set_preset("1", "Entrada")
    api.rename_preset("1", "Patio")
    api.remove_preset("1")

    assert sent == [
        "command.gotoPreset",
        "command.setPreset",
        "command.renamePreset",
        "command.removePreset",
    ]


def test_set_speed_sends_set_speed_command(tmp_path) -> None:
    api, _settings, sent = _api_with_bus(tmp_path)

    result = api.set_speed(0.75)

    assert result == {"ok": True}
    assert sent == ["command.setSpeed"]


def test_apply_connection_settings_updates_camera(tmp_path) -> None:
    api, settings, _sent = _api_with_bus(tmp_path)

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


def test_apply_connection_settings_ignores_missing_keys(tmp_path) -> None:
    api, settings, _sent = _api_with_bus(tmp_path)
    original_ip = settings.camera.ip

    api.apply_connection_settings({})

    assert settings.camera.ip == original_ip


def test_get_settings_matches_settings_to_dict(tmp_path) -> None:
    api, settings, _sent = _api_with_bus(tmp_path)

    assert api.get_settings() == settings.to_dict()


def test_save_settings_mutates_the_live_settings_object(tmp_path) -> None:
    """save_settings no debe sustituir el objeto Settings por uno nuevo.

    Otro código (closures de main.py, MovementState...) guarda una
    referencia directa a este mismo objeto: si se reemplazara, se
    quedarían leyendo datos obsoletos sin enterarse.
    """
    config_path = tmp_path / "config.yaml"
    bus = EventBus()
    settings = Settings.defaults()
    api = Api(bus, settings, config_path)

    result = api.save_settings(
        {
            "camera": {"ip": " 10.0.0.9 ", "rtsp_url": " rtsp://cam/1 "},
            "movement": {"speed": 0.8, "deadzone": 0.15, "zoom_mode": "step"},
        }
    )

    assert settings.camera.ip == "10.0.0.9"  # el mismo objeto, mutado
    assert settings.camera.rtsp_url == "rtsp://cam/1"
    assert settings.movement.speed == 0.8
    assert settings.movement.deadzone == 0.15
    assert settings.movement.zoom_mode == "step"
    assert result == settings.to_dict()


def test_save_settings_persists_to_config_path(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    bus = EventBus()
    settings = Settings.defaults()
    api = Api(bus, settings, config_path)

    api.save_settings({"camera": {"ip": "10.0.0.9"}})

    assert config_path.is_file()
    reloaded = Settings.load(config_path)
    assert reloaded.camera.ip == "10.0.0.9"


def test_save_settings_ignores_missing_keys(tmp_path) -> None:
    api, settings, _sent = _api_with_bus(tmp_path)
    original_speed = settings.movement.speed

    api.save_settings({})

    assert settings.movement.speed == original_speed


def test_discover_returns_json_safe_devices(monkeypatch, tmp_path) -> None:
    device = DiscoveredDevice(
        host="10.0.0.5",
        port=80,
        xaddrs=("http://10.0.0.5/onvif/device_service",),
        scopes=(),
        types=(),
    )
    monkeypatch.setattr(api_module, "discover_devices", lambda timeout: [device])
    api, _settings, _sent = _api_with_bus(tmp_path)

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


def test_discover_returns_empty_list_on_error(monkeypatch, tmp_path) -> None:
    def boom(timeout: float) -> list[DiscoveredDevice]:
        raise OSError("sin red")

    monkeypatch.setattr(api_module, "discover_devices", boom)
    api, _settings, _sent = _api_with_bus(tmp_path)

    assert api.discover() == []
