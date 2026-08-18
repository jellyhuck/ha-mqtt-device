"""The Device class: publishes a Home Assistant device's discovery and availability."""

from __future__ import annotations

import json
import logging
from types import TracebackType
from typing import Any, Self

from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.provider import MqttProvider
from ha_mqtt_device.publish_topic import PublishTopic

__all__ = ["Device"]

logger = logging.getLogger(__name__)


class Device:
    """A Home Assistant device exposed over MQTT device discovery.

    Constructing a device only stores the provider and the device info; nothing
    is published yet. The device is an async context manager — the recommended
    way to manage its lifecycle: entering it publishes the discovery config and
    announces the device as available, and exiting it announces the device as
    unavailable. The individual steps are also exposed as :meth:`configure`,
    :meth:`set_availability`, :meth:`remove`, and :meth:`close`.
    """

    def __init__(
        self,
        provider: MqttProvider,
        info: DeviceInfo,
        entities: list[Entity] | None = None,
    ) -> None:
        self.provider = provider
        self.info = info
        self._publish_topics: dict[str, PublishTopic] = {}
        self.entities: tuple[Entity, ...] = tuple(entities or [])
        seen: set[str] = set()
        for entity in self.entities:
            if entity.unique_id in seen:
                raise ValueError(f"duplicate entity unique_id: {entity.unique_id}")
            seen.add(entity.unique_id)
        for entity in self.entities:
            entity.bind(self)

    async def __aenter__(self) -> Self:
        """Publish the discovery config and announce the device as available.

        Equivalent to ``await configure()`` followed by
        ``await set_availability(True)``.

        Raises:
            Exception: If a message could not be published.
        """
        await self.configure()
        await self.set_availability(True)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Announce the device as unavailable.

        Runs even when the body of the ``async with`` block raised, but does
        not suppress the exception.

        Raises:
            Exception: If the message could not be published.
        """
        # TODO-21: Configure provider/client LWT support for unclean disconnects.
        await self.set_availability(False)

    async def configure(self) -> None:
        """Publish the MQTT discovery config for this device.

        Raises:
            Exception: If the message could not be published.
        """
        payload = self.info.discovery_payload()
        if self.entities:
            cmps: dict[str, dict[str, Any]] = {}
            for entity in self.entities:
                cmps[entity.unique_id] = entity.discovery_config()
            payload["cmps"] = cmps
        discovery_topic = self._register_publish_topic(
            self.info.discovery_topic(), retain=True
        )
        await self._publish(discovery_topic, json.dumps(payload))

    async def set_availability(self, available: bool) -> None:
        """Publish the device's availability state.

        ``True`` publishes ``info.availability_payload_available`` (default
        ``"online"``) and ``False`` publishes
        ``info.availability_payload_unavailable`` (default ``"offline"``) to
        the availability topic.

        Raises:
            Exception: If the message could not be published.
        """
        payload = (
            self.info.availability_payload_available
            if available
            else self.info.availability_payload_unavailable
        )
        topic = self._register_publish_topic(
            self.info.resolve_topic(self.info.availability_topic), retain=True
        )
        await self._publish(topic, payload)

    async def remove(self) -> None:
        """Remove the device from Home Assistant.

        Publishes empty retained payloads to discovery, availability, and all
        registered retained entity topics, clearing them from the broker.

        Raises:
            Exception: If the message could not be published.
        """
        self._register_publish_topic(self.info.discovery_topic(), retain=True)
        self._register_publish_topic(
            self.info.resolve_topic(self.info.availability_topic), retain=True
        )
        await self._on_remove()

    def _register_publish_topic(self, topic: str, *, retain: bool) -> PublishTopic:
        """Register a device-owned topic and enforce its retention policy."""
        descriptor = PublishTopic(topic, retain)
        existing = self._publish_topics.get(topic)
        if existing is not None and existing.retain != retain:
            raise ValueError(
                f"topic {topic!r} was registered with conflicting retention policies"
            )
        self._publish_topics[topic] = descriptor
        return existing or descriptor

    async def _publish(self, topic: PublishTopic, message: str | bytes) -> None:
        """Publish through a device-owned topic descriptor."""
        await self.provider.publish(topic.topic, message, retain=topic.retain)

    async def _on_remove(self) -> None:
        """Clear all retained device and entity topics."""
        for descriptor in self._publish_topics.values():
            if descriptor.retain:
                await self.provider.publish(descriptor.topic, "", retain=True)
        for entity in self.entities:
            await entity._on_remove()

    async def close(self) -> None:
        """Publish the "unavailable" state.

        This is the explicit, awaited teardown; call it before the event loop
        shuts down. Prefer ``async with device``, which announces the device as
        unavailable automatically when the block exits. To make Home Assistant
        forget the device, call :meth:`remove` separately.

        Raises:
            Exception: If a message could not be published.
        """
        await self.set_availability(False)
