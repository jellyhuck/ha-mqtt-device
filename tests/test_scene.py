"""Tests for Scene using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Scene


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Scene]:
    scene = Scene(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [scene]
    ), scene


async def test_activate_publishes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, scene = bound(provider, unique_id="party")

    await scene.activate()

    assert provider.published == [
        ("homeassistant/device/dev-1/party/command", "ON", False)
    ]


async def test_activate_republishes_identical_commands() -> None:
    provider = RecordingProvider()
    _, scene = bound(provider, unique_id="party", payload_on="GO")

    await scene.activate()
    await scene.activate()

    expected = ("homeassistant/device/dev-1/party/command", "GO", False)
    assert provider.published == [expected, expected]


async def test_discovery_is_command_only_and_omits_defaults() -> None:
    _, scene = bound(RecordingProvider(), unique_id="party", name="Party")

    assert scene.command_topic == "homeassistant/device/dev-1/party/command"
    assert scene.discovery_config() == {
        "uniq_id": "party",
        "p": "scene",
        "name": "Party",
        "cmd_t": "homeassistant/device/dev-1/party/command",
    }


async def test_discovery_includes_custom_payload_template_and_availability() -> None:
    _, scene = bound(
        RecordingProvider(),
        unique_id="party",
        payload_on="ACTIVATE",
        command_template="{{ value }}",
        availability_topic="~/availability",
        availability_template="{{ value }}",
        payload_available="ready",
        payload_not_available="lost",
    )

    assert scene.discovery_config() == {
        "uniq_id": "party",
        "p": "scene",
        "cmd_t": "homeassistant/device/dev-1/party/command",
        "pl_on": "ACTIVATE",
        "cmd_tpl": "{{ value }}",
        "avty_t": "homeassistant/device/dev-1/availability",
        "avty_tpl": "{{ value }}",
        "pl_avail": "ready",
        "pl_not_avail": "lost",
    }


async def test_command_events_are_mapped_and_subscribed_once() -> None:
    provider = RecordingProvider()
    _, scene = bound(provider, unique_id="party", payload_on="GO")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await scene.on_event(collect)
    await scene.on_event(collect)
    topic = "homeassistant/device/dev-1/party/command"
    await provider.deliver(topic, "GO")
    await provider.deliver(topic, "OTHER")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == ["on", "on", None, None]
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"
    assert received[0].message == "GO"


async def test_unbound_scene_operations_fail_and_device_configures() -> None:
    scene = Scene(unique_id="party")
    with pytest.raises(RuntimeError, match="not bound"):
        await scene.activate()
    with pytest.raises(RuntimeError, match="not bound"):
        await scene.on_event(lambda event: _noop())

    provider = RecordingProvider()
    device, _scene = bound(provider, unique_id="party")
    await device.configure()
    assert json.loads(provider.published[0][1])["cmps"] == {
        "party": _scene.discovery_config()
    }


async def _noop() -> None:
    return None
