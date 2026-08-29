"""Tests de gui_web/serialize.py::to_json_safe."""

from gui_web.serialize import to_json_safe
from models.commands import PresetInfo, PTZStatus, SpeedLevel


def test_plain_values_pass_through() -> None:
    assert to_json_safe("hola") == "hola"
    assert to_json_safe(3.5) == 3.5
    assert to_json_safe(True) is True
    assert to_json_safe(None) is None


def test_dataclass_becomes_dict() -> None:
    preset = PresetInfo(token="1", name="Entrada")
    assert to_json_safe(preset) == {"token": "1", "name": "Entrada"}


def test_nested_dataclass_with_tuple_of_dataclasses() -> None:
    status = PTZStatus(
        connected=True,
        pan=0.1,
        tilt=-0.2,
        zoom=0.0,
        speed=0.5,
        device_name="Cam1",
        ip="10.0.0.5",
        input_active="keyboard",
        presets=(PresetInfo(token="1", name="Entrada"), PresetInfo(token="2")),
    )

    result = to_json_safe(status)

    assert result["connected"] is True
    assert result["presets"] == [
        {"token": "1", "name": "Entrada"},
        {"token": "2", "name": ""},
    ]


def test_enum_becomes_its_value() -> None:
    assert to_json_safe(SpeedLevel.FAST) == 3


def test_list_and_dict_are_recursed() -> None:
    payload = {"items": [PresetInfo(token="1", name="A"), {"raw": 1}]}
    assert to_json_safe(payload) == {"items": [{"token": "1", "name": "A"}, {"raw": 1}]}
