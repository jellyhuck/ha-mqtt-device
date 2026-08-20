"""Tests for retained and transient publish-topic bookkeeping."""

from __future__ import annotations

from recording_provider import RecordingProvider

from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event_entity import EventEntity
from ha_mqtt_device.light import Light
from ha_mqtt_device.text import Text


def bound(entity: Entity) -> tuple[Device, RecordingProvider]:
    provider = RecordingProvider()
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[entity],
    )
    return device, provider


async def test_entity_state_value_clears_retained_topics() -> None:
    sensor = BinarySensor(unique_id="motion")
    _device, provider = bound(sensor)

    await sensor.set_state(True)
    await sensor._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/motion/state", "ON", True),
        ("homeassistant/device/dev-1/motion/state", "", True),
    ]


async def test_entity_clears_enabled_retained_topics_before_first_publish() -> None:
    light = Light(unique_id="lamp", brightness_enabled=True, rgb_enabled=True)
    _device, provider = bound(light)

    await light._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/lamp/state/power", "", True),
        ("homeassistant/device/dev-1/lamp/state/brightness", "", True),
        ("homeassistant/device/dev-1/lamp/state/rgb", "", True),
    ]


async def test_disabled_retained_topic_is_not_cleared() -> None:
    text = Text(unique_id="message", state_enabled=False)
    _device, provider = bound(text)

    await text._on_remove()

    assert provider.published == []


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
