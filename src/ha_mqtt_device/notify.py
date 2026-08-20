"""Notify entity for Home Assistant MQTT discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Notify"]

logger = logging.getLogger(__name__)


@dataclass
class Notify(Entity):
    """An MQTT notification service.

    Home Assistant sends notification messages to the command topic.  Notify
    has no state topic; received payloads are delivered to callbacks verbatim
    and valid JSON objects are also exposed as a dictionary in ``Event.state``.
    """

    component = "notify"

    command_template: str | None = None
    availability_topic: str | None = None
    availability_template: str | None = None
    payload_available: str = "online"
    payload_not_available: str = "offline"

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.payload_available or not self.payload_not_available:
            raise ValueError("availability payloads must be non-empty")

    @property
    def command_topic(self) -> str:
        """Return the resolved command topic for this bound entity."""
        return self.command_topic_for()

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for notification messages from Home Assistant."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(self.command_topic, self._dispatch)
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="command",
            topic=message.topic,
            topic_type="command_topic",
            message=payload,
            state=self._state(payload),
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

    @staticmethod
    def _state(payload: str) -> str | dict[str, Any]:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        return value if isinstance(value, dict) else payload

    def discovery_config(self) -> dict[str, object]:
        """Return this notify service's device discovery configuration."""
        config = super().discovery_config()
        config["cmd_t"] = self.command_topic
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.availability_topic is not None:
            config["avty_t"] = self.availability_topic
        if self.availability_template is not None:
            config["avty_tpl"] = self.availability_template
        if self.payload_available != "online":
            config["pl_avail"] = self.payload_available
        if self.payload_not_available != "offline":
            config["pl_not_avail"] = self.payload_not_available
        return self._resolve_discovery_config(config)
