"""Tests for TagScanner using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, TagScanner


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, TagScanner]:
    scanner = TagScanner(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [scanner]
    ), scanner


async def test_scan_publishes_to_resolved_topic() -> None:
    provider = RecordingProvider()
    _, scanner = bound(provider, unique_id="scanner", topic="~/tags")

    await scanner.scan("E9F35959")

    assert provider.published == [
        ("homeassistant/device/dev-1/tags", "E9F35959", False)
    ]


async def test_discovery_contains_tag_topic_and_template() -> None:
    provider = RecordingProvider()
    device, _scanner = bound(
        provider,
        unique_id="scanner",
        topic="~/tags",
        value_template="{{ value_json.uid }}",
    )

    await device.configure()

    assert json.loads(provider.published[0][1]) == {
        "dev": {"ids": ["dev-1"], "name": "Device"},
        "o": {"name": "ha-mqtt-device"},
        "avty": [{"topic": "~/status"}],
        "~": "homeassistant/device/dev-1",
        "cmps": {
            "scanner": {
                "uniq_id": "scanner",
                "p": "tag",
                "t": "~/tags",
                "val_tpl": "{{ value_json.uid }}",
            }
        },
    }
    await device.remove()
    assert provider.published[1] == ("homeassistant/device/dev-1/config", "", True)


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
