"""Pruebas del módulo de versión y comprobación de actualizaciones."""

from __future__ import annotations

import urllib.error

import pytest

from models.version import UpdateResult, check_for_updates, compare_versions, parse_version


def test_parse_version_acepta_prefijo_v() -> None:
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("v10.20.30") == (10, 20, 30)
    assert parse_version("v0.2.0") == (0, 2, 0)


def test_parse_version_invalida() -> None:
    assert parse_version("hola") is None
    assert parse_version("1.2") is None
    assert parse_version("") is None


def test_compare_versions() -> None:
    assert compare_versions("0.2.0", "0.2.0") == 0
    assert compare_versions("0.1.0", "0.2.0") == -1
    assert compare_versions("1.0.0", "0.9.9") == 1


def test_check_updates_al_dia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "models.version._latest_release_json",
        lambda timeout: {"tag_name": "v0.2.0", "html_url": "https://ejemplo/rel"},
    )
    result = check_for_updates()
    assert result.ok
    assert result.up_to_date
    assert not result.available
    assert result.latest == "v0.2.0"


def test_check_updates_disponible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "models.version._latest_release_json",
        lambda timeout: {"tag_name": "v9.9.9", "html_url": "https://ejemplo/rel"},
    )
    result = check_for_updates()
    assert result.ok
    assert not result.up_to_date
    assert result.available


def test_check_updates_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(timeout: float) -> dict:
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr("models.version._latest_release_json", boom)
    result = check_for_updates()
    assert not result.ok
    assert result.error


def test_check_updates_sin_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "models.version._latest_release_json", lambda timeout: {}
    )
    result = check_for_updates()
    assert not result.ok


def test_update_result_defaults() -> None:
    result = UpdateResult()
    assert result.ok
    assert result.up_to_date
    assert not result.available
    assert result.release_url.startswith("https://github.com/")
