"""Capa de cámara: interfaces PTZ, cliente ONVIF, simulador y discovery."""

from camera.client import CameraError, OnvifClient
from camera.discovery import DiscoveredDevice, discover_devices
from camera.mock_ptz import MockPTZController
from camera.ptz_controller import OnvifPTZController, PTZController

__all__ = [
    "CameraError",
    "DiscoveredDevice",
    "MockPTZController",
    "OnvifClient",
    "OnvifPTZController",
    "PTZController",
    "discover_devices",
]
