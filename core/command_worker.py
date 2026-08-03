"""Ejecución de trabajos PTZ en un hilo propio.

Las llamadas ONVIF son peticiones SOAP por red: pueden tardar cientos de
milisegundos. Como el ``EventBus`` invoca a los handlers en el hilo del
publicador, ejecutarlas directamente bloquea el hilo de la GUI (que es
quien recibe las teclas y quien pinta la vista previa de vídeo).

``CommandWorker`` recibe esos trabajos y los ejecuta en serie en un hilo
aparte. Además **fusiona** los trabajos repetidos mediante una clave: un
movimiento pendiente es sustituido por el siguiente en lugar de
acumularse, de modo que la cola nunca crece aunque la cámara responda más
despacio de lo que se pulsa el teclado (y el ``Stop`` no llega tarde).
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Callable, Iterable

from utils.logger import get_logger

log = get_logger(__name__)

Job = Callable[[], None]


class CommandWorker:
    """Cola de trabajos con fusión por clave, ejecutados en un hilo."""

    def __init__(self, name: str = "ptz-worker") -> None:
        self._name = name
        self._pending: deque[tuple[str | None, Job]] = deque()
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._running = False

    # -- Ciclo de vida ----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Detiene el hilo tras terminar el trabajo en curso."""
        thread = self._thread
        with self._condition:
            self._running = False
            self._pending.clear()
            self._condition.notify_all()
        self._thread = None
        if thread is not None:
            thread.join(timeout)

    # -- Encolado ---------------------------------------------------------

    def submit(
        self,
        job: Job,
        key: str | None = None,
        cancels: Iterable[str] = (),
    ) -> None:
        """Encola un trabajo.

        Args:
            job: función sin argumentos a ejecutar en el hilo del worker.
            key: si se indica, sustituye al trabajo pendiente con la misma
                clave (p. ej. 'move': solo interesa el último).
            cancels: claves cuyos trabajos pendientes se descartan (un
                ``Stop`` invalida los movimientos que aún no han salido).
        """
        with self._condition:
            if not self._running:
                return
            discarded = set(cancels)
            if key is not None:
                discarded.add(key)
            if discarded:
                self._pending = deque(
                    item for item in self._pending if item[0] not in discarded
                )
            self._pending.append((key, job))
            self._condition.notify()

    @property
    def pending(self) -> int:
        with self._condition:
            return len(self._pending)

    # -- Internos ---------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._running and not self._pending:
                    self._condition.wait()
                if not self._running:
                    return
                _, job = self._pending.popleft()
            try:
                job()
            except Exception:  # noqa: BLE001 - un trabajo no puede matar el hilo
                log.exception("Error al ejecutar un trabajo en %s", self._name)
