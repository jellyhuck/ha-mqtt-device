"""The Device class: publishes a Home Assistant device's discovery and availability."""

from __future__ import annotations

import json
import logging
from types import TracebackType
from typing import Any, Self

from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.provider import MqttProvider

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
        self.entities: tuple[Entity, ...] = tuple(entities or [])
        seen: set[tuple[str, str]] = set()
        for entity in self.entities:
            key = (entity.component, entity.unique_id)
            if key in seen:
                raise ValueError(
                    f"duplicate entity component/unique_id: "
                    f"{entity.component}/{entity.unique_id}"
                )
            seen.add(key)
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
        await self.set_availability(False)

    async def configure(self) -> None:
        """Publish the MQTT discovery config for this device.

        Raises:
            Exception: If the message could not be published.
        """
        payload = self.info.discovery_payload()
        if self.entities:
            cmps: dict[str, dict[str, dict[str, Any]]] = {}
            for entity in self.entities:
                cmps.setdefault(entity.component, {})[entity.unique_id] = (
                    entity.discovery_config()
                )
            payload["cmps"] = cmps
        await self.provider.publish(self.info.discovery_topic(), json.dumps(payload))

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
        topic = self.info.resolve_topic(self.info.availability_topic)
        await self.provider.publish(topic, payload)

    async def remove(self) -> None:
        """Remove the device from Home Assistant.

        Publishes an empty payload to the discovery topic, which clears the
        discovery config.

        Raises:
            Exception: If the message could not be published.
        """
        await self.provider.publish(self.info.discovery_topic(), "")

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
