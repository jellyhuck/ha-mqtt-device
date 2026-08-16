"""Tests for Vacuum using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device import Device, DeviceInfo, Event, Vacuum
from ha_mqtt_device.provider import Message, MqttMessageCallback


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

    async def deliver(self, topic: str, payload: str) -> None:
        for callback in self.subscriptions.get(topic, []):
            await callback(Message(topic, payload.encode()))


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Vacuum]:
    entity = Vacuum(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [entity]
    ), entity


async def test_default_discovery_and_json_state() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="cleaner")

    assert entity.discovery_config() == {
        "uniq_id": "cleaner",
        "p": "vacuum",
        "stat_t": "~/cleaner/state",
        "cmd_t": "~/cleaner/command",
    }
    await entity.set_state(
        "docked",
        fan_speed="off",
        segments={"1": "Kitchen", "2": "Living room"},
    )

    assert json.loads(provider.published[0][1]) == {
        "state": "docked",
        "fan_speed": "off",
        "segments": {"1": "Kitchen", "2": "Living room"},
    }
    await entity.reset_state()
    assert provider.published[1] == ("homeassistant/device/dev-1/cleaner/state", "null")


async def test_optional_features_and_payload_mappings() -> None:
    _, entity = bound(
        RecordingProvider(),
        unique_id="cleaner",
        supported_features=[
            "start",
            "pause",
            "stop",
            "return_home",
            "locate",
            "clean_spot",
            "status",
            "fan_speed",
            "send_command",
        ],
        fan_speed_list=["min", "max"],
        send_command_enabled=True,
        clean_segments_enabled=True,
        payload_start="go",
    )

    assert entity.discovery_config() == {
        "uniq_id": "cleaner",
        "p": "vacuum",
        "stat_t": "~/cleaner/state",
        "cmd_t": "~/cleaner/command",
        "send_cmd_t": "~/cleaner/command/send",
        "set_fan_spd_t": "~/cleaner/command/fan_speed",
        "fanspd_lst": ["min", "max"],
        "clean_segments_command_topic": "~/cleaner/command/clean_segments",
        "sup_feat": [
            "start",
            "pause",
            "stop",
            "return_home",
            "locate",
            "clean_spot",
            "status",
            "fan_speed",
            "send_command",
        ],
        "pl_strt": "go",
    }


async def test_all_command_paths_publish_documented_payloads() -> None:
    provider = RecordingProvider()
    _, entity = bound(
        provider,
        unique_id="cleaner",
        supported_features=[
            "start",
            "pause",
            "stop",
            "return_home",
            "locate",
            "clean_spot",
            "fan_speed",
            "send_command",
        ],
        fan_speed_list=["min", "max"],
        send_command_enabled=True,
        clean_segments_enabled=True,
    )

    await entity.start()
    await entity.pause()
    await entity.stop()
    await entity.return_to_base()
    await entity.locate()
    await entity.clean_spot()
    await entity.set_fan_speed("max")
    await entity.send_command("custom")
    await entity.send_command("custom", {"param": "value"})
    await entity.clean_segments(["1", "2"])

    assert provider.published == [
        ("homeassistant/device/dev-1/cleaner/command", "start"),
        ("homeassistant/device/dev-1/cleaner/command", "pause"),
        ("homeassistant/device/dev-1/cleaner/command", "stop"),
        ("homeassistant/device/dev-1/cleaner/command", "return_to_base"),
        ("homeassistant/device/dev-1/cleaner/command", "locate"),
        ("homeassistant/device/dev-1/cleaner/command", "clean_spot"),
        ("homeassistant/device/dev-1/cleaner/command/fan_speed", "max"),
        ("homeassistant/device/dev-1/cleaner/command/send", "custom"),
        (
            "homeassistant/device/dev-1/cleaner/command/send",
            json.dumps({"command": "custom", "param": "value"}),
        ),
        (
            "homeassistant/device/dev-1/cleaner/command/clean_segments",
            '["1", "2"]',
        ),
    ]


async def test_command_events_map_topics_and_unknown_values() -> None:
    provider = RecordingProvider()
    _, entity = bound(
        provider,
        unique_id="cleaner",
        supported_features=["start", "fan_speed", "send_command"],
        fan_speed_list=["min", "max"],
        send_command_enabled=True,
        clean_segments_enabled=True,
    )
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await entity.on_event(collect)
    await entity.on_event(collect)
    command = "homeassistant/device/dev-1/cleaner/command"
    fan = "homeassistant/device/dev-1/cleaner/command/fan_speed"
    custom = "homeassistant/device/dev-1/cleaner/command/send"
    await provider.deliver(command, "start")
    await provider.deliver(command, "unknown")
    await provider.deliver(fan, "max")
    await provider.deliver(fan, "turbo")
    await provider.deliver(custom, '{"command":"spot","room":2}')

    assert all(len(callbacks) == 1 for callbacks in provider.subscriptions.values())
    assert [event.state for event in received] == [
        "start",
        "start",
        None,
        None,
        "max",
        "max",
        None,
        None,
        {"command": "spot", "room": 2},
        {"command": "spot", "room": 2},
    ]
    assert received[0].topic_type == "command_topic"
    assert received[4].topic_type == "set_fan_speed_topic"
    assert received[8].topic_type == "send_command_topic"


async def test_vacuum_validation_and_device_configuration() -> None:
    with pytest.raises(ValueError, match="supported state"):
        Vacuum(unique_id="cleaner")._validated_state({"state": "unknown"})
    with pytest.raises(ValueError, match="fan_speed_list"):
        Vacuum(unique_id="cleaner", supported_features=["fan_speed"])
    with pytest.raises(ValueError, match="unsupported vacuum feature"):
        Vacuum(unique_id="cleaner", supported_features=["wash"])

    provider = RecordingProvider()
    device, entity = bound(provider, unique_id="cleaner")
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"cleaner": entity.discovery_config()}

    with pytest.raises(ValueError, match="disabled"):
        await entity.set_fan_speed("max")
    with pytest.raises(ValueError, match="unsupported vacuum state"):
        await entity.set_state("unknown")
