"""Sondeo periódico de estado, sustituto del QTimer de MainWindow.

``gui/main_window.py`` arranca un ``QTimer`` en ``MainWindow.__init__``
(cada ``poll_interval_ms``, mínimo 30ms) que llama a ``poll_status()``
para republicar ``ptz.status``. pywebview no tiene un timer de GUI
equivalente (no hay bucle de eventos Qt), así que aquí se reemplaza por
un hilo daemon simple.
"""

from __future__ import annotations

import threading
from typing import Callable

IntervalMs = int | Callable[[], int]


class StatusPoller:
    """Llama a ``job()`` cada ``interval_ms`` milisegundos en un hilo daemon.

    ``interval_ms`` acepta un entero fijo o una función sin argumentos que
    se evalúa en cada ciclo: en el flujo web, a diferencia del diálogo
    modal de Qt, no hay un punto único "tras confirmar conexión, antes de
    crear la ventana" donde fijar el intervalo según modo mock/real — el
    modo puede cambiar mientras la ventana ya está abierta (vía
    ``Api.apply_connection_settings``). Pasando una función se recalcula
    en cada vuelta sin necesidad de reiniciar el poller.
    """

    def __init__(self, job: Callable[[], None], interval_ms: IntervalMs) -> None:
        self._job = job
        self._interval_ms = interval_ms
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _current_interval_s(self) -> float:
        value = self._interval_ms() if callable(self._interval_ms) else self._interval_ms
        return max(30, value) / 1000.0

    def _run(self) -> None:
        while not self._stop_event.wait(self._current_interval_s()):
            self._job()
