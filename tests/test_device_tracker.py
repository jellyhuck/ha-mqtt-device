"""Tests for DeviceTracker using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.device_tracker import DeviceTracker


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, DeviceTracker]:
    """Build a device and a bound device tracker with the given kwargs."""
    tracker = DeviceTracker(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[tracker],
    )
    return device, tracker


async def test_set_state_publishes_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(provider, unique_id="phone")

    await tracker.set_state(True)
    await tracker.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/phone/state", "home", True),
        ("homeassistant/device/dev-1/phone/state", "not_home", True),
    ]


async def test_set_state_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(
        provider, unique_id="phone", payload_home="in", payload_not_home="out"
    )

    await tracker.set_state(True)
    await tracker.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/phone/state", "in", True),
        ("homeassistant/device/dev-1/phone/state", "out", True),
    ]


async def test_set_state_requires_binding() -> None:
    tracker = DeviceTracker(unique_id="phone")

    with pytest.raises(RuntimeError, match="not bound"):
        await tracker.set_state(True)


async def test_set_location_publishes_json_report_to_state_topic() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(provider, unique_id="phone")

    await tracker.set_location(32.87336, -117.22743)

    topic, message, retain = provider.published[0]
    assert topic == "homeassistant/device/dev-1/phone/state"
    assert json.loads(message) == {
        "latitude": 32.87336,
        "longitude": -117.22743,
    }
    assert retain is True


async def test_set_location_includes_extra_fields() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(provider, unique_id="phone")

    await tracker.set_location(
        32.87336, -117.22743, gps_accuracy=50, battery_level=82, source_type="gps"
    )

    _, message, _ = provider.published[0]
    assert json.loads(message) == {
        "latitude": 32.87336,
        "longitude": -117.22743,
        "gps_accuracy": 50,
        "battery_level": 82,
        "source_type": "gps",
    }


async def test_set_location_falls_back_to_configured_extras() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(
        provider,
        unique_id="phone",
        gps_accuracy=50,
        battery_level=82,
        source_type="gps",
    )

    await tracker.set_location(32.87336, -117.22743)

    _, message, _ = provider.published[0]
    assert json.loads(message) == {
        "latitude": 32.87336,
        "longitude": -117.22743,
        "gps_accuracy": 50,
        "battery_level": 82,
        "source_type": "gps",
    }


async def test_set_location_requires_binding() -> None:
    tracker = DeviceTracker(unique_id="phone")

    with pytest.raises(RuntimeError, match="not bound"):
        await tracker.set_location(32.87336, -117.22743)


async def test_state_and_location_share_change_detection() -> None:
    provider = RecordingProvider()
    _, tracker = make_bound(provider, unique_id="phone")

    await tracker.set_state(True)
    await tracker.set_state(True)
    await tracker.set_location(32.87336, -117.22743)
    await tracker.set_state(True)

    location = json.dumps({"latitude": 32.87336, "longitude": -117.22743})
    assert provider.published == [
        ("homeassistant/device/dev-1/phone/state", "home", True),
        ("homeassistant/device/dev-1/phone/state", location, True),
        ("homeassistant/device/dev-1/phone/state", "home", True),
    ]


async def test_discovery_config_defaults() -> None:
    _, tracker = make_bound(RecordingProvider(), unique_id="phone")

    # pl_home/pl_not_home are omitted because they match the discovery
    # defaults; the optional location fields are omitted when unset.
    assert tracker.discovery_config() == {
        "uniq_id": "phone",
        "p": "device_tracker",
        "stat_t": "homeassistant/device/dev-1/phone/state",
    }


async def test_discovery_config_includes_name_and_icon() -> None:
    _, tracker = make_bound(
        RecordingProvider(),
        unique_id="phone",
        name="Phone",
        icon="mdi:cellphone",
    )

    assert tracker.discovery_config() == {
        "uniq_id": "phone",
        "p": "device_tracker",
        "stat_t": "homeassistant/device/dev-1/phone/state",
        "name": "Phone",
        "ic": "mdi:cellphone",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, tracker = make_bound(
        RecordingProvider(),
        unique_id="phone",
        payload_home="in",
        payload_not_home="out",
    )

    assert tracker.discovery_config() == {
        "uniq_id": "phone",
        "p": "device_tracker",
        "stat_t": "homeassistant/device/dev-1/phone/state",
        "pl_home": "in",
        "pl_not_home": "out",
    }


async def test_discovery_config_includes_location_fields() -> None:
    _, tracker = make_bound(
        RecordingProvider(),
        unique_id="phone",
        source_type="bluetooth",
        latitude=32.87336,
        longitude=-117.22743,
        gps_accuracy=50,
        battery_level=82,
    )

    assert tracker.discovery_config() == {
        "uniq_id": "phone",
        "p": "device_tracker",
        "stat_t": "homeassistant/device/dev-1/phone/state",
        "source_type": "bluetooth",
        "lat": 32.87336,
        "lon": -117.22743,
        "gps_acc": 50,
        "bat_lvl": 82,
    }


async def test_discovery_config_omits_default_source_type() -> None:
    _, tracker = make_bound(RecordingProvider(), unique_id="phone", source_type="gps")

    # source_type matches the Home Assistant default and is omitted.
    assert tracker.discovery_config() == {
        "uniq_id": "phone",
        "p": "device_tracker",
        "stat_t": "homeassistant/device/dev-1/phone/state",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        DeviceTracker(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, tracker = make_bound(provider, unique_id="phone", name="Phone")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"phone": tracker.discovery_config()}
