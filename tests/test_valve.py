"""Tests for Valve using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.valve import Valve


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Valve]:
    valve = Valve(**kwargs)
    device = Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), entities=[valve]
    )
    return device, valve


def collector(events: list[Event]) -> EventCallback:
    async def collect(event: Event) -> None:
        events.append(event)

    return collect


async def test_default_discovery_and_state_commands() -> None:
    provider = RecordingProvider()
    _, valve = bound(provider, unique_id="valve")

    assert valve.discovery_config() == {
        "uniq_id": "valve",
        "p": "valve",
        "stat_t": "~/valve/state",
        "cmd_t": "~/valve/command",
    }
    await valve.set_state("open")
    await valve.open()
    await valve.close()
    assert provider.published == [
        ("homeassistant/device/dev-1/valve/state", "open", False),
        ("homeassistant/device/dev-1/valve/command", "OPEN", False),
        ("homeassistant/device/dev-1/valve/command", "CLOSE", False),
    ]


async def test_custom_discovery_and_optional_stop() -> None:
    _, valve = bound(
        RecordingProvider(),
        unique_id="valve",
        name="Water valve",
        payload_open="OPEN_VALVE",
        payload_close=None,
        payload_stop="STOP",
        state_open="OPEN",
        state_closing="CLOSING",
        optimistic=True,
        value_template="{{ value_json.state }}",
    )
    assert valve.discovery_config() == {
        "uniq_id": "valve",
        "p": "valve",
        "name": "Water valve",
        "stat_t": "~/valve/state",
        "cmd_t": "~/valve/command",
        "pl_open": "OPEN_VALVE",
        "pl_cls": None,
        "stat_open": "OPEN",
        "stat_closing": "CLOSING",
        "pl_stop": "STOP",
        "opt": True,
        "val_tpl": "{{ value_json.state }}",
    }


async def test_position_mode_publishes_and_parses_numeric_and_json() -> None:
    provider = RecordingProvider()
    _, valve = bound(
        provider,
        unique_id="valve",
        reports_position=True,
        position_closed=10,
        position_open=90,
    )
    assert valve.discovery_config() == {
        "uniq_id": "valve",
        "p": "valve",
        "stat_t": "~/valve/state",
        "cmd_t": "~/valve/command",
        "pos": True,
        "pos_clsd": 10,
        "pos_open": 90,
    }
    await valve.open()
    await valve.close()
    await valve.set_position(50)
    assert provider.published == [
        ("homeassistant/device/dev-1/valve/command", "90", False),
        ("homeassistant/device/dev-1/valve/command", "10", False),
        ("homeassistant/device/dev-1/valve/command", "50", False),
    ]

    events: list[Event] = []
    await valve.on_event(collector(events))
    await provider.deliver("homeassistant/device/dev-1/valve/command", "50")
    await provider.deliver(
        "homeassistant/device/dev-1/valve/command",
        json.dumps({"state": "opening", "position": 30}),
    )
    await provider.deliver("homeassistant/device/dev-1/valve/command", "999")
    assert events[0].event_type == "position"
    assert events[0].state == "50"
    assert events[1].state == {"state": "opening", "position": 30}
    assert events[2].state is None


async def test_commands_deliver_canonical_events_and_unknown_values() -> None:
    provider = RecordingProvider()
    _, valve = bound(provider, unique_id="valve", payload_stop="STOP")
    events: list[Event] = []
    await valve.on_event(collector(events))
    await valve.on_event(collector([]))
    await provider.deliver("homeassistant/device/dev-1/valve/command", "OPEN")
    await provider.deliver("homeassistant/device/dev-1/valve/command", "STOP")
    await provider.deliver("homeassistant/device/dev-1/valve/command", "other")
    assert list(provider.subscriptions) == ["homeassistant/device/dev-1/valve/command"]
    assert [event.state for event in events] == ["open", "stop", None]
    assert all(event.event_type == "command" for event in events)
    assert all(event.topic_type == "command_topic" for event in events)


async def test_validation_and_device_configure() -> None:
    provider = RecordingProvider()
    device, valve = bound(provider, unique_id="valve")
    with pytest.raises(ValueError, match="unsupported valve state"):
        await valve.set_state("broken")
    with pytest.raises(ValueError, match="not configured"):
        await valve.stop()
    with pytest.raises(ValueError, match="reports_position"):
        await valve.set_position(50)
    with pytest.raises(ValueError, match="reports_position"):
        Valve(unique_id="valve", reports_position=True, payload_open="OPEN_VALVE")
    with pytest.raises(ValueError, match="must differ"):
        Valve(unique_id="valve", position_closed=5, position_open=5)

    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"valve": valve.discovery_config()}
