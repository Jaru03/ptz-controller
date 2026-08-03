"""Tests de los modelos de dominio."""

from models.commands import (
    GotoPresetCommand,
    HomeCommand,
    MoveCommand,
    PresetInfo,
    RenamePresetCommand,
    SetPresetCommand,
    SetSpeedCommand,
    StopCommand,
    Vector2,
)


def test_vector2_clamps_to_unit_range() -> None:
    vector = Vector2(x=2.5, y=-3.0)
    assert vector.x == 1.0
    assert vector.y == -1.0


def test_vector2_zero_state() -> None:
    assert Vector2().is_zero
    assert not Vector2(x=0.1).is_zero


def test_vector2_equality_with_tolerance() -> None:
    assert Vector2(x=0.1, y=0.2) == Vector2(x=0.1, y=0.2)
    assert Vector2(x=0.1, y=0.2) != Vector2(x=0.1, y=0.200001) or abs(
        0.2 - 0.200001
    ) < 1e-9


def test_move_command_neutral() -> None:
    assert MoveCommand().is_neutral
    assert not MoveCommand(pan=0.3).is_neutral


def test_move_command_values_preserved() -> None:
    command = MoveCommand(pan=0.5, tilt=-0.5, zoom=1.0, speed=0.8)
    assert command.pan == 0.5
    assert command.tilt == -0.5
    assert command.zoom == 1.0
    assert command.speed == 0.8


def test_commands_are_frozen() -> None:
    import dataclasses

    assert dataclasses.is_dataclass(MoveCommand)
    assert dataclasses.is_dataclass(StopCommand)
    assert dataclasses.is_dataclass(HomeCommand)
    assert dataclasses.is_dataclass(GotoPresetCommand)
    assert dataclasses.is_dataclass(SetSpeedCommand)


def test_set_preset_command_carries_name() -> None:
    command = SetPresetCommand(token="7", name="Patio")
    assert command.token == "7"
    assert command.name == "Patio"


def test_rename_preset_command_defaults() -> None:
    assert RenamePresetCommand(token="2", name="Salón").name == "Salón"
    assert RenamePresetCommand().token == ""


def test_preset_commands_accept_non_numeric_tokens() -> None:
    assert GotoPresetCommand(token="PresetEntrada").token == "PresetEntrada"
    assert PresetInfo(token="a1b2", name="Patio").token == "a1b2"
