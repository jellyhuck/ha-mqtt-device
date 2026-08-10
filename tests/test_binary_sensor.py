"""Tests for BinarySensor using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.provider import MqttMessageCallback


class RecordingProvider:
    """Minimal structural MqttProvider that records published messages."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str | bytes]] = []

    async def publish(self, topic: str, message: str | bytes) -> None:
        self.published.append((topic, message))

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        return None

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, BinarySensor]:
    """Build a device and a bound binary sensor with the given kwargs."""
    sensor = BinarySensor(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[sensor],
    )
    return device, sensor


async def test_set_state_publishes_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, sensor = make_bound(provider, unique_id="is_led_on")

    await sensor.set_state(True)
    await sensor.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/is_led_on/state", "ON"),
        ("homeassistant/device/dev-1/is_led_on/state", "OFF"),
    ]


async def test_set_state_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, sensor = make_bound(
        provider, unique_id="motion", payload_on="1", payload_off="0"
    )

    await sensor.set_state(True)
    await sensor.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/motion/state", "1"),
        ("homeassistant/device/dev-1/motion/state", "0"),
    ]


async def test_set_state_requires_binding() -> None:
    sensor = BinarySensor(unique_id="is_led_on")

    with pytest.raises(RuntimeError, match="not bound"):
        await sensor.set_state(True)


async def test_discovery_config_defaults() -> None:
    _, sensor = make_bound(RecordingProvider(), unique_id="is_led_on")

    # pl_on/pl_off are omitted because they match the discovery defaults.
    assert sensor.discovery_config() == {
        "uniq_id": "is_led_on",
        "p": "~/is_led_on/state",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, sensor = make_bound(
        RecordingProvider(),
        unique_id="door",
        name="Front door",
        device_class="door",
    )

    assert sensor.discovery_config() == {
        "uniq_id": "door",
        "p": "~/door/state",
        "name": "Front door",
        "dev_cla": "door",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, sensor = make_bound(
        RecordingProvider(),
        unique_id="motion",
        payload_on="1",
        payload_off="0",
    )

    assert sensor.discovery_config() == {
        "uniq_id": "motion",
        "p": "~/motion/state",
        "pl_on": "1",
        "pl_off": "0",
    }


async def test_discovery_config_omits_only_default_payloads() -> None:
    _, sensor = make_bound(
        RecordingProvider(),
        unique_id="motion",
        payload_on="1",
    )

    # pl_off still matches the discovery default and is omitted.
    assert sensor.discovery_config() == {
        "uniq_id": "motion",
        "p": "~/motion/state",
        "pl_on": "1",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        BinarySensor(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, sensor = make_bound(provider, unique_id="is_led_on", name="LED state")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {
        "binary_sensor": {"is_led_on": sensor.discovery_config()}
    }
