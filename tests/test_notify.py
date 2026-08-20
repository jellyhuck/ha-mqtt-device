"""Tests for Notify using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Notify


def make_bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Notify]:
    notify = Notify(**kwargs)
    device = Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [notify])
    return device, notify


async def test_discovery_is_command_only() -> None:
    _, notify = make_bound(RecordingProvider(), unique_id="alerts")

    assert notify.command_topic == "homeassistant/device/dev-1/alerts/command"
    assert notify.discovery_config() == {
        "uniq_id": "alerts",
        "p": "notify",
        "cmd_t": "homeassistant/device/dev-1/alerts/command",
    }


async def test_discovery_includes_template_and_availability_options() -> None:
    _, notify = make_bound(
        RecordingProvider(),
        unique_id="alerts",
        command_template="{{ value_json.message }}",
        availability_topic="~/notify_status",
        availability_template="{{ value }}",
        payload_available="up",
        payload_not_available="down",
    )

    assert notify.discovery_config() == {
        "uniq_id": "alerts",
        "p": "notify",
        "cmd_t": "homeassistant/device/dev-1/alerts/command",
        "cmd_tpl": "{{ value_json.message }}",
        "avty_t": "homeassistant/device/dev-1/notify_status",
        "avty_tpl": "{{ value }}",
        "pl_avail": "up",
        "pl_not_avail": "down",
    }


async def test_messages_are_subscribed_once_and_preserve_payloads() -> None:
    provider = RecordingProvider()
    _, notify = make_bound(provider, unique_id="alerts")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await notify.on_event(collect)
    await notify.on_event(collect)
    topic = "homeassistant/device/dev-1/alerts/command"
    await provider.deliver(topic, '{"message":"hello","title":"Alert"}')
    await provider.deliver(topic, "plain text")

    assert len(provider.subscriptions[topic]) == 1
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"
    assert received[0].state == {"message": "hello", "title": "Alert"}
    assert received[0].message == '{"message":"hello","title":"Alert"}'
    assert received[1].state == {"message": "hello", "title": "Alert"}
    assert received[2].state == "plain text"
    assert received[3].state == "plain text"


async def test_on_event_requires_binding_and_device_configure() -> None:
    notify = Notify(unique_id="alerts")
    with pytest.raises(RuntimeError, match="not bound"):
        await notify.on_event(lambda event: _noop())

    provider = RecordingProvider()
    device, notify = make_bound(provider, unique_id="alerts")
    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"alerts": notify.discovery_config()}


async def _noop() -> None:
    return None
