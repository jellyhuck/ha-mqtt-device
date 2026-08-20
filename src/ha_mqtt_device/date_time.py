"""DateTime entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.date_time_value import DateTimeValue

__all__ = ["DateTime"]

logger = logging.getLogger(__name__)

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Format Home Assistant uses for datetime state and command payloads.
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Canonical datetime payload format, ``YYYY-MM-DD HH:MM:SS``.
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


@dataclass
class DateTime(Entity):
    """A datetime belonging to a device.

    A datetime has two MQTT topics. The device publishes the current value to
    the state topic (``~/<unique_id>/state``) with :meth:`set_state`, and it
    receives new values from Home Assistant on the command topic
    (``~/<unique_id>/command``). Values are ``YYYY-MM-DD HH:MM:SS`` datetimes,
    for example ``"2024-02-14 10:30:00"``. Registering an async callback with
    :meth:`on_event` subscribes to the command topic and delivers every
    command as an :class:`~ha_mqtt_device.event.Event`::

        alarm = DateTime(unique_id="alarm", name="Morning alarm")
        device = Device(provider, info, entities=[alarm])

        async def on_command(event: Event) -> None:
            if event.state is not None:
                await alarm.set_state(event.state)

        async with device:
            await alarm.on_event(on_command)
            await alarm.set_state(datetime(2024, 2, 14, 10, 30))

    Unlike :meth:`set_state`, commands received from Home Assistant do not
    change the datetime by themselves — the application decides what to do in
    the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
        force_update: Whether Home Assistant should publish an update even if
            the value is unchanged (``frc_upd``). Defaults to ``False``.
    """

    component = "datetime"

    optimistic: bool = False
    force_update: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)
    _state_value: Entity.StateValue[datetime] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._state_value = self._make_state(
            DateTimeValue(), "state", retain=True, force_update=self.force_update
        )

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, value: datetime | str) -> None:
        """Publish the datetime's value.

        ``value`` is converted to a ``YYYY-MM-DD HH:MM:SS`` payload and
        published to the state topic (``~/<unique_id>/state``), for example
        ``datetime(2024, 2, 14, 10, 30)`` is published as
        ``"2024-02-14 10:30:00"``. A timezone-aware datetime is published with
        its wall-clock components verbatim — no timezone conversion is
        performed. Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topic do.
        Canonically equal values are suppressed unless :attr:`force_update`
        was enabled at construction.

        Raises:
            RuntimeError: If the datetime is not bound to a device.
            ValueError: If ``value`` is not a ``YYYY-MM-DD HH:MM:SS`` string.
            TypeError: If ``value`` is neither a :class:`datetime.datetime`
                nor a ``YYYY-MM-DD HH:MM:SS`` string.
            Exception: If the message could not be published.
        """
        normalized = datetime.fromisoformat(self._datetime_payload(value))
        await self._state_value.set_value(normalized)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``). Every command message is awaited as
        an :class:`~ha_mqtt_device.event.Event` with ``event_type``
        ``"command"``, ``topic_type`` ``"command_topic"``, and ``state`` equal
        to the payload when it is a ``YYYY-MM-DD HH:MM:SS`` datetime (for
        example ``"2024-02-14 10:30:00"``). An unknown payload is still
        delivered with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the datetime is not bound to a device.
            Exception: If the subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            topic = device.info.resolve_topic(self.command_topic)
            await device.provider.subscribe(topic, self._dispatch)
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

        The payload is returned verbatim when it is a canonical
        ``YYYY-MM-DD HH:MM:SS`` datetime; anything else maps to ``None``.
        """
        if not _DATETIME_PATTERN.fullmatch(payload):
            return None
        try:
            datetime.fromisoformat(payload)
        except ValueError:
            return None
        return payload

    def _datetime_payload(self, value: datetime | str) -> str:
        """Convert a datetime or datetime string to a payload.

        ``value`` is formatted as ``YYYY-MM-DD HH:MM:SS``; timezone
        information is not included in the payload. Strings must be canonical
        ``YYYY-MM-DD HH:MM:SS`` datetimes; other ISO formats accepted by
        :meth:`datetime.datetime.fromisoformat` (for example ``"2024-02-14T10:30:00"``)
        are rejected so that only formats Home Assistant understands are
        published.

        Raises:
            ValueError: If ``value`` is not a ``YYYY-MM-DD HH:MM:SS`` string.
            TypeError: If ``value`` is neither a :class:`datetime.datetime`
                nor a ``YYYY-MM-DD HH:MM:SS`` string.
        """
        if isinstance(value, str):
            return self._canonical_datetime(value)
        if isinstance(value, datetime):
            return value.strftime(_DATETIME_FORMAT)
        raise TypeError(
            "datetime value must be a datetime.datetime or a "
            "YYYY-MM-DD HH:MM:SS string, "
            f"got {type(value).__name__} {value!r}"
        )

    def _canonical_datetime(self, value: str) -> str:
        """Return the canonical ``YYYY-MM-DD HH:MM:SS`` form of a datetime string.

        Raises:
            ValueError: If ``value`` is not a valid ``YYYY-MM-DD HH:MM:SS``
                datetime.
        """
        if not _DATETIME_PATTERN.fullmatch(value):
            raise ValueError(
                f"datetime value {value!r} must be a "
                "YYYY-MM-DD HH:MM:SS datetime string"
            )
        try:
            return datetime.fromisoformat(value).strftime(_DATETIME_FORMAT)
        except ValueError:
            raise ValueError(
                f"datetime value {value!r} is not a valid datetime"
            ) from None

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this datetime's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.optimistic:
            config["opt"] = True
        if self.force_update:
            config["frc_upd"] = True
        return self._resolve_discovery_config(config)
