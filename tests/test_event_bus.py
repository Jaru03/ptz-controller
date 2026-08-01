"""Tests del bus de eventos."""

import threading
import time

import pytest

from core.event_bus import EventBus, _command_topic
from models.commands import (
    GotoPresetCommand,
    HomeCommand,
    MoveCommand,
    RenamePresetCommand,
    SetPresetCommand,
    StopCommand,
)


def test_publish_delivers_payload() -> None:
    bus = EventBus()
    received: list[object] = []

    def handler(payload: object) -> None:
        received.append(payload)

    bus.subscribe("topic.a", handler)
    bus.publish("topic.a", 42)
    assert received == [42]


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[object] = []

    def handler(payload: object) -> None:
        received.append(payload)

    bus.subscribe("topic.a", handler)
    bus.unsubscribe("topic.a", handler)
    bus.publish("topic.a", 1)
    assert received == []


def test_duplicate_handler_registered_once() -> None:
    bus = EventBus()

    def handler(payload: object) -> None:
        pass

    bus.subscribe("t", handler)
    bus.subscribe("t", handler)
    assert len(bus._handlers["t"]) == 1


def test_command_topic_mapping() -> None:
    assert _command_topic(MoveCommand()) == "command.move"
    assert _command_topic(StopCommand()) == "command.stop"
    assert _command_topic(HomeCommand()) == "command.home"
    assert _command_topic(GotoPresetCommand(1)) == "command.gotoPreset"
    assert _command_topic(SetPresetCommand(1, "X")) == "command.setPreset"
    assert _command_topic(RenamePresetCommand(1, "X")) == "command.renamePreset"


def test_send_dispatches_by_command_type() -> None:
    bus = EventBus()
    received: list[MoveCommand] = []
    bus.subscribe("command.move", received.append)
    bus.send(MoveCommand(pan=1.0, tilt=0.5))
    assert len(received) == 1
    assert received[0].pan == 1.0


def test_publish_is_thread_safe() -> None:
    bus = EventBus()
    count = 0
    lock = threading.Lock()

    def handler(_: object) -> None:
        nonlocal count
        with lock:
            count += 1

    bus.subscribe("t", handler)
    threads = [
        threading.Thread(target=lambda: [bus.publish("t", None) for _ in range(200)])
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert count == 8 * 200


def test_subscribe_rejects_non_callable() -> None:
    bus = EventBus()
    with pytest.raises(TypeError):
        bus.subscribe("t", "not-a-callable")  # type: ignore[arg-type]


def test_clear_removes_all_handlers() -> None:
    bus = EventBus()
    bus.subscribe("t", lambda _: None)
    bus.clear()
    assert not bus.has_subscribers("t")


def test_threaded_subscribe_while_publishing() -> None:
    bus = EventBus()
    stop = time.monotonic() + 0.1

    def pusher() -> None:
        while time.monotonic() < stop:
            bus.publish("t", None)

    def subscriber() -> None:
        bus.subscribe("t", lambda _: None)
        bus.unsubscribe("t", lambda _: None)

    threads = [threading.Thread(target=pusher)] + [
        threading.Thread(target=subscriber) for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
