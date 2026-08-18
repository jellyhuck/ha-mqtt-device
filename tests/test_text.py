"""Tests for Text using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Text


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Text]:
    text = Text(**kwargs)
    return Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [text]), text


async def test_set_state_validates_and_publishes_text() -> None:
    provider = RecordingProvider()
    _, text = bound(provider, unique_id="label", min_length=2, max_length=8)

    await text.set_state("hello")

    assert provider.published == [
        ("homeassistant/device/dev-1/label/state", "hello", True)
    ]
    with pytest.raises(ValueError, match="length"):
        await text.set_state("x")
    with pytest.raises(ValueError, match="length"):
        await text.set_state("too-long-value")


async def test_discovery_defaults_and_options() -> None:
    _, defaults = bound(RecordingProvider(), unique_id="label")
    assert defaults.discovery_config() == {
        "uniq_id": "label",
        "p": "text",
        "stat_t": "~/label/state",
        "cmd_t": "~/label/command",
    }

    _, configured = bound(
        RecordingProvider(),
        unique_id="password",
        min_length=1,
        max_length=20,
        mode="password",
        pattern=r"[A-Z]+",
        command_template="{{ value }}",
        value_template="{{ value_json.text }}",
    )
    assert configured.discovery_config() == {
        "uniq_id": "password",
        "p": "text",
        "stat_t": "~/password/state",
        "cmd_t": "~/password/command",
        "max": 20,
        "min": 1,
        "mode": "password",
        "ptrn": r"[A-Z]+",
        "cmd_tpl": "{{ value }}",
        "val_tpl": "{{ value_json.text }}",
    }


async def test_command_events_validate_values_and_subscribe_once() -> None:
    provider = RecordingProvider()
    _, text = bound(
        provider, unique_id="label", min_length=2, max_length=8, pattern=r"[A-Z]+"
    )
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await text.on_event(collect)
    await text.on_event(collect)
    topic = "homeassistant/device/dev-1/label/command"
    await provider.deliver(topic, "HELLO")
    await provider.deliver(topic, "bad")
    await provider.deliver(topic, "X")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == [
        "HELLO",
        "HELLO",
        None,
        None,
        None,
        None,
    ]
    assert received[2].message == "bad"
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"


async def test_configuration_validation_and_state_can_be_disabled() -> None:
    with pytest.raises(ValueError, match="min_length"):
        Text(unique_id="label", min_length=5, max_length=2)
    with pytest.raises(ValueError, match="mode"):
        Text(unique_id="label", mode="multiline")
    with pytest.raises(ValueError, match="invalid text pattern"):
        Text(unique_id="label", pattern="[")

    provider = RecordingProvider()
    _, text = bound(provider, unique_id="label", state_enabled=False, min_length=0)
    assert text.discovery_config() == {
        "uniq_id": "label",
        "p": "text",
        "cmd_t": "~/label/command",
    }
    with pytest.raises(ValueError, match="state reporting"):
        await text.set_state("value")


async def test_unbound_and_device_configuration() -> None:
    text = Text(unique_id="label")
    with pytest.raises(RuntimeError, match="not bound"):
        await text.set_state("value")
    with pytest.raises(RuntimeError, match="not bound"):
        await text.on_event(lambda event: _noop())

    provider = RecordingProvider()
    device, text = bound(provider, unique_id="label")
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"label": text.discovery_config()}


async def _noop() -> None:
    return None
