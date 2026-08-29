"""Tests de main.py::resolve_mock (decide entre cámara real y simulada)."""

import argparse

import main
from config.settings import Settings


def _args(mock: bool = False, real: bool = False) -> argparse.Namespace:
    return argparse.Namespace(mock=mock, real=real)


def test_explicit_mock_flag_wins() -> None:
    settings = Settings.defaults()
    settings.camera.mock = False
    assert main.resolve_mock(_args(mock=True), settings) is True


def test_explicit_real_flag_wins() -> None:
    settings = Settings.defaults()
    settings.camera.mock = True
    assert main.resolve_mock(_args(real=True), settings) is False


def test_falls_back_to_settings_in_development(monkeypatch) -> None:
    """Sin --mock/--real y sin empaquetar, manda camera.mock del YAML.

    Regresión: `sys.frozen` no existe en un intérprete normal (solo lo
    define PyInstaller en el ejecutable congelado) — usar el atributo
    directamente revienta con AttributeError en cuanto se ejecuta
    `uv run python main.py` sin flags, que es el caso más común en
    desarrollo. Debe pasar por `utils.paths.is_frozen()`, que sí
    contempla ese caso con `getattr(sys, "frozen", False)`.
    """
    monkeypatch.setattr(main, "is_frozen", lambda: False)
    settings = Settings.defaults()

    settings.camera.mock = True
    assert main.resolve_mock(_args(), settings) is True

    settings.camera.mock = False
    assert main.resolve_mock(_args(), settings) is False


def test_frozen_defaults_to_real_camera(monkeypatch) -> None:
    monkeypatch.setattr(main, "is_frozen", lambda: True)
    settings = Settings.defaults()
    settings.camera.mock = True

    assert main.resolve_mock(_args(), settings) is False
