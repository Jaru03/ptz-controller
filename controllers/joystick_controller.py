"""Control de la cámara mediante joystick/mando (pygame).

Detecta automáticamente cualquier mando SDL (DualShock 4/5, DualSense,
Xbox, USB genéricos) gestionando el hotplug. El movimiento es
proporcional al stick (con deadzone re-escalada) y solo se publican
comandos cuando la dirección cambia (vía ``MovementState``).

El mapeo por defecto se define en la configuración y puede adaptarse por
mando con ``device_overrides``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pygame

from config.settings import JoystickConfig
from controllers.base import InputController, MovementState, PresetRegistry
from controllers.pygame_events import PyGameEventBroker
from core.event_bus import EventBus
from models.commands import GotoPresetCommand, HomeCommand, SetSpeedCommand
from utils.logger import get_logger

log = get_logger(__name__)

JOYSTICK_TOPIC = "input.joystick"


class JoystickController(InputController):
    """Controlador de un mando con movimiento proporcional."""

    def __init__(
        self,
        config: JoystickConfig,
        broker: PyGameEventBroker,
        movement: MovementState,
        bus: EventBus,
        speed_step: float = 0.1,
        presets: PresetRegistry | None = None,
    ) -> None:
        self._config = config
        self._broker = broker
        self._movement = movement
        self._bus = bus
        self._speed_step = speed_step
        self._presets = presets if presets is not None else PresetRegistry(bus)
        self._axes: dict[int, dict[int, float]] = {}
        self._hats: dict[int, dict[int, tuple[int, int]]] = {}
        self._started = False

    @property
    def name(self) -> str:
        return "joystick"

    @property
    def is_active(self) -> bool:
        return bool(self._axes)

    # -- Ciclo de vida ----------------------------------------------------

    def start(self) -> None:
        broker = self._broker
        broker.subscribe(pygame.JOYAXISMOTION, self._on_axis_motion)
        broker.subscribe(pygame.JOYHATMOTION, self._on_hat_motion)
        broker.subscribe(pygame.JOYBUTTONDOWN, self._on_button_down)
        broker.subscribe(pygame.JOYBUTTONUP, self._on_button_up)
        broker.subscribe(pygame.JOYDEVICEADDED, self._on_device_added)
        broker.subscribe(pygame.JOYDEVICEREMOVED, self._on_device_removed)
        self._started = True
        for instance_id in broker.instance_ids:
            self._init_device(instance_id)
        self._publish_device_status()
        log.info("Controlador de joystick activo")

    def stop(self) -> None:
        if not self._started:
            return
        broker = self._broker
        broker.unsubscribe(pygame.JOYAXISMOTION, self._on_axis_motion)
        broker.unsubscribe(pygame.JOYHATMOTION, self._on_hat_motion)
        broker.unsubscribe(pygame.JOYBUTTONDOWN, self._on_button_down)
        broker.unsubscribe(pygame.JOYBUTTONUP, self._on_button_up)
        broker.unsubscribe(pygame.JOYDEVICEADDED, self._on_device_added)
        broker.unsubscribe(pygame.JOYDEVICEREMOVED, self._on_device_removed)
        self._started = False
        self._axes.clear()
        self._hats.clear()
        self._publish_device_status()

    # -- Handlers de eventos ---------------------------------------------

    def _on_axis_motion(self, event: Any) -> None:
        instance_id = event.instance_id
        self._axes.setdefault(instance_id, {})[event.axis] = event.value
        self._recompute(instance_id)

    def _on_hat_motion(self, event: Any) -> None:
        instance_id = event.instance_id
        self._hats.setdefault(instance_id, {})[event.hat] = tuple(event.value)
        self._recompute(instance_id)

    def _on_button_down(self, event: Any) -> None:
        instance_id = event.instance_id
        config = self._config_for(instance_id)
        button = event.button

        if button == config.home_button:
            self._bus.send(HomeCommand())
            log.info("Joystick: home (botón %s)", button)
        elif button == config.speed_up_button:
            self._change_speed(+self._speed_step)
        elif button == config.speed_down_button:
            self._change_speed(-self._speed_step)
        elif button in config.preset_buttons:
            index = config.preset_buttons.index(button)
            token = self._presets.token_at(index)
            if token is None:
                log.info("Joystick: no hay preset en la posición %s", index + 1)
                return
            self._bus.send(GotoPresetCommand(token))
            log.info("Joystick: GotoPreset %s (botón %s)", token, button)

    def _on_button_up(self, event: Any) -> None:
        pass  # las acciones de botón son instantáneas (al pulsar)

    def _on_device_added(self, event: Any) -> None:
        instance_id = getattr(event, "instance_id", getattr(event, "device_index", None))
        if instance_id is None:
            return
        self._init_device(instance_id)
        self._recompute(instance_id)
        self._publish_device_status()

    def _on_device_removed(self, event: Any) -> None:
        instance_id = getattr(event, "instance_id", None)
        if instance_id is None:
            return
        self._axes.pop(instance_id, None)
        self._hats.pop(instance_id, None)
        self._publish_device_status()

    # -- Lógica -----------------------------------------------------------

    def _init_device(self, instance_id: int) -> None:
        joystick = self._broker.joystick_by_instance(instance_id)
        if joystick is None:
            return
        axes: dict[int, float] = {
            index: joystick.get_axis(index)
            for index in range(joystick.get_numaxes())
        }
        self._axes[instance_id] = axes
        self._hats[instance_id] = {}
        log.info("Mando detectado: %s", joystick.get_name())

    def _recompute(self, instance_id: int) -> None:
        config = self._config_for(instance_id)
        axes = self._axes.get(instance_id, {})

        pan = axes.get(config.pan_axis, 0.0)
        tilt = axes.get(config.tilt_axis, 0.0)
        if config.invert_tilt:
            tilt = -tilt

        zoom_in = axes.get(config.zoom_in_axis, 0.0)
        zoom_out = axes.get(config.zoom_out_axis, 0.0)
        zoom = zoom_in - zoom_out

        hats = self._hats.get(instance_id, {})
        for hat_x, hat_y in hats.values():
            pan += hat_x
            tilt += hat_y

        self._movement.update(pan, tilt, zoom)

    def _change_speed(self, delta: float) -> None:
        new_speed = max(0.05, min(1.0, self._movement.speed + delta))
        self._movement.set_speed(new_speed)
        self._bus.send(SetSpeedCommand(new_speed))
        log.info("Joystick: velocidad %.2f", new_speed)

    def _config_for(self, instance_id: int) -> JoystickConfig:
        joystick = self._broker.joystick_by_instance(instance_id)
        name = joystick.get_name() if joystick is not None else ""
        guid = joystick.get_guid() if joystick is not None else ""
        for pattern, overrides in self._config.device_overrides.items():
            if pattern.lower() in name.lower() or pattern.lower() in guid.lower():
                return JoystickConfig(
                    **{
                        **dataclasses.asdict(self._config),
                        **overrides,
                    }
                )
        return self._config

    def _publish_device_status(self) -> None:
        names = []
        for instance_id in self._axes:
            joystick = self._broker.joystick_by_instance(instance_id)
            if joystick is not None:
                names.append(joystick.get_name())
        if names:
            self._bus.publish(JOYSTICK_TOPIC, {"connected": True, "name": ", ".join(names)})
        else:
            self._bus.publish(JOYSTICK_TOPIC, {"connected": False, "name": ""})
