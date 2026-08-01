"""Tests del cliente ONVIF (sin conexión de red)."""

from pathlib import Path

from camera.client import _resolve_wsdl_dir


def test_wsdl_dir_resolves_to_existing_directory() -> None:
    wsdl_dir = Path(_resolve_wsdl_dir())
    assert wsdl_dir.is_dir()
    assert (wsdl_dir / "devicemgmt.wsdl").is_file()
    assert (wsdl_dir / "media.wsdl").is_file()
    assert (wsdl_dir / "ptz.wsdl").is_file()
