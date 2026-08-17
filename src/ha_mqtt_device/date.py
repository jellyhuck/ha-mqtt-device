"""Date entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Date"]

logger = logging.getLogger(__name__)

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Canonical date payload format, ISO 8601 ``YYYY-MM-DD``.
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Date(Entity):
    """A date belonging to a device.

    A date has two MQTT topics. The device publishes the current value to the
    state topic (``~/<unique_id>/state``) with :meth:`set_state`, and it
    receives new values from Home Assistant on the command topic
    (``~/<unique_id>/command``). Values are ISO 8601 dates
    (``YYYY-MM-DD``), for example ``"2024-02-14"``. Registering an async
    callback with :meth:`on_event` subscribes to the command topic and
    delivers every command as an :class:`~ha_mqtt_device.event.Event`::

        vacation = Date(unique_id="vacation", name="Vacation start")
        device = Device(provider, info, entities=[vacation])

        async def on_command(event: Event) -> None:
            if event.state is not None:
                await vacation.set_state(event.state)

        async with device:
            await vacation.on_event(on_command)
            await vacation.set_state(date(2024, 2, 14))

    Unlike :meth:`set_state`, commands received from Home Assistant do not
    change the date by themselves — the application decides what to do in the
    callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
        force_update: Whether Home Assistant should publish an update even if
            the value is unchanged (``frc_upd``). Defaults to ``False``.
    """

    component = "date"

    optimistic: bool = False
    force_update: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, value: date | str) -> None:
        """Publish the date's value.

        ``value`` is converted to an ISO 8601 ``YYYY-MM-DD`` payload and
        published to the state topic (``~/<unique_id>/state``), for example
        ``date(2024, 2, 14)`` is published as ``"2024-02-14"``. Publishing
        does not trigger callbacks registered with :meth:`on_event`; only
        messages received on the command topic do.

        Raises:
            RuntimeError: If the date is not bound to a device.
            ValueError: If ``value`` is not a ``YYYY-MM-DD`` date string.
            TypeError: If ``value`` is a :class:`datetime.datetime` rather
                than a :class:`datetime.date`.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = self._date_payload(value)
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``). Every command message is awaited as
        an :class:`~ha_mqtt_device.event.Event` with ``event_type``
        ``"command"``, ``topic_type`` ``"command_topic"``, and ``state`` equal
        to the payload when it is a ``YYYY-MM-DD`` date (for example
        ``"2024-02-14"``). An unknown payload is still delivered with ``state``
        ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the date is not bound to a device.
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

        The payload is returned verbatim when it is a canonical ``YYYY-MM-DD``
        date; anything else maps to ``None``.
        """
        if not _DATE_PATTERN.fullmatch(payload):
            return None
        try:
            date.fromisoformat(payload)
        except ValueError:
            return None
        return payload

    def _date_payload(self, value: date | str) -> str:
        """Convert a date or ISO date string to a ``YYYY-MM-DD`` payload.

        Strings must be canonical ``YYYY-MM-DD`` dates; the extended ISO
        format accepted by :meth:`datetime.date.fromisoformat` (for example
        ``"20240214"``) is rejected so that only formats Home Assistant
        understands are published.

        Raises:
            ValueError: If ``value`` is not a ``YYYY-MM-DD`` date string.
            TypeError: If ``value`` is a :class:`datetime.datetime` rather
                than a :class:`datetime.date`.
        """
        if isinstance(value, str):
            return self._canonical_date(value)
        if isinstance(value, datetime):
            raise TypeError(
                "date value must be a datetime.date or a YYYY-MM-DD string, "
                f"got datetime {value.isoformat()!r}"
            )
        return value.isoformat()

    def _canonical_date(self, value: str) -> str:
        """Return the canonical ``YYYY-MM-DD`` form of an ISO date string.

        Raises:
            ValueError: If ``value`` is not a valid ``YYYY-MM-DD`` date.
        """
        if not _DATE_PATTERN.fullmatch(value):
            raise ValueError(f"date value {value!r} must be a YYYY-MM-DD date string")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError(f"date value {value!r} is not a valid date") from None

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this date's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.optimistic:
            config["opt"] = True
        if self.force_update:
            config["frc_upd"] = True
        return config
