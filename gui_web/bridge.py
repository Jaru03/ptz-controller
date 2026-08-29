"""Puente de eventos Python -> JS. Equivalente a QtEventBridge.

``gui/main_window.py::QtEventBridge`` suscribe topics del ``EventBus`` a
señales Qt; Qt encola automáticamente la emisión en el hilo de la GUI
cuando el emisor está en otro hilo (AutoConnection). pywebview no tiene
ese encolado automático, pero ``Window.evaluate_js`` está documentado como
seguro de llamar desde hilos en segundo plano — así que aquí no hace
falta ninguna cola propia, solo despachar cada evento del bus a
``window.__ptzBridge.dispatch(topic, payload)`` (frontend/src/lib/bridge.ts).

Sin throttling adicional: ``ptz.status`` ya tiene cadencia fija por
``StatusPoller``, ``input.*`` son eventos de cambio (no por tick), y el
vídeo no pasa por este canal (ver gui_web/video_server.py, Fase 3).
"""

from __future__ import annotations

import json
from typing import Callable

from core.event_bus import EventBus
from gui_web.serialize import to_json_safe
from utils.logger import get_logger

log = get_logger(__name__)

_BRIDGED_TOPICS = (
    "ptz.status",
    "input.keyboard",
    "input.joystick",
    "command.setSpeed",
    "ptz.presets",
    "ptz.stream",
    "gui.discovery",
    "gui.error",
    "gui.streamState",
    "command.quit",
)


class EventBridge:
    """Reenvía topics del bus a la ventana pywebview vía ``evaluate_js``."""

    def __init__(self, bus: EventBus, get_window: Callable[[], object | None]) -> None:
        self._get_window = get_window
        for topic in _BRIDGED_TOPICS:
            bus.subscribe(topic, self._make_handler(topic))

    def _make_handler(self, topic: str) -> Callable[[object], None]:
        def handler(payload: object) -> None:
            self._emit(topic, payload)

        return handler

    def _emit(self, topic: str, payload: object) -> None:
        window = self._get_window()
        if window is None:
            return
        script = (
            "window.__ptzBridge && window.__ptzBridge.dispatch("
            f"{json.dumps(topic)}, {json.dumps(to_json_safe(payload))})"
        )
        try:
            window.evaluate_js(script)
        except Exception:  # noqa: BLE001 - la ventana puede estar cerrándose
            log.debug("evaluate_js falló para %s (¿ventana cerrándose?)", topic, exc_info=True)
