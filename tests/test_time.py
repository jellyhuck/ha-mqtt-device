"""Tests for Time using a recording provider."""

from __future__ import annotations

import json
from datetime import time
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Time


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Time]:
    entity = Time(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [entity]
    ), entity


async def test_set_state_serializes_time_values_deterministically() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="alarm")

    await entity.set_state(time(3, 4))
    await entity.set_state("3:05")
    await entity.set_state("03:06:07")

    assert provider.published == [
        ("homeassistant/device/dev-1/alarm/state", "03:04:00", True),
        ("homeassistant/device/dev-1/alarm/state", "03:05:00", True),
        ("homeassistant/device/dev-1/alarm/state", "03:06:07", True),
    ]


async def test_invalid_time_values_are_rejected() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="alarm")

    with pytest.raises(ValueError):
        await entity.set_state("25:00")
    with pytest.raises(ValueError):
        await entity.set_state("12:60:00")
    with pytest.raises(ValueError):
        await entity.set_state("12:00:00.500")
    with pytest.raises(ValueError, match="fractional"):
        await entity.set_state(time(12, 0, microsecond=1))
    with pytest.raises(TypeError):
        await entity.set_state(12)  # type: ignore[arg-type]


async def test_command_events_normalize_valid_values_and_preserve_unknowns() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="alarm")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await entity.on_event(collect)
    await entity.on_event(collect)
    topic = "homeassistant/device/dev-1/alarm/command"
    await provider.deliver(topic, "3:04")
    await provider.deliver(topic, "not-a-time")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == [
        "03:04:00",
        "03:04:00",
        None,
        None,
    ]
    assert received[0].message == "3:04"
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"


async def test_discovery_options_and_device_configuration() -> None:
    provider = RecordingProvider()
    device, entity = bound(
        provider,
        unique_id="alarm",
        command_template="{{ value }}",
        value_template="{{ value_json.time }}",
    )
    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "time",
        "stat_t": "~/alarm/state",
        "cmd_t": "~/alarm/command",
        "cmd_tpl": "{{ value }}",
        "val_tpl": "{{ value_json.time }}",
    }

    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"alarm": entity.discovery_config()}


async def test_unbound_and_disabled_state_errors() -> None:
    entity = Time(unique_id="alarm")
    with pytest.raises(RuntimeError, match="not bound"):
        await entity.set_state("12:00")
    with pytest.raises(RuntimeError, match="not bound"):
        await entity.on_event(lambda event: _noop())

    provider = RecordingProvider()
    _, disabled = bound(provider, unique_id="alarm", state_enabled=False)
    assert disabled.discovery_config() == {
        "uniq_id": "alarm",
        "p": "time",
        "cmd_t": "~/alarm/command",
    }
    with pytest.raises(ValueError, match="state reporting"):
        await disabled.set_state("12:00")


async def _noop() -> None:
    return None
