"""Tests del worker que ejecuta los comandos de cámara fuera de la GUI."""

import threading
import time

from core.command_worker import CommandWorker


def _worker() -> CommandWorker:
    worker = CommandWorker(name="test-worker")
    worker.start()
    return worker


def test_jobs_run_in_a_background_thread() -> None:
    worker = _worker()
    done = threading.Event()
    threads: list[str] = []
    worker.submit(lambda: (threads.append(threading.current_thread().name), done.set()))
    assert done.wait(1.0)
    assert threads == ["test-worker"]
    worker.stop()


def test_jobs_keep_their_order() -> None:
    worker = _worker()
    order: list[int] = []
    done = threading.Event()
    for value in range(5):
        worker.submit(lambda value=value: order.append(value))
    worker.submit(done.set)
    assert done.wait(1.0)
    assert order == [0, 1, 2, 3, 4]
    worker.stop()


def test_same_key_replaces_the_pending_job() -> None:
    worker = CommandWorker(name="test-worker")
    executed: list[str] = []
    # Sin arrancar el hilo, los trabajos se acumulan y se puede observar
    # la fusión: solo debe sobrevivir el último de cada clave.
    worker._running = True
    worker.submit(lambda: executed.append("move-1"), key="move")
    worker.submit(lambda: executed.append("move-2"), key="move")
    worker.submit(lambda: executed.append("preset"))
    worker.submit(lambda: executed.append("move-3"), key="move")
    assert worker.pending == 2

    worker.start()
    time.sleep(0.2)
    assert executed == ["preset", "move-3"]
    worker.stop()


def test_stop_cancels_the_pending_move() -> None:
    worker = CommandWorker(name="test-worker")
    executed: list[str] = []
    worker._running = True
    worker.submit(lambda: executed.append("move"), key="move")
    worker.submit(lambda: executed.append("stop"), key="stop", cancels=("move",))
    assert worker.pending == 1

    worker.start()
    time.sleep(0.2)
    assert executed == ["stop"]
    worker.stop()


def test_a_failing_job_does_not_kill_the_worker() -> None:
    worker = _worker()
    done = threading.Event()

    def boom() -> None:
        raise RuntimeError("fallo simulado")

    worker.submit(boom)
    worker.submit(done.set)
    assert done.wait(1.0)
    worker.stop()


def test_submit_is_ignored_once_stopped() -> None:
    worker = _worker()
    worker.stop()
    executed: list[str] = []
    worker.submit(lambda: executed.append("tarde"))
    time.sleep(0.1)
    assert executed == []
