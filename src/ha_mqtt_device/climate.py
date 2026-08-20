"""Climate entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.numeric_value import NumericValue
from ha_mqtt_device.values.str_value import StrValue

__all__ = ["Climate"]

logger = logging.getLogger(__name__)

#: ``event_type`` of events built from messages on the temperature command topic.
_EVENT_TYPE_TEMPERATURE = "temperature"

#: ``event_type`` of events built from messages on the mode command topic.
_EVENT_TYPE_MODE = "mode"

#: Discovery config field that names the temperature command topic.
_TOPIC_TYPE_TEMPERATURE = "temperature_command_topic"

#: Discovery config field that names the mode command topic.
_TOPIC_TYPE_MODE = "mode_command_topic"


@dataclass
class Climate(Entity):
    """A climate entity (thermostat) belonging to a device.

    A climate entity has six MQTT topics. The device publishes the current
    temperature to the current-temperature topic (``~/<unique_id>/current_temperature``)
    with :meth:`set_current_temperature`, the target temperature to the state
    topic (``~/<unique_id>/temperature``) with :meth:`set_target_temperature`,
    the HVAC mode to the mode state topic (``~/<unique_id>/mode``) with
    :meth:`set_mode`, and the current action to the action topic
    (``~/<unique_id>/action``) with :meth:`set_action`. It receives commands
    from Home Assistant on the temperature command topic
    (``~/<unique_id>/temperature_command``) and the mode command topic
    (``~/<unique_id>/mode_command``). Registering an async callback with
    :meth:`on_event` subscribes to both and delivers every message as an
    :class:`~ha_mqtt_device.event.Event`::

        thermostat = Climate(
            unique_id="thermostat",
            name="Thermostat",
            modes=["off", "heat", "cool", "auto"],
            temperature_unit="C",
        )
        device = Device(provider, info, entities=[thermostat])

        async def on_command(event: Event) -> None:
            if event.event_type == "temperature" and event.state is not None:
                # event.state is the requested temperature, e.g. "21.5".
                await thermostat.set_target_temperature(float(event.state))
            elif event.event_type == "mode":
                # event.state is the requested mode, e.g. "heat".
                await thermostat.set_mode(event.state)

        async with device:
            await thermostat.on_event(on_command)
            await thermostat.set_target_temperature(21.5)

    Unlike :meth:`set_target_temperature` and :meth:`set_mode`, commands
    received from Home Assistant do not change the climate by themselves — the
    application decides what to do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        modes: HVAC modes the climate supports (``modes``), for example
            ``["off", "heat", "cool", "auto"]``. Omitted from the discovery
            config when unset; when set, :meth:`set_mode` rejects modes not in
            the list.
        temperature_unit: Unit of the target temperature (``temp_unit``),
            either ``"C"`` or ``"F"``. Omitted when unset.
        min_temp: Minimum target temperature (``min_temp``). Omitted when
            unset.
        max_temp: Maximum target temperature (``max_temp``). Omitted when
            unset.
        temp_step: Step size of the target temperature (``temp_step``).
            Omitted when unset.
        precision: Precision of the temperature (``prec``), for example
            ``0.5``. Omitted when unset.
        initial: Initial target temperature (``init``) shown until the first
            state update arrives. Omitted when unset.
        mode_opt: Whether Home Assistant should assume mode commands take
            effect immediately (``mode_opt``). Defaults to ``False``.
        temp_opt: Whether Home Assistant should assume temperature commands
            take effect immediately (``temp_opt``). Defaults to ``False``.
    """

    component = "climate"

    modes: list[str] | None = None
    temperature_unit: str | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    temp_step: float | None = None
    precision: float | None = None
    initial: float | None = None
    mode_opt: bool = False
    temp_opt: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscriptions have been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)
    _current_temperature_value: Entity.StateValue[float] = field(
        init=False, repr=False, compare=False
    )
    _target_temperature_value: Entity.StateValue[float] = field(
        init=False, repr=False, compare=False
    )
    _mode_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)
    _action_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._current_temperature_value = self._make_persistent_state(
            NumericValue(), "state/current_temperature"
        )
        self._target_temperature_value = self._make_persistent_state(
            NumericValue(), "state/temperature"
        )
        self._mode_value = self._make_persistent_state(StrValue(), "state/mode")
        self._action_value = self._make_momentary_state(StrValue(), "state/action")

    @property
    def current_temperature_topic(self) -> str:
        """Current-temperature topic, ``~/<unique_id>/current_temperature``."""
        return Entity.state_topic_for(self.unique_id, "current_temperature")

    @property
    def temperature_state_topic(self) -> str:
        """Target-temperature state topic, ``~/<unique_id>/temperature``."""
        return Entity.state_topic_for(self.unique_id, "temperature")

    @property
    def temperature_command_topic(self) -> str:
        """Target-temperature command topic, ``~/<unique_id>/temperature_command``."""
        return Entity.command_topic_for(self.unique_id, "temperature")

    @property
    def mode_state_topic(self) -> str:
        """Mode state topic, ``~/<unique_id>/mode``."""
        return Entity.state_topic_for(self.unique_id, "mode")

    @property
    def mode_command_topic(self) -> str:
        """Mode command topic, ``~/<unique_id>/mode_command``."""
        return Entity.command_topic_for(self.unique_id, "mode")

    @property
    def action_topic(self) -> str:
        """Action topic, ``~/<unique_id>/action``."""
        return Entity.state_topic_for(self.unique_id, "action")

    async def set_current_temperature(self, temperature: float) -> None:
        """Publish the current temperature.

        ``temperature`` is converted to a string and published to the
        current-temperature topic (``~/<unique_id>/current_temperature``).
        Consecutive unchanged temperatures are not republished.
        Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topics do.

        Raises:
            RuntimeError: If the climate is not bound to a device.
            Exception: If the message could not be published.
        """
        self._validate_finite(temperature, "temperature")
        await self._current_temperature_value.set_value(temperature)

    async def set_target_temperature(self, temperature: float) -> None:
        """Publish the target temperature.

        ``temperature`` is converted to a string and published to the state
        topic (``~/<unique_id>/temperature``), for example ``21.5`` is
        published as ``"21.5"``. Consecutive unchanged temperatures are not
        republished. Publishing does not trigger callbacks
        registered with :meth:`on_event`; only messages received on the command
        topics do.

        Raises:
            RuntimeError: If the climate is not bound to a device.
            Exception: If the message could not be published.
        """
        self._validate_target_temperature(temperature)
        await self._target_temperature_value.set_value(temperature)

    async def set_mode(self, mode: str) -> None:
        """Publish the HVAC mode.

        ``mode`` must be one of :attr:`modes` when :attr:`modes` is set; it is
        published verbatim to the mode state topic (``~/<unique_id>/mode``).
        Consecutive unchanged modes are not republished.
        Publishing does not trigger callbacks registered with :meth:`on_event`;
        only messages received on the command topics do.

        Raises:
            RuntimeError: If the climate is not bound to a device.
            ValueError: If :attr:`modes` is set and ``mode`` is not in it.
            Exception: If the message could not be published.
        """
        if self.modes is not None and mode not in self.modes:
            raise ValueError(f"mode {mode!r} is not in modes {self.modes!r}")
        await self._mode_value.set_value(mode)

    async def set_action(self, action: str) -> None:
        """Publish the current action.

        ``action`` is published verbatim to the action topic
        (``~/<unique_id>/action``). The Home Assistant climate actions are
        ``"off"``, ``"heating"``, ``"cooling"``, ``"drying"``, ``"idle"``,
        and ``"fan"``; no validation is performed. Publishing does not trigger
        callbacks registered with :meth:`on_event`; only messages received on
        the command topics do. Actions are transient, so every call publishes.

        Raises:
            RuntimeError: If the climate is not bound to a device.
            Exception: If the message could not be published.
        """
        await self._action_value.set_value(action)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the temperature
        command topic (``~/<unique_id>/temperature_command``) and the mode
        command topic (``~/<unique_id>/mode_command``). Every message on the
        temperature command topic is awaited as an
        :class:`~ha_mqtt_device.event.Event` with ``event_type``
        ``"temperature"``, ``topic_type`` ``"temperature_command_topic"``, and
        ``state`` equal to the payload when it parses as a number (for example
        ``"21.5"``). Every message on the mode command topic is awaited with
        ``event_type`` ``"mode"``, ``topic_type`` ``"mode_command_topic"``, and
        ``state`` equal to the payload verbatim. An unknown payload is still
        delivered with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the climate is not bound to a device.
            Exception: If a subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            temperature_topic = device.info.resolve_topic(
                self.temperature_command_topic
            )
            await device.provider.subscribe(
                temperature_topic, self._dispatch_temperature
            )
            mode_topic = device.info.resolve_topic(self.mode_command_topic)
            await device.provider.subscribe(mode_topic, self._dispatch_mode)
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch_temperature(self, message: Message) -> None:
        """Turn a temperature command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_TEMPERATURE,
            topic_type=_TOPIC_TYPE_TEMPERATURE,
            message=message,
            payload=payload,
            state=self._temperature_state(payload),
        )

    async def _dispatch_mode(self, message: Message) -> None:
        """Turn a mode command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_MODE,
            topic_type=_TOPIC_TYPE_MODE,
            message=message,
            payload=payload,
            state=self._mode_state(payload),
        )

    def _mode_state(self, payload: str) -> str | None:
        """Map a mode command to a configured mode when modes are advertised."""
        if self.modes is not None and payload not in self.modes:
            return None
        return payload

    async def _notify(
        self,
        event_type: str,
        topic_type: str,
        message: Message,
        payload: str,
        state: str | None,
    ) -> None:
        """Build the event and await every registered callback."""
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            topic=message.topic,
            topic_type=topic_type,
            message=payload,
            state=state,
        )
        for callback in tuple(self._event_callbacks):
            try:
                await callback(event)
            except Exception:
                logger.exception(
                    "event callback failed for %s %r on topic %r",
                    type(self).__name__,
                    self.unique_id,
                    message.topic,
                )

    def _temperature_state(self, payload: str) -> str | None:
        """Map a temperature command payload to the payload string or ``None``.

        The payload is returned verbatim when it parses as a number; anything
        else maps to ``None``.
        """
        try:
            temperature = float(payload)
        except ValueError:
            return None
        if not isfinite(temperature) or not self._in_target_range(temperature):
            return None
        return payload

    def _validate_target_temperature(self, temperature: float) -> None:
        self._validate_finite(temperature, "temperature")
        if not self._in_target_range(temperature):
            raise ValueError("temperature is outside the configured range")

    def _in_target_range(self, temperature: float) -> bool:
        return (self.min_temp is None or temperature >= self.min_temp) and (
            self.max_temp is None or temperature <= self.max_temp
        )

    @staticmethod
    def _validate_finite(value: float, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    def discovery_config(self) -> dict[str, object]:
        """Return this climate's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        # Home Assistant's climate has no single state topic; its topics are
        # named individually.
        config["curr_temp_t"] = self.current_temperature_topic
        config["temp_stat_t"] = self.temperature_state_topic
        config["temp_cmd_t"] = self.temperature_command_topic
        config["mode_stat_t"] = self.mode_state_topic
        config["mode_cmd_t"] = self.mode_command_topic
        config["act_t"] = self.action_topic
        if self.modes is not None:
            config["modes"] = self.modes
        if self.temperature_unit is not None:
            config["temp_unit"] = self.temperature_unit
        if self.min_temp is not None:
            config["min_temp"] = self.min_temp
        if self.max_temp is not None:
            config["max_temp"] = self.max_temp
        if self.temp_step is not None:
            config["temp_step"] = self.temp_step
        if self.precision is not None:
            config["prec"] = self.precision
        if self.initial is not None:
            config["init"] = self.initial
        if self.mode_opt:
            config["mode_opt"] = True
        if self.temp_opt:
            config["temp_opt"] = True
        return self._resolve_discovery_config(config)
