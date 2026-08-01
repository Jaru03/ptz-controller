"""Tests del cliente ONVIF (sin conexión de red)."""

from pathlib import Path

from camera.client import OnvifClient, _resolve_wsdl_dir


def test_wsdl_dir_resolves_to_existing_directory() -> None:
    wsdl_dir = Path(_resolve_wsdl_dir())
    assert wsdl_dir.is_dir()
    assert (wsdl_dir / "devicemgmt.wsdl").is_file()
    assert (wsdl_dir / "media.wsdl").is_file()
    assert (wsdl_dir / "ptz.wsdl").is_file()


def test_preset_id_for_numeric_token() -> None:
    assert OnvifClient._preset_id_for_token("3") == 3
    assert OnvifClient._preset_id_for_token("255") == 255


def test_preset_id_for_string_token_is_stable() -> None:
    first = OnvifClient._preset_id_for_token("PresetEntrada")
    second = OnvifClient._preset_id_for_token("PresetEntrada")
    assert first == second
    assert OnvifClient._preset_id_for_token("PresetEntrada") != OnvifClient._preset_id_for_token("PresetPatio")


class _Preset:
    def __init__(self, token: str, name: str = "") -> None:
        self.token = token
        self.Name = name


def test_get_presets_keeps_string_tokens() -> None:
    client = OnvifClient("192.168.1.1", 80, "admin", "")
    client.profile_token = "profile-0"
    client._ptz = type(
        "FakePtz",
        (),
        {"GetPresets": lambda self, request: [_Preset("1", "Entrada"), _Preset("PresetA", "Patio")]},
    )()

    presets = client.get_presets()
    assert [p.token for p in presets] == ["1", "PresetA"]
    assert presets[0].preset_id == 1
    assert presets[1].preset_id == OnvifClient._preset_id_for_token("PresetA")
    assert client._preset_tokens[1] == "1"
    assert client._preset_tokens[presets[1].preset_id] == "PresetA"


def test_goto_preset_uses_real_token(monkeypatch) -> None:
    client = OnvifClient("192.168.1.1", 80, "admin", "")
    client.profile_token = "profile-0"
    sent: list[str] = []
    client._ptz = type(
        "FakePtz",
        (),
        {"GotoPreset": lambda self, request: sent.append(request["PresetToken"])},
    )()

    client._preset_tokens[42] = "PresetPatio"
    client.goto_preset(42)
    assert sent == ["PresetPatio"]

    client.goto_preset(99)
    assert sent == ["PresetPatio", "99"]
