"""Scene entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.mapped_value import MappedValue

__all__ = ["Scene"]

logger = logging.getLogger(__name__)
DEFAULT_PAYLOAD_ON = "ON"


@dataclass
class Scene(Entity):
    """An MQTT scene activated by Home Assistant on a command topic.

    A scene has no state topic. :meth:`activate` publishes the configured
    activation payload, while :meth:`on_event` can be used when the device
    itself receives activation messages on the command topic.
    """

    component = "scene"

    payload_on: str = DEFAULT_PAYLOAD_ON
    command_template: str | None = None
    availability_topic: str | None = None
    availability_template: str | None = None
    payload_available: str = "online"
    payload_not_available: str = "offline"

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)
    _activation_value: Entity.StateValue[bool] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._activation_value = self._make_momentary_state(
            MappedValue({True: self.payload_on}),
            "command",
        )

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def activate(self) -> None:
        """Publish the configured payload for every activation request."""
        await self._activation_value.set_value(True)

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for activation messages received by the device."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
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
            state="on" if payload == self.payload_on else None,
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

    def discovery_config(self) -> dict[str, object]:
        """Return this scene's command-only discovery configuration."""
        config = super().discovery_config()
        config["cmd_t"] = self.command_topic
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
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
