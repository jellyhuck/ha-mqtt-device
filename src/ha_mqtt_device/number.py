"""Number entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.numeric_value import NumericValue

__all__ = ["Number"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``min``.
DEFAULT_MIN = 0.0

#: Home Assistant MQTT discovery default for ``max``.
DEFAULT_MAX = 100.0

#: Home Assistant MQTT discovery default for ``step``.
DEFAULT_STEP = 1.0

#: Home Assistant MQTT discovery default for ``mode``.
DEFAULT_MODE = "auto"

#: Home Assistant MQTT discovery default for ``payload_reset``.
DEFAULT_PAYLOAD_RESET = "None"

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"


@dataclass
class Number(Entity):
    """A number belonging to a device.

    A number has two MQTT topics. The device publishes the current value to
    the state topic (``<device topic prefix>/<unique_id>/state``) with
    :meth:`set_state`, and it receives new values from Home Assistant on the
    command topic (``<device topic prefix>/<unique_id>/command``). Registering
    an async callback with
    :meth:`on_event` subscribes to the command topic and delivers every
    command as an :class:`~ha_mqtt_device.event.Event`::

        dimmer = Number(
            unique_id="dimmer",
            name="Dimmer",
            min_value=0,
            max_value=100,
            step=1,
            mode="box",
            unit_of_measurement="%",
        )
        device = Device(provider, info, entities=[dimmer])

        async def on_command(event: Event) -> None:
            if event.state is not None:
                await dimmer.set_state(float(event.state))

        async with device:
            await dimmer.on_event(on_command)
            await dimmer.set_state(75.0)

    Unlike :meth:`set_state`, commands received from Home Assistant do not
    change the number's value by themselves — the application decides what to
    do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"temperature"`` or ``"battery"``. Omitted from the discovery
            config when unset.
        min_value: Minimum value (``min``). Defaults to ``0``.
        max_value: Maximum value (``max``). Defaults to ``100``.
        step: Step size (``step``). Defaults to ``1``.
        mode: Slider mode (``mode``), either ``"auto"`` or ``"box"``.
            Defaults to ``"auto"``.
        unit_of_measurement: Unit of measurement (``unit_of_meas``), for
            example ``"°C"`` or ``"%"``. Omitted when unset.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
        payload_reset: Payload that resets the value to unknown
            (``pl_rst``). Omitted when unset or equal to the discovery
            default ``"None"``.
        expire_after: Seconds after which Home Assistant marks the number as
            unavailable without a state update (``exp_aft``). Omitted when
            unset.
        force_update: Whether Home Assistant should publish an update even if
            the value is unchanged (``frc_upd``). Defaults to ``False``.
    """

    component = "number"

    device_class: str | None = None
    min_value: float = DEFAULT_MIN
    max_value: float = DEFAULT_MAX
    step: float = DEFAULT_STEP
    mode: str = DEFAULT_MODE
    unit_of_measurement: str | None = None
    optimistic: bool = False
    payload_reset: str | None = None
    expire_after: int | None = None
    force_update: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)
    _state_value: Entity.StateValue[float] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._state_value = self._make_state(
            NumericValue(),
            "state",
            retain=True,
            force_update=self.force_update or self.expire_after is not None,
        )

    @property
    def command_topic(self) -> str:
        """Return the resolved MQTT command topic."""
        return self.command_topic_for()

    async def set_state(self, value: float) -> None:
        """Publish the number's value.

        ``value`` is converted to a string and published to the state topic
        (``<device topic prefix>/<unique_id>/state``), for example ``75.0`` is
        published as ``"75.0"``. Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topic do.
        Unchanged values are suppressed unless ``force_update`` or
        ``expire_after`` was configured when the entity was constructed.

        Raises:
            RuntimeError: If the number is not bound to a device.
            Exception: If the message could not be published.
        """
        self._validate_value(value)
        await self._state_value.set_value(value)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``<device topic prefix>/<unique_id>/command``). Every command
        message is awaited as
        an :class:`~ha_mqtt_device.event.Event` with ``event_type``
        ``"command"``, ``topic_type`` ``"command_topic"``, and ``state`` equal
        to the payload when it parses as a number (for example ``"75"``). An
        unknown payload — such as a reset payload — is still delivered with
        ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the number is not bound to a device.
            Exception: If the subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(self.command_topic, self._dispatch)
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        """Turn an MQTT message into an :class:`Event` and await the callbacks."""
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=_EVENT_TYPE_COMMAND,
            topic=message.topic,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=payload,
            state=self._command_state(payload),
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
        """Map a command payload to the payload string or ``None``.

        The payload is returned verbatim when it parses as a number;
        anything else (for example a reset payload) maps to ``None``.
        """
        try:
            value = float(payload)
        except ValueError:
            return None
        if not isfinite(value) or not self._value_in_range(value):
            return None
        return payload

    def _validate_value(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("value must be a number")
        if not isfinite(value):
            raise ValueError("value must be finite")
        if not self._value_in_range(value):
            raise ValueError("value is outside the configured range")

    def _value_in_range(self, value: float) -> bool:
        return self.min_value <= value <= self.max_value

    @property
    def state_topic(self) -> str:
        return self._state_value.topic().topic

    def discovery_config(self) -> dict[str, object]:
        """Return this number's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.min_value != DEFAULT_MIN:
            config["min"] = self.min_value
        if self.max_value != DEFAULT_MAX:
            config["max"] = self.max_value
        if self.step != DEFAULT_STEP:
            config["step"] = self.step
        if self.mode != DEFAULT_MODE:
            config["mode"] = self.mode
        if self.optimistic:
            config["opt"] = True
        if (
            self.payload_reset is not None
            and self.payload_reset != DEFAULT_PAYLOAD_RESET
        ):
            config["pl_rst"] = self.payload_reset
        if self.unit_of_measurement is not None:
            config["unit_of_meas"] = self.unit_of_measurement
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        if self.expire_after is not None:
            config["exp_aft"] = self.expire_after
        if self.force_update:
            config["frc_upd"] = True
        return self._resolve_discovery_config(config)
