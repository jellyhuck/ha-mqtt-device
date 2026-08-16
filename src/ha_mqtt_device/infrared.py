"""Infrared emitter and receiver entities for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["InfraredEmitter", "InfraredReceiver"]

logger = logging.getLogger(__name__)


def _validate_signal(signal: dict[str, Any]) -> None:
    """Validate the documented infrared signal fields."""
    timings = signal.get("timings")
    if (
        not isinstance(timings, list)
        or not timings
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value == 0
            for value in timings
        )
    ):
        raise ValueError("signal must contain non-zero integer 'timings'")
    for name in ("modulation", "repeat_count"):
        value = signal.get(name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"signal {name} must be an integer")
        if name == "modulation" and value <= 0:
            raise ValueError("signal modulation must be positive")
        if name == "repeat_count" and value < 0:
            raise ValueError("signal repeat_count must not be negative")


#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Discovery config field for the schema (emitter/receiver).
_SCHEMA_FIELD = "schema"


@dataclass
class InfraredEmitter(Entity):
    """An infrared emitter belonging to a device.

    An infrared emitter is triggered by Home Assistant rather than reported by
    the device: Home Assistant publishes an IR signal payload to the emitter's
    command topic (``~/<unique_id>/command``). The emitter has no state topic —
    the device never publishes anything for it. Registering an async callback
    with :meth:`on_event` subscribes to the command topic and delivers every
    command as an :class:`~ha_mqtt_device.event.Event`::

        emitter = InfraredEmitter(unique_id="tv_power", name="TV power")
        device = Device(provider, info, entities=[emitter])

        async def on_command(event: Event) -> None:
            # event.state is the parsed signal dict (timings, modulation, repeat_count)
            # or None for an unknown payload.
            await send_ir_signal(event.state)

        async with device:
            await emitter.on_event(on_command)

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
    """

    component = "infrared"

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return f"~/{self.unique_id}/command"

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``). Every command is awaited as an
        :class:`~ha_mqtt_device.event.Event` with ``event_type`` ``"command"``,
        ``topic_type`` ``"command_topic"``, ``message`` the raw JSON payload,
        and ``state`` the parsed signal dict (``{"timings": [...], "modulation": 38000,
        "repeat_count": 0}``) or ``None`` if the payload cannot be parsed.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the emitter is not bound to a device.
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
        state = self._parse_signal(payload)
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=_EVENT_TYPE_COMMAND,
            topic=message.topic,
            topic_type=_TOPIC_TYPE_COMMAND,
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

    def _parse_signal(self, payload: str) -> dict[str, Any] | None:
        """Parse an IR signal JSON payload.

        Returns a dict with ``timings`` (list[int]), ``modulation`` (int, optional),
        and ``repeat_count`` (int, optional), or ``None`` if parsing fails.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        try:
            _validate_signal(data)
        except TypeError, ValueError:
            return None
        result: dict[str, Any] = {"timings": data["timings"]}
        if "modulation" in data:
            result["modulation"] = data["modulation"]
        if "repeat_count" in data:
            result["repeat_count"] = data["repeat_count"]
        return result

    def discovery_config(self) -> dict[str, object]:
        """Return this emitter's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        # Emitters have no state topic; the single topic is the command topic.
        config.pop("stat_t")
        config["cmd_t"] = self.command_topic
        config[_SCHEMA_FIELD] = "emitter"
        return config


@dataclass
class InfraredReceiver(Entity):
    """An infrared receiver belonging to a device.

    An infrared receiver reports received IR signals to Home Assistant over MQTT;
    it has no command topic (receivers are read-only in Home Assistant). Create it
    with just a unique id and pass it to the device constructor, which binds it
    and publishes its discovery config::

        receiver = InfraredReceiver(unique_id="living_room_ir", name="Living room IR")
        device = Device(provider, info, entities=[receiver])

        async with device:
            await receiver.set_state({"timings": [9000, -4500, 562, -1687], "modulation": 38000})

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
    """

    component = "infrared"

    async def set_state(self, signal: dict[str, Any]) -> None:
        """Publish a received IR signal to Home Assistant.

        ``signal`` must be a dict with a required ``timings`` key (list of ints
        representing on/off microseconds) and an optional ``modulation`` key
        (int, typically 38000). The JSON payload is published to the state topic
        (``~/<unique_id>/state``).

        Raises:
            RuntimeError: If the receiver is not bound to a device.
            TypeError: If ``signal`` is not a dict.
            ValueError: If ``signal`` does not contain a valid ``timings`` list.
            Exception: If the message could not be published.
        """
        if not isinstance(signal, dict):
            raise TypeError("signal must be a dict")
        _validate_signal(signal)
        device = self._require_device()
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, json.dumps(signal))

    def discovery_config(self) -> dict[str, object]:
        """Return this receiver's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config[_SCHEMA_FIELD] = "receiver"
        return config
