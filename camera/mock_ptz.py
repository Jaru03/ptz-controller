"""Controlador PTZ simulado (Mock) para desarrollo sin hardware.

Implementa la misma interfaz que ``PTZController`` pero sobre un estado
virtual: mantiene posición pan/tilt/zoom y velocidad, integra el
movimiento en un hilo a una tasa fija y notifica los cambios a un
callback (que la GUI usa para redibujar la vista de la cámara).

El estado virtual se limita al rango -1..1 (coordenadas normalizadas).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from models.commands import PTZStatus, PresetInfo
from utils.logger import get_logger

from camera.ptz_controller import PTZController

log = get_logger(__name__)

StatusCallback = Callable[[PTZStatus], None]


class MockPTZController(PTZController):
    """Simulación de una cámara PTZ.

    La integración de posición es determinista: ``_advance(dt)`` aplica
    ``pos += velocidad * dt``, por lo que es comprobable en tests sin
    depender del hilo.
    """

    def __init__(
        self,
        ip: str = "192.168.1.100",
        port: int = 80,
        username: str = "admin",
        password: str = "",
        tick_rate: int = 30,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self._ip = ip
        self._port = port
        self._username = username
        self._password = password
        self._tick_rate = tick_rate
        self._dt = 1.0 / max(1, tick_rate)
        self._status_callback = status_callback

        self._pan = 0.0
        self._tilt = 0.0
        self._zoom = 0.0
        self._vpan = 0.0
        self._vtilt = 0.0
        self._vzoom = 0.0
        self._speed = 0.5
        self._presets: dict[int, tuple[float, float, float, str]] = {}

        self._connected = False
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._lock = threading.RLock()

    # -- Estado / ciclo de vida ------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    def set_status_callback(self, callback: StatusCallback | None) -> None:
        """Registra el callback que recibe instantáneas de estado."""
        self._status_callback = callback

    def connect(self) -> None:
        with self._lock:
            self._connected = True
            self._pan = self._tilt = self._zoom = 0.0
            self._vpan = self._vtilt = self._vzoom = 0.0
            self._running.set()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run,
                name="mock-ptz",
                daemon=True,
            )
            self._thread.start()
        log.info("Cámara simulada conectada (%s:%s)", self._ip, self._port)
        self._notify()

    def disconnect(self) -> None:
        self._running.clear()
        with self._lock:
            self._connected = False
            self._vpan = self._vtilt = self._vzoom = 0.0
        log.info("Cámara simulada desconectada")
        self._notify()

    def _run(self) -> None:
        while self._running.is_set():
            self._advance(self._dt)
            time.sleep(self._dt)

    def _advance(self, dt: float) -> None:
        """Integra la posición virtual un paso ``dt`` (segundos)."""
        with self._lock:
            self._pan = _clamp(self._pan + self._vpan * dt)
            self._tilt = _clamp(self._tilt + self._vtilt * dt)
            self._zoom = _clamp(self._zoom + self._vzoom * dt)
        self._notify()

    # -- Interfaz PTZController ------------------------------------------

    def move(self, pan: float, tilt: float, zoom: float, speed: float) -> None:
        with self._lock:
            if not self._connected:
                log.warning("move() ignorado: cámara simulada no conectada")
                return
            self._speed = _clamp(speed, 0.0, 1.0)
            self._vpan = _clamp(pan * self._speed)
            self._vtilt = _clamp(tilt * self._speed)
            self._vzoom = _clamp(zoom * self._speed)
        self._notify()

    def stop(self) -> None:
        with self._lock:
            self._vpan = self._vtilt = self._vzoom = 0.0
        self._notify()

    def home(self) -> None:
        with self._lock:
            self._pan = self._tilt = self._zoom = 0.0
            self._vpan = self._vtilt = self._vzoom = 0.0
        log.info("Home ejecutado en cámara simulada")
        self._notify()

    def goto_preset(self, preset_id: int) -> None:
        with self._lock:
            if preset_id not in self._presets:
                log.warning("Preset %s no existe en la cámara simulada", preset_id)
                return
            pan, tilt, zoom, _ = self._presets[preset_id]
            self._pan, self._tilt, self._zoom = pan, tilt, zoom
            self._vpan = self._vtilt = self._vzoom = 0.0
        log.info("GotoPreset %s ejecutado en cámara simulada", preset_id)
        self._notify()

    def set_preset(self, preset_id: int, name: str = "") -> None:
        with self._lock:
            self._presets[preset_id] = (self._pan, self._tilt, self._zoom, name)
        log.info(
            "SetPreset %s guardado en cámara simulada%s",
            preset_id,
            f" (nombre: {name})" if name else "",
        )
        self._notify()

    def rename_preset(self, preset_id: int, name: str) -> None:
        with self._lock:
            if preset_id not in self._presets:
                log.warning("Preset %s no existe en la cámara simulada", preset_id)
                return
            pan, tilt, zoom, _ = self._presets[preset_id]
            self._presets[preset_id] = (pan, tilt, zoom, name)
        log.info("Preset %s renombrado a '%s' en cámara simulada", preset_id, name)
        self._notify()

    def remove_preset(self, preset_id: int) -> None:
        with self._lock:
            removed = self._presets.pop(preset_id, None)
        if removed is None:
            log.warning("Preset %s no existe en la cámara simulada", preset_id)
            return
        log.info("RemovePreset %s eliminado en cámara simulada", preset_id)
        self._notify()

    def list_presets(self) -> list[PresetInfo]:
        with self._lock:
            return [
                PresetInfo(
                    preset_id=preset_id,
                    name=name or f"Preset {preset_id}",
                    token=str(preset_id),
                )
                for preset_id, (*_, name) in sorted(self._presets.items())
            ]

    def get_status(self) -> PTZStatus:
        with self._lock:
            return self._build_status()

    # -- Internos ---------------------------------------------------------

    def _build_status(self) -> PTZStatus:
        presets = tuple(
            PresetInfo(
                preset_id=preset_id,
                name=name or f"Preset {preset_id}",
                token=str(preset_id),
            )
            for preset_id, (*_, name) in sorted(self._presets.items())
        )
        return PTZStatus(
            connected=self._connected,
            pan=self._pan,
            tilt=self._tilt,
            zoom=self._zoom,
            speed=self._speed,
            device_name="Cámara simulada (Mock)",
            ip=self._ip,
            presets=presets,
        )

    def _notify(self) -> None:
        callback = self._status_callback
        if callback is not None:
            try:
                callback(self.get_status())
            except Exception:  # noqa: BLE001 - nunca romper el hilo por la GUI
                log.exception("Error al notificar el estado de la cámara simulada")


def _clamp(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))
