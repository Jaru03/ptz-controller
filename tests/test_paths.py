"""Tests de la resolución de rutas (código fuente vs ejecutable congelado)."""

import sys
from pathlib import Path

from utils import paths


def _freeze(monkeypatch, bundle_dir: Path) -> None:
    """Simula la ejecución dentro de un ejecutable de PyInstaller."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)


def test_source_mode_keeps_everything_next_to_the_project() -> None:
    assert not paths.is_frozen()
    assert paths.resource_dir() == paths.PROJECT_ROOT
    assert paths.default_config_path() == paths.PROJECT_ROOT / "config.yaml"
    assert paths.default_log_dir("logs") == paths.PROJECT_ROOT / "logs"


def test_frozen_mode_uses_the_bundle_for_resources(monkeypatch, tmp_path) -> None:
    _freeze(monkeypatch, tmp_path)
    assert paths.resource_dir() == tmp_path


def test_frozen_mode_writes_under_the_user_directory(monkeypatch, tmp_path) -> None:
    # El directorio del programa puede ser de solo lectura (~/.local/bin,
    # Program Files), así que config y logs van al directorio del usuario.
    _freeze(monkeypatch, tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "cfg"))

    config_path = paths.default_config_path()
    assert config_path.name == "config.yaml"
    assert paths.PROJECT_ROOT not in config_path.parents
    assert config_path.parent.name == paths.APP_NAME
    assert paths.default_log_dir("logs") == config_path.parent / "logs"


def test_absolute_log_dir_is_always_respected(monkeypatch, tmp_path) -> None:
    absolute = tmp_path / "otro" / "sitio"
    assert paths.default_log_dir(absolute) == absolute
    _freeze(monkeypatch, tmp_path)
    assert paths.default_log_dir(absolute) == absolute


def test_bundled_file_only_returns_existing_resources(monkeypatch, tmp_path) -> None:
    _freeze(monkeypatch, tmp_path)
    assert paths.bundled_file("config.yaml.example") is None
    (tmp_path / "config.yaml.example").write_text("camera: {}\n", encoding="utf-8")
    assert paths.bundled_file("config.yaml.example") == tmp_path / "config.yaml.example"


def test_wsdl_dir_prefers_the_bundled_copy(monkeypatch, tmp_path) -> None:
    # Sin esta preferencia, el ejecutable buscaría los WSDL en unos
    # site-packages que no existen y la conexión ONVIF fallaría.
    from camera import client

    bundled_wsdl = tmp_path / "wsdl"
    bundled_wsdl.mkdir()
    monkeypatch.setattr(client, "resource_dir", lambda: tmp_path)
    assert client._resolve_wsdl_dir() == str(bundled_wsdl)


def test_wsdl_dir_falls_back_to_site_packages(monkeypatch, tmp_path) -> None:
    from camera import client

    monkeypatch.setattr(client, "resource_dir", lambda: tmp_path)
    resolved = Path(client._resolve_wsdl_dir())
    assert resolved.is_dir()
    assert (resolved / "ptz.wsdl").is_file()
