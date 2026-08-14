"""Tests for TagScanner using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device import Device, DeviceInfo, Event, TagScanner
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


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, TagScanner]:
    scanner = TagScanner(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [scanner]
    ), scanner


async def test_scan_publishes_to_resolved_topic() -> None:
    provider = RecordingProvider()
    _, scanner = bound(provider, unique_id="scanner", topic="~/tags")

    await scanner.scan("E9F35959")

    assert provider.published == [("homeassistant/device/dev-1/tags", "E9F35959")]


async def test_standalone_discovery_contains_tag_topic_template_and_device() -> None:
    provider = RecordingProvider()
    device, scanner = bound(
        provider,
        unique_id="scanner",
        topic="~/tags",
        value_template="{{ value_json.uid }}",
        node_id="node-1",
    )

    await device.configure()

    assert json.loads(provider.published[0][1]) == {
        "dev": {"ids": ["dev-1"], "name": "Device"},
        "o": {"name": "ha-mqtt-device"},
        "avty": [{"topic": "~/status"}],
        "~": "homeassistant/device/dev-1",
    }
    assert provider.published[1][0] == ("homeassistant/tag/node-1/scanner/config")
    assert json.loads(provider.published[1][1]) == {
        "t": "~/tags",
        "val_tpl": "{{ value_json.uid }}",
        "dev": {"ids": ["dev-1"], "name": "Device"},
    }
    await device.remove()
    assert provider.published[2] == (
        "homeassistant/device/dev-1/config",
        "",
    )
    assert provider.published[3] == (
        "homeassistant/tag/node-1/scanner/config",
        "",
    )
    assert scanner.standalone_discovery is True


async def test_scan_events_preserve_raw_payload_and_subscribe_once() -> None:
    provider = RecordingProvider()
    _, scanner = bound(provider, unique_id="scanner", topic="~/tags")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await scanner.on_event(collect)
    await scanner.on_event(collect)
    topic = "homeassistant/device/dev-1/tags"
    await provider.deliver(topic, "E9F35959")
    await provider.deliver(topic, "")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == ["E9F35959", "E9F35959", "", ""]
    assert received[0].event_type == "scan"
    assert received[0].topic_type == "topic"
    assert received[0].message == "E9F35959"


async def test_topic_is_required_and_unbound_operations_fail() -> None:
    with pytest.raises(ValueError, match="topic is required"):
        TagScanner(unique_id="scanner")

    scanner = TagScanner(unique_id="scanner", topic="tags")
    with pytest.raises(RuntimeError, match="not bound"):
        await scanner.scan("tag")
    with pytest.raises(RuntimeError, match="not bound"):
        await scanner.on_event(lambda event: _noop())


async def _noop() -> None:
    return None
