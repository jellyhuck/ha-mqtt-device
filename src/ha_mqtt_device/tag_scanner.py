"""MQTT tag scanner support for Home Assistant standalone discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["TagScanner"]

logger = logging.getLogger(__name__)


@dataclass
class TagScanner(Entity):
    """A tag scanner discovered on Home Assistant's standalone ``tag`` topic.

    ``topic`` is the MQTT topic carrying scans. ``scan`` publishes a tag ID
    for hardware integrations, while ``on_event`` subscribes to the same topic
    and exposes incoming scans through the normal :class:`Event` callback API.
    The value template is retained as Home Assistant discovery configuration;
    this library deliberately does not evaluate Jinja templates.
    """

    component = "tag"
    standalone_discovery = True

    topic: str = ""
    value_template: str | None = None
    node_id: str | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.topic:
            raise ValueError("topic is required")

    async def scan(self, tag_id: str) -> None:
        """Publish a scanned tag ID to the configured scan topic."""
        device = self._require_device()
        if not isinstance(tag_id, str):
            raise TypeError("tag_id must be a string")
        await device.provider.publish(device.info.resolve_topic(self.topic), tag_id)

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for tag scans received on ``topic``."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="scan",
            topic=message.topic,
            topic_type="topic",
            message=payload,
            state=payload,
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

    def discovery_config(self) -> dict[str, Any]:
        """Return the standalone tag discovery payload, without ``device``."""
        config: dict[str, Any] = {"t": self.topic}
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        return config

    def standalone_discovery_config(
        self, info: DeviceInfo
    ) -> tuple[str, dict[str, Any]]:
        """Return this scanner's standalone discovery topic and payload."""
        object_path = (
            f"{info.discovery_prefix}/tag/{self.node_id}/{self.unique_id}/config"
            if self.node_id is not None
            else f"{info.discovery_prefix}/tag/{self.unique_id}/config"
        )
        config = self.discovery_config()
        config["dev"] = info.discovery_payload()["dev"]
        return object_path, config
