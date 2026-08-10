"""Tests for Sensor using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.provider import MqttMessageCallback
from ha_mqtt_device.sensor import Sensor


class RecordingProvider:
    """Minimal structural MqttProvider that records publishes and subscriptions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str | bytes]] = []
        self.subscriptions: dict[str, list[MqttMessageCallback]] = {}

    async def publish(self, topic: str, message: str | bytes) -> None:
        self.published.append((topic, message))

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        self.subscriptions.setdefault(topic, []).append(callback)

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Sensor]:
    """Build a device and a bound sensor with the given kwargs."""
    sensor = Sensor(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[sensor],
    )
    return device, sensor


async def test_set_state_publishes_stringified_values_to_state_topic() -> None:
    provider = RecordingProvider()
    _, sensor = make_bound(provider, unique_id="temperature")

    await sensor.set_state("21.5")
    await sensor.set_state(42)
    await sensor.set_state(21.5)

    assert provider.published == [
        ("homeassistant/device/dev-1/temperature/state", "21.5"),
        ("homeassistant/device/dev-1/temperature/state", "42"),
        ("homeassistant/device/dev-1/temperature/state", "21.5"),
    ]


async def test_set_state_requires_binding() -> None:
    sensor = Sensor(unique_id="temperature")

    with pytest.raises(RuntimeError, match="not bound"):
        await sensor.set_state(21.5)


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, sensor = make_bound(provider, unique_id="temperature")

    await sensor.set_state(21.5)

    assert provider.subscriptions == {}


async def test_discovery_config_defaults() -> None:
    _, sensor = make_bound(RecordingProvider(), unique_id="temperature")

    # Every optional key is omitted because it matches the discovery defaults.
    assert sensor.discovery_config() == {
        "uniq_id": "temperature",
        "p": "~/temperature/state",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, sensor = make_bound(
        RecordingProvider(),
        unique_id="temperature",
        name="Temperature",
        device_class="temperature",
    )

    assert sensor.discovery_config() == {
        "uniq_id": "temperature",
        "p": "~/temperature/state",
        "name": "Temperature",
        "dev_cla": "temperature",
    }


async def test_discovery_config_includes_measurement_fields() -> None:
    _, sensor = make_bound(
        RecordingProvider(),
        unique_id="energy",
        unit_of_measurement="kWh",
        state_class="total_increasing",
        expire_after=300,
        suggested_display_precision=2,
    )

    assert sensor.discovery_config() == {
        "uniq_id": "energy",
        "p": "~/energy/state",
        "unit_of_meas": "kWh",
        "stat_cla": "total_increasing",
        "exp_aft": 300,
        "sug_dsp_prc": 2,
    }


async def test_discovery_config_omits_force_update_by_default() -> None:
    _, sensor = make_bound(RecordingProvider(), unique_id="temperature")

    assert "frc_upd" not in sensor.discovery_config()


async def test_discovery_config_includes_force_update() -> None:
    _, sensor = make_bound(
        RecordingProvider(), unique_id="temperature", force_update=True
    )

    assert sensor.discovery_config() == {
        "uniq_id": "temperature",
        "p": "~/temperature/state",
        "frc_upd": True,
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Sensor(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, sensor = make_bound(provider, unique_id="temperature", name="Temperature")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"sensor": {"temperature": sensor.discovery_config()}}
