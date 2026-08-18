"""Tests for Device using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.provider import MqttMessageCallback
from ha_mqtt_device.sensor import Sensor


class FailingProvider:
    """MqttProvider whose publish always raises."""

    async def publish(
        self, topic: str, message: str | bytes, retain: bool = False
    ) -> None:
        raise RuntimeError("broker down")

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        return None

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def make_device(provider: Any, **info_kwargs: Any) -> Device:
    kwargs: dict[str, Any] = {"device_id": "dev-1", "name": "Device"}
    kwargs.update(info_kwargs)
    return Device(provider, DeviceInfo(**kwargs))


async def test_configure_publishes_discovery_payload() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.configure()

    assert provider.published == [
        (
            "homeassistant/device/dev-1/config",
            json.dumps(device.info.discovery_payload()),
            True,
        )
    ]
    payload = json.loads(provider.published[0][1])
    assert payload["dev"]["ids"] == ["dev-1"]
    assert payload["dev"]["name"] == "Device"
    assert payload["o"]["name"] == "ha-mqtt-device"
    assert payload["~"] == "homeassistant/device/dev-1"
    assert payload["avty"][0]["topic"] == "~/status"


async def test_set_availability_publishes_online_and_offline() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.set_availability(True)
    await device.set_availability(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/status", "online", True),
        ("homeassistant/device/dev-1/status", "offline", True),
    ]


async def test_set_availability_uses_custom_topic_and_payloads() -> None:
    provider = RecordingProvider()
    device = make_device(
        provider,
        topic_prefix="home/dev",
        availability_topic="~/state",
        availability_payload_available="up",
        availability_payload_unavailable="down",
    )

    await device.set_availability(True)
    await device.set_availability(False)

    assert provider.published == [
        ("home/dev/state", "up", True),
        ("home/dev/state", "down", True),
    ]


async def test_remove_publishes_empty_config() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/config", "", True),
        ("homeassistant/device/dev-1/status", "", True),
    ]


async def test_remove_clears_availability_and_configured_entity_state() -> None:
    provider = RecordingProvider()
    sensor = BinarySensor(unique_id="motion")
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[sensor],
    )

    await sensor.set_state(True)
    await device.remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/motion/state", "ON", True),
        ("homeassistant/device/dev-1/config", "", True),
        ("homeassistant/device/dev-1/status", "", True),
        ("homeassistant/device/dev-1/motion/state", "", True),
    ]


async def test_close_publishes_offline() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.close()

    assert provider.published == [
        ("homeassistant/device/dev-1/status", "offline", True)
    ]


async def test_aenter_returns_self_and_brings_device_online() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    entered = await device.__aenter__()

    assert entered is device
    assert provider.published == [
        (
            "homeassistant/device/dev-1/config",
            json.dumps(device.info.discovery_payload()),
            True,
        ),
        ("homeassistant/device/dev-1/status", "online", True),
    ]


async def test_aexit_publishes_offline() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.__aexit__(None, None, None)

    assert provider.published == [
        ("homeassistant/device/dev-1/status", "offline", True)
    ]


async def test_async_context_manager_manages_lifecycle() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    async with device:
        assert provider.published == [
            (
                "homeassistant/device/dev-1/config",
                json.dumps(device.info.discovery_payload()),
                True,
            ),
            ("homeassistant/device/dev-1/status", "online", True),
        ]

    assert provider.published[-1] == (
        "homeassistant/device/dev-1/status",
        "offline",
        True,
    )
    assert len(provider.published) == 3


async def test_async_context_manager_publishes_offline_on_exception() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    with pytest.raises(RuntimeError, match="boom"):
        async with device:
            raise RuntimeError("boom")

    assert provider.published[-1] == (
        "homeassistant/device/dev-1/status",
        "offline",
        True,
    )
    assert len(provider.published) == 3


async def test_aexit_propagates_publish_failure() -> None:
    device = make_device(FailingProvider())

    with pytest.raises(RuntimeError, match="broker down"):
        await device.__aexit__(None, None, None)


async def test_configure_propagates_publish_failure() -> None:
    device = make_device(FailingProvider())

    with pytest.raises(RuntimeError, match="broker down"):
        await device.configure()


async def test_set_availability_propagates_publish_failure() -> None:
    device = make_device(FailingProvider())

    with pytest.raises(RuntimeError, match="broker down"):
        await device.set_availability(True)


async def test_constructor_does_not_publish() -> None:
    provider = RecordingProvider()
    make_device(provider)

    assert provider.published == []


async def test_configure_includes_cmps_for_entities() -> None:
    provider = RecordingProvider()
    sensor = BinarySensor(unique_id="is_led_on", name="LED state")
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[sensor],
    )

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {
        "is_led_on": {
            "uniq_id": "is_led_on",
            "p": "binary_sensor",
            "stat_t": "~/is_led_on/state",
            "name": "LED state",
        }
    }


async def test_configure_without_entities_has_no_cmps() -> None:
    provider = RecordingProvider()
    device = make_device(provider)

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert "cmps" not in payload


async def test_constructor_binds_entities() -> None:
    provider = RecordingProvider()
    sensor = BinarySensor(unique_id="is_led_on")
    Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[sensor],
    )

    await sensor.set_state(True)

    assert provider.published == [
        ("homeassistant/device/dev-1/is_led_on/state", "ON", True)
    ]


async def test_constructor_rejects_duplicate_entity_keys() -> None:
    provider = RecordingProvider()
    first = BinarySensor(unique_id="is_led_on")
    second = BinarySensor(unique_id="is_led_on", name="Duplicate")

    with pytest.raises(ValueError, match="duplicate entity unique_id"):
        Device(
            provider,
            DeviceInfo(device_id="dev-1", name="Device"),
            entities=[first, second],
        )

    # Neither entity was bound.
    assert first.device is None
    assert second.device is None


async def test_constructor_rejects_duplicate_unique_id_across_components() -> None:
    provider = RecordingProvider()
    first = BinarySensor(unique_id="shared_id")
    second = Sensor(unique_id="shared_id")

    with pytest.raises(ValueError, match="duplicate entity unique_id"):
        Device(
            provider,
            DeviceInfo(device_id="dev-1", name="Device"),
            entities=[first, second],
        )

    assert first.device is None
    assert second.device is None


async def test_constructor_rejects_binding_same_entity_twice() -> None:
    provider = RecordingProvider()
    sensor = BinarySensor(unique_id="is_led_on")

    with pytest.raises(ValueError, match="duplicate entity"):
        Device(
            provider,
            DeviceInfo(device_id="dev-1", name="Device"),
            entities=[sensor, sensor],
        )
