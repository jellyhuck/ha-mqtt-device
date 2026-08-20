"""Humidifier entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.mapped_value import MappedValue
from ha_mqtt_device.values.numeric_value import NumericValue

__all__ = ["Humidifier"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``payload_on``.
DEFAULT_PAYLOAD_ON = "ON"

#: Home Assistant MQTT discovery default for ``payload_off``.
DEFAULT_PAYLOAD_OFF = "OFF"

#: Home Assistant MQTT discovery default for ``min_humidity``.
DEFAULT_MIN_HUMIDITY = 0

#: Home Assistant MQTT discovery default for ``max_humidity``.
DEFAULT_MAX_HUMIDITY = 100

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: ``event_type`` of events built from messages on the target-humidity
#: command topic.
_EVENT_TYPE_TARGET_HUMIDITY = "target_humidity"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Discovery config field that names the target-humidity command topic.
_TOPIC_TYPE_TARGET_HUMIDITY = "target_humidity_command_topic"


@dataclass
class Humidifier(Entity):
    """A humidifier belonging to a device.

    A humidifier has an on/off state and command topic, plus an optional
    target-humidity state and command topic. The device publishes its on/off
    state to the state topic (``~/<unique_id>/state``) with :meth:`set_state`;
    when target-humidity control is enabled, it publishes humidity to
    ``~/<unique_id>/target_humidity`` with :meth:`set_target_humidity`. It
    receives commands from Home Assistant on the corresponding command
    topics. Registering an async callback with :meth:`on_event` subscribes to
    the enabled topics and delivers every message as an
    :class:`~ha_mqtt_device.event.Event`::

        humidifier = Humidifier(unique_id="bedroom", name="Bedroom humidifier")
        device = Device(provider, info, entities=[humidifier])

        async def on_command(event: Event) -> None:
            if event.event_type == "command":
                await humidifier.set_state(event.state == "on")
            elif event.event_type == "target_humidity" and event.state is not None:
                await humidifier.set_target_humidity(float(event.state))

        async with device:
            await humidifier.on_event(on_command)
            await humidifier.set_state(True)
            await humidifier.set_target_humidity(50)

    Unlike :meth:`set_state` and :meth:`set_target_humidity`, commands
    received from Home Assistant do not change the humidifier by themselves —
    the application decides what to do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"humidifier"`` or ``"dehumidifier"``. Omitted from the discovery
            config when unset (Home Assistant defaults to ``"humidifier"``).
        payload_on: Payload published when the humidifier reports ``True`` and
            the default for the on state/command mapping.
        payload_off: Payload published when the humidifier reports ``False``
            and the default for the off state/command mapping.
        min_humidity: Minimum target humidity (``min_hum``). Defaults to
            ``0``, Home Assistant's discovery default.
        max_humidity: Maximum target humidity (``max_hum``). Defaults to
            ``100``, Home Assistant's discovery default.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
        target_humidity_enabled: Whether target-humidity state and command
            topics are advertised and subscribed. Defaults to ``True``.
    """

    component = "humidifier"

    device_class: str | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    min_humidity: int = DEFAULT_MIN_HUMIDITY
    max_humidity: int = DEFAULT_MAX_HUMIDITY
    optimistic: bool = False
    target_humidity_enabled: bool = True

    _state_value: Entity.StateValue[bool] = field(init=False, repr=False, compare=False)
    _target_humidity_value: Entity.StateValue[float] | None = field(
        init=False, repr=False, compare=False
    )

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscriptions have been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._state_value = self._make_persistent_state(
            MappedValue({True: self.payload_on, False: self.payload_off}),
            "state",
        )
        self._target_humidity_value = (
            self._make_persistent_state(NumericValue(), "state/target_humidity")
            if self.target_humidity_enabled
            else None
        )

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return Entity.command_topic_for(self.unique_id)

    @property
    def target_humidity_state_topic(self) -> str:
        """Target-humidity state topic, ``~/<unique_id>/target_humidity``."""
        return Entity.state_topic_for(self.unique_id, "target_humidity")

    @property
    def target_humidity_command_topic(self) -> str:
        """Target-humidity command topic, ``~/<unique_id>/target_humidity_command``."""
        return Entity.command_topic_for(self.unique_id, "target_humidity")

    async def set_state(self, state: bool) -> None:
        """Publish the humidifier's on/off state.

        ``True`` publishes :attr:`payload_on` and ``False`` publishes
        :attr:`payload_off` to the state topic (``~/<unique_id>/state``).
        Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topics do.

        Raises:
            RuntimeError: If the humidifier is not bound to a device.
            Exception: If the message could not be published.
        """
        await self._state_value.set_value(state)

    async def set_target_humidity(self, humidity: float) -> None:
        """Publish the target humidity.

        ``humidity`` is converted to a string and published to the
        target-humidity state topic (``~/<unique_id>/target_humidity``), for
        example ``50`` is published as ``"50"``. Publishing does not trigger
        callbacks registered with :meth:`on_event`; only messages received on
        the command topics do.

        Raises:
            RuntimeError: If the humidifier is not bound to a device.
            ValueError: If target-humidity control is disabled or the humidity
                is outside the configured range.
            Exception: If the message could not be published.
        """
        if not self.target_humidity_enabled:
            raise ValueError("target humidity control is disabled")
        self._validate_humidity(humidity)
        assert self._target_humidity_value is not None
        await self._target_humidity_value.set_value(humidity)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``) and, when enabled, the target-
        humidity command topic (``~/<unique_id>/target_humidity_command``).
        Every message is awaited as an :class:`~ha_mqtt_device.event.Event`:

        - On the command topic, ``event_type`` is ``"command"``,
          ``topic_type`` is ``"command_topic"``, and ``state`` is ``"on"`` or
          ``"off"`` derived from the payload via
          :attr:`payload_on`/:attr:`payload_off`.
        - On the target-humidity command topic, ``event_type`` is
          ``"target_humidity"``, ``topic_type`` is
          ``"target_humidity_command_topic"``, and ``state`` is the payload
          when it parses as a number (for example ``"50"``).

        An unknown payload is still delivered with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the humidifier is not bound to a device.
            Exception: If a subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch_command
            )
            if self.target_humidity_enabled:
                await device.provider.subscribe(
                    device.info.resolve_topic(self.target_humidity_command_topic),
                    self._dispatch_target_humidity,
                )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch_command(self, message: Message) -> None:
        """Turn a command topic message into an :class:`Event` and await it."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_COMMAND,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=message,
            payload=payload,
            state=self._command_state(payload),
        )

    async def _dispatch_target_humidity(self, message: Message) -> None:
        """Turn a target-humidity command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_TARGET_HUMIDITY,
            topic_type=_TOPIC_TYPE_TARGET_HUMIDITY,
            message=message,
            payload=payload,
            state=self._target_humidity_state(payload),
        )

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

    def _command_state(self, payload: str) -> str | None:
        """Map a command payload to ``"on"``, ``"off"``, or ``None``."""
        if payload == self.payload_on:
            return "on"
        if payload == self.payload_off:
            return "off"
        return None

    def _target_humidity_state(self, payload: str) -> str | None:
        """Map a target-humidity command payload to the payload or ``None``.

        The payload is returned verbatim when it parses as a number;
        anything else maps to ``None``.
        """
        try:
            humidity = float(payload)
        except ValueError:
            return None
        if not isfinite(humidity) or not self._humidity_in_range(humidity):
            return None
        return payload

    def _validate_humidity(self, humidity: float) -> None:
        if isinstance(humidity, bool) or not isinstance(humidity, (int, float)):
            raise TypeError("humidity must be a number")
        if not isfinite(humidity):
            raise ValueError("humidity must be finite")
        if not self._humidity_in_range(humidity):
            raise ValueError("humidity is outside the configured range")

    def _humidity_in_range(self, humidity: float) -> bool:
        return self.min_humidity <= humidity <= self.max_humidity

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this humidifier's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.target_humidity_enabled:
            config["hum_stat_t"] = self.target_humidity_state_topic
            config["hum_cmd_t"] = self.target_humidity_command_topic
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        if self.target_humidity_enabled:
            if self.min_humidity != DEFAULT_MIN_HUMIDITY:
                config["min_hum"] = self.min_humidity
            if self.max_humidity != DEFAULT_MAX_HUMIDITY:
                config["max_hum"] = self.max_humidity
        if self.optimistic:
            config["opt"] = True
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return self._resolve_discovery_config(config)
