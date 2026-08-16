"""Tests for WaterHeater using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message, MqttMessageCallback
from ha_mqtt_device.valve import Valve
from ha_mqtt_device.water_heater import WaterHeater


class RecordingProvider:
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

    async def deliver(self, topic: str, payload: str | bytes) -> None:
        raw = payload.encode() if isinstance(payload, str) else payload
        for callback in self.subscriptions.get(topic, []):
            await callback(Message(topic=topic, payload=raw))


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, WaterHeater]:
    heater = WaterHeater(**kwargs)
    device = Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), entities=[heater]
    )
    return device, heater


def collector(events: list[Event]) -> EventCallback:
    async def collect(event: Event) -> None:
        events.append(event)

    return collect


async def test_default_discovery_and_state_topics() -> None:
    _, heater = bound(RecordingProvider(), unique_id="boiler")
    assert heater.discovery_config() == {
        "uniq_id": "boiler",
        "p": "water_heater",
        "curr_temp_t": "~/boiler/state/current_temperature",
        "temp_stat_t": "~/boiler/state/temperature",
        "temp_cmd_t": "~/boiler/command/temperature",
        "mode_stat_t": "~/boiler/state/mode",
        "mode_cmd_t": "~/boiler/command/mode",
    }


async def test_publish_temperature_mode_and_power() -> None:
    provider = RecordingProvider()
    _, heater = bound(
        provider,
        unique_id="boiler",
        min_temp=40,
        max_temp=80,
        power_enabled=True,
    )
    await heater.set_current_temperature(55.5)
    await heater.set_target_temperature(60)
    await heater.set_mode("eco")
    await heater.set_power(True)
    await heater.set_power(False)
    assert provider.published == [
        (
            "homeassistant/device/dev-1/boiler/state/current_temperature",
            "55.5",
        ),
        ("homeassistant/device/dev-1/boiler/state/temperature", "60"),
        ("homeassistant/device/dev-1/boiler/state/mode", "eco"),
        ("homeassistant/device/dev-1/boiler/command/power", "ON"),
        ("homeassistant/device/dev-1/boiler/command/power", "OFF"),
    ]


async def test_optional_discovery_and_custom_payloads() -> None:
    _, heater = bound(
        RecordingProvider(),
        unique_id="boiler",
        name="Boiler",
        modes=["off", "eco"],
        temperature_unit="F",
        min_temp=115,
        max_temp=135,
        precision=0.5,
        initial=120,
        payload_on="ENABLE",
        payload_off="DISABLE",
        optimistic=True,
        power_enabled=True,
    )
    assert heater.discovery_config() == {
        "uniq_id": "boiler",
        "p": "water_heater",
        "name": "Boiler",
        "curr_temp_t": "~/boiler/state/current_temperature",
        "temp_stat_t": "~/boiler/state/temperature",
        "temp_cmd_t": "~/boiler/command/temperature",
        "mode_stat_t": "~/boiler/state/mode",
        "mode_cmd_t": "~/boiler/command/mode",
        "power_command_topic": "~/boiler/command/power",
        "modes": ["off", "eco"],
        "min_temp": 115,
        "max_temp": 135,
        "init": 120,
        "prec": 0.5,
        "temp_unit": "F",
        "pl_on": "ENABLE",
        "pl_off": "DISABLE",
        "opt": True,
    }


async def test_commands_subscribe_once_and_map_events() -> None:
    provider = RecordingProvider()
    _, heater = bound(provider, unique_id="boiler", power_enabled=True)
    events: list[Event] = []
    await heater.on_event(collector(events))
    await heater.on_event(collector([]))
    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/boiler/command/temperature",
        "homeassistant/device/dev-1/boiler/command/mode",
        "homeassistant/device/dev-1/boiler/command/power",
    ]
    await provider.deliver(
        "homeassistant/device/dev-1/boiler/command/temperature", "55.5"
    )
    await provider.deliver("homeassistant/device/dev-1/boiler/command/mode", "eco")
    await provider.deliver("homeassistant/device/dev-1/boiler/command/power", "ON")
    await provider.deliver("homeassistant/device/dev-1/boiler/command/mode", "unknown")
    assert [(event.event_type, event.state) for event in events] == [
        ("temperature", "55.5"),
        ("mode", "eco"),
        ("power", "on"),
        ("mode", None),
    ]
    assert events[0].topic_type == "temperature_command_topic"
    assert events[2].topic_type == "power_command_topic"


async def test_validation_and_device_configure() -> None:
    provider = RecordingProvider()
    device, heater = bound(provider, unique_id="boiler")
    with pytest.raises(ValueError, match="outside"):
        await heater.set_target_temperature(100)
    with pytest.raises(ValueError, match="unsupported water heater mode"):
        await heater.set_mode("solar")
    with pytest.raises(ValueError, match="not enabled"):
        await heater.set_power(True)
    with pytest.raises(ValueError, match="precision"):
        WaterHeater(unique_id="boiler", precision=0.25)
    with pytest.raises(ValueError, match="temperature_unit"):
        WaterHeater(unique_id="boiler", temperature_unit="K")
    with pytest.raises(ValueError, match="unsupported water heater modes"):
        WaterHeater(unique_id="boiler", modes=["solar"])

    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"boiler": heater.discovery_config()}


async def test_valve_and_water_heater_coexist_in_one_device() -> None:
    provider = RecordingProvider()
    valve = Valve(unique_id="valve")
    heater = WaterHeater(unique_id="boiler")
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[valve, heater],
    )

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert set(payload["cmps"]) == {"valve", "boiler"}
    assert payload["cmps"]["valve"] == valve.discovery_config()
    assert payload["cmps"]["boiler"] == heater.discovery_config()
