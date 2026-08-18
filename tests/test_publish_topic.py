"""Tests for retained and transient publish-topic bookkeeping."""

from __future__ import annotations

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event_entity import EventEntity


def bound(entity: Entity) -> tuple[Device, RecordingProvider]:
    provider = RecordingProvider()
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[entity],
    )
    return device, provider


async def test_entity_registry_clears_retained_topics() -> None:
    sensor = BinarySensor(unique_id="motion")
    _device, provider = bound(sensor)

    await sensor.set_state(True)
    await sensor._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/motion/state", "ON", True),
        ("homeassistant/device/dev-1/motion/state", "", True),
    ]


async def test_entity_registry_rejects_conflicting_retention() -> None:
    sensor = BinarySensor(unique_id="motion")
    _device, _provider = bound(sensor)
    sensor._register_publish_topic(sensor.state_topic, retain=True)

    with pytest.raises(ValueError, match="conflicting retention policies"):
        sensor._register_publish_topic(sensor.state_topic, retain=False)


async def test_transient_topics_are_not_cleared() -> None:
    event = EventEntity(unique_id="doorbell", event_types=["pressed"])
    device, provider = bound(event)

    await event.set_event("pressed")
    await device.remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/doorbell/state", "pressed", False),
        ("homeassistant/device/dev-1/config", "", True),
        ("homeassistant/device/dev-1/status", "", True),
    ]
