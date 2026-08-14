"""Tests for SelectEntity using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device import Device, DeviceInfo, Event, SelectEntity
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


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, SelectEntity]:
    select = SelectEntity(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [select]
    ), select


async def test_set_state_validates_and_publishes_selected_option() -> None:
    provider = RecordingProvider()
    _, select = bound(provider, unique_id="mode", options=["Auto", "Manual"])

    await select.set_state("Manual")

    assert provider.published == [("homeassistant/device/dev-1/mode/state", "Manual")]
    with pytest.raises(ValueError, match="must be one of"):
        await select.set_state("Invalid")


async def test_discovery_defaults_include_required_options_and_topics() -> None:
    _, select = bound(
        RecordingProvider(), unique_id="mode", name="Mode", options=["Auto", "Manual"]
    )

    assert select.discovery_config() == {
        "uniq_id": "mode",
        "name": "Mode",
        "stat_t": "~/mode/state",
        "cmd_t": "~/mode/command",
        "ops": ["Auto", "Manual"],
    }


async def test_discovery_omits_or_includes_optimistic_and_templates() -> None:
    _, optimistic = bound(
        RecordingProvider(),
        unique_id="mode",
        options=[],
        state_enabled=False,
    )
    assert optimistic.discovery_config() == {
        "uniq_id": "mode",
        "cmd_t": "~/mode/command",
        "ops": [],
    }

    _, configured = bound(
        RecordingProvider(),
        unique_id="mode",
        options=["Auto"],
        optimistic=True,
        command_template="{{ value }}",
        value_template="{{ value_json.option }}",
    )
    assert configured.discovery_config() == {
        "uniq_id": "mode",
        "stat_t": "~/mode/state",
        "cmd_t": "~/mode/command",
        "ops": ["Auto"],
        "opt": True,
        "cmd_tpl": "{{ value }}",
        "val_tpl": "{{ value_json.option }}",
    }


async def test_command_events_preserve_unknown_options_and_subscribe_once() -> None:
    provider = RecordingProvider()
    _, select = bound(provider, unique_id="mode", options=["Auto", "Manual"])
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await select.on_event(collect)
    await select.on_event(collect)
    topic = "homeassistant/device/dev-1/mode/command"
    await provider.deliver(topic, "Manual")
    await provider.deliver(topic, "Unknown")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == [
        "Manual",
        "Manual",
        None,
        None,
    ]
    assert received[2].message == "Unknown"
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"


async def test_options_must_be_strings_and_state_requires_enabled_topic() -> None:
    with pytest.raises(ValueError, match="only strings"):
        SelectEntity(unique_id="mode", options=["Auto", 1])  # type: ignore[list-item]

    provider = RecordingProvider()
    _, select = bound(provider, unique_id="mode", options=["Auto"], state_enabled=False)
    with pytest.raises(ValueError, match="state reporting"):
        await select.set_state("Auto")


async def test_unbound_event_and_device_configuration() -> None:
    select = SelectEntity(unique_id="mode", options=["Auto"])
    with pytest.raises(RuntimeError, match="not bound"):
        await select.set_state("Auto")
    with pytest.raises(RuntimeError, match="not bound"):
        await select.on_event(lambda event: _noop())

    provider = RecordingProvider()
    device, select = bound(provider, unique_id="mode", options=["Auto"])
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"select": {"mode": select.discovery_config()}}


async def _noop() -> None:
    return None
