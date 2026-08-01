"""Tests de la configuración YAML."""

import yaml

from config.settings import Settings


def test_defaults_are_used_without_file(tmp_path) -> None:
    settings = Settings.load(tmp_path / "missing.yaml")
    assert settings.camera.ip == "192.168.1.100"
    assert settings.movement.speed == 0.5
    assert settings.joystick.deadzone == 0.08
    assert settings.keyboard.backend == "auto"


def test_roundtrip_save_and_load(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    settings = Settings.defaults()
    settings.camera.ip = "10.0.0.5"
    settings.camera.port = 8080
    settings.movement.speeds = [0.1, 0.5, 0.9]
    settings.joystick.device_overrides = {"Xbox": {"home_button": 3}}
    settings.save(path)

    loaded = Settings.load(path)
    assert loaded.camera.ip == "10.0.0.5"
    assert loaded.camera.port == 8080
    assert loaded.movement.speeds == [0.1, 0.5, 0.9]
    assert loaded.joystick.device_overrides == {"Xbox": {"home_button": 3}}


def test_partial_yaml_merges_over_defaults(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("camera:\n    ip: 192.168.1.50\n", encoding="utf-8")
    settings = Settings.load(path)
    assert settings.camera.ip == "192.168.1.50"
    assert settings.camera.port == 80
    assert settings.movement.speed == 0.5


def test_unknown_keys_are_ignored(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("camera:\n    ip: 1.2.3.4\n    inexistente: true\n", encoding="utf-8")
    settings = Settings.load(path)
    assert settings.camera.ip == "1.2.3.4"


def test_ensure_default_config_creates_file(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    settings = Settings.ensure_default_config(path)
    assert path.is_file()
    assert settings.camera.ip == "192.168.1.100"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "camera" in data
    assert "joystick" in data


def test_ensure_default_config_keeps_existing(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("camera:\n    ip: 9.9.9.9\n", encoding="utf-8")
    settings = Settings.ensure_default_config(path)
    assert settings.camera.ip == "9.9.9.9"


def test_validate_reports_invalid_values() -> None:
    settings = Settings.defaults()
    settings.movement.speed = 1.5
    settings.keyboard.backend = "bogus"
    settings.camera.port = 99999
    warnings = settings.validate()
    assert any("speed" in warning for warning in warnings)
    assert any("backend" in warning for warning in warnings)
    assert any("port" in warning for warning in warnings)


def test_validate_ok_for_defaults() -> None:
    assert Settings.defaults().validate() == []
