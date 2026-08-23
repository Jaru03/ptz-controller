"""Tests del cliente ONVIF (sin conexión de red)."""

from pathlib import Path

from camera.client import OnvifClient, _resolve_wsdl_dir


def test_wsdl_dir_resolves_to_existing_directory() -> None:
    wsdl_dir = Path(_resolve_wsdl_dir())
    assert wsdl_dir.is_dir()
    assert (wsdl_dir / "devicemgmt.wsdl").is_file()
    assert (wsdl_dir / "media.wsdl").is_file()
    assert (wsdl_dir / "ptz.wsdl").is_file()


class _Preset:
    def __init__(self, token: str, name: str = "") -> None:
        self.token = token
        self.Name = name


def _client_with_ptz(**methods) -> OnvifClient:
    """Cliente con un servicio PTZ falso (sin red)."""
    client = OnvifClient("192.168.1.1", 80, "admin", "")
    client.profile_token = "profile-0"
    client._ptz = type("FakePtz", (), methods)()
    return client


def test_get_presets_keeps_string_tokens() -> None:
    client = _client_with_ptz(
        GetPresets=lambda self, request: [
            _Preset("1", "Entrada"),
            _Preset("PresetA", "Patio"),
        ]
    )

    presets = client.get_presets()
    assert [p.token for p in presets] == ["1", "PresetA"]
    assert [p.name for p in presets] == ["Entrada", "Patio"]


def test_get_presets_names_unnamed_presets() -> None:
    client = _client_with_ptz(
        GetPresets=lambda self, request: [_Preset("PresetB", "")]
    )
    assert client.get_presets()[0].name == "Preset PresetB"


def test_goto_preset_sends_token_verbatim() -> None:
    sent: list[str] = []
    client = _client_with_ptz(
        GotoPreset=lambda self, request: sent.append(request["PresetToken"])
    )

    client.goto_preset("PresetPatio")
    client.goto_preset("99")
    assert sent == ["PresetPatio", "99"]


def test_set_preset_without_token_lets_camera_assign() -> None:
    sent: list[dict] = []
    client = _client_with_ptz(SetPreset=lambda self, request: sent.append(request))

    client.set_preset("", "Nueva escena")
    assert "PresetToken" not in sent[0]
    assert sent[0]["Name"] == "Nueva escena"

    client.set_preset("7")
    assert sent[1]["PresetToken"] == "7"


def test_continuous_move_sends_only_active_axes() -> None:
    sent: list[dict] = []
    client = _client_with_ptz(
        ContinuousMove=lambda self, request: sent.append(request["Velocity"]),
        Stop=lambda self, request: None,
    )

    client.continuous_move(0.0, 0.0, 1.0, 1.0)
    assert sent[0] == {"Zoom": {"x": 1.0}}

    client.continuous_move(1.0, 0.0, 0.0, 0.5)
    assert sent[1] == {"PanTilt": {"x": 0.5, "y": 0.0}}


def test_continuous_move_stops_the_axis_that_became_inactive() -> None:
    stops: list[dict] = []
    client = _client_with_ptz(
        ContinuousMove=lambda self, request: None,
        Stop=lambda self, request: stops.append(request),
    )

    client.continuous_move(0.0, 0.0, 1.0, 1.0)   # solo zoom
    assert stops == []

    client.continuous_move(1.0, 0.0, 0.0, 1.0)   # el zoom deja de enviarse
    assert stops[-1]["Zoom"] is True
    assert stops[-1]["PanTilt"] is False


def test_stop_sends_one_request_per_axis_when_both_are_requested() -> None:
    """Algunas cámaras solo atienden un eje en un Stop combinado."""
    stops: list[dict] = []
    client = _client_with_ptz(Stop=lambda self, request: stops.append(request))

    client.stop()  # ambos ejes (por defecto)

    assert stops == [
        {"ProfileToken": "profile-0", "PanTilt": True, "Zoom": False},
        {"ProfileToken": "profile-0", "PanTilt": False, "Zoom": True},
    ]


def test_stop_sends_a_single_request_for_one_axis() -> None:
    stops: list[dict] = []
    client = _client_with_ptz(Stop=lambda self, request: stops.append(request))

    client.stop(pan_tilt=False, zoom=True)

    assert stops == [{"ProfileToken": "profile-0", "PanTilt": False, "Zoom": True}]


def test_relative_move_omits_empty_axes() -> None:
    sent: list[dict] = []
    client = _client_with_ptz(
        RelativeMove=lambda self, request: sent.append(request["Translation"])
    )

    client.relative_move(0.0, 0.0, 0.05)
    assert sent[0] == {"Zoom": {"x": 0.05}}

    client.relative_move(0.0, 0.0, 0.0)
    assert len(sent) == 1  # nada que mover: no se envía petición
