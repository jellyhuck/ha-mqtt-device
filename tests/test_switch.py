"""Tests for Switch using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.switch import Switch


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Switch]:
    """Build a device and a bound switch with the given kwargs."""
    switch = Switch(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[switch],
    )
    return device, switch


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")

    await switch.set_state(True)
    await switch.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/relay_1/state", "ON", True),
        ("homeassistant/device/dev-1/relay_1/state", "OFF", True),
    ]


async def test_set_state_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(
        provider, unique_id="relay_1", payload_on="1", payload_off="0"
    )

    await switch.set_state(True)
    await switch.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/relay_1/state", "1", True),
        ("homeassistant/device/dev-1/relay_1/state", "0", True),
    ]


async def test_set_state_requires_binding() -> None:
    switch = Switch(unique_id="relay_1")

    with pytest.raises(RuntimeError, match="not bound"):
        await switch.set_state(True)


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")

    await switch.set_state(True)

    assert provider.subscriptions == {}


async def test_state_and_command_topics_are_resolved() -> None:
    _, switch = make_bound(RecordingProvider(), unique_id="relay_1")

    assert switch.state_topic == switch._state_value.topic().topic
    assert switch.command_topic == "homeassistant/device/dev-1/relay_1/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")

    await switch.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/relay_1/command"
    ]


async def test_on_event_requires_binding() -> None:
    switch = Switch(unique_id="relay_1")

    with pytest.raises(RuntimeError, match="not bound"):
        await switch.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")

    await switch.on_event(lambda event: _noop())
    await switch.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/relay_1/command": [switch._dispatch]
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")
    received: list[Event] = []
    await switch.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "ON")
    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "OFF")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/relay_1/command"
    assert first.message == "ON"
    assert first.state == "on"
    assert second.state == "off"


async def test_dispatch_uses_command_mapping() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(
        provider,
        unique_id="relay_1",
        command_on="TURN_ON",
        command_off="TURN_OFF",
    )
    received: list[Event] = []
    await switch.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "TURN_ON")
    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "TURN_OFF")
    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "ON")

    assert [event.state for event in received] == ["on", "off", None]


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")
    received: list[Event] = []
    await switch.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "TOGGLE")

    assert len(received) == 1
    assert received[0].message == "TOGGLE"
    assert received[0].state is None


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")
    received: list[Event] = []
    await switch.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/relay_1/command", b"ON")

    assert received[0].message == "ON"
    assert received[0].state == "on"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")
    first: list[Event] = []
    second: list[Event] = []
    await switch.on_event(collector(first))
    await switch.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/relay_1/command", "ON")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, switch = make_bound(provider, unique_id="relay_1")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await switch.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.switch"):
        await provider.deliver("homeassistant/device/dev-1/relay_1/command", "ON")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, switch = make_bound(RecordingProvider(), unique_id="relay_1")

    # pl_on/pl_off are omitted because they match the discovery defaults.
    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, switch = make_bound(
        RecordingProvider(),
        unique_id="relay_1",
        name="Relay",
        device_class="outlet",
    )

    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
        "name": "Relay",
        "dev_cla": "outlet",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, switch = make_bound(
        RecordingProvider(),
        unique_id="relay_1",
        payload_on="1",
        payload_off="0",
    )

    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
        "pl_on": "1",
        "pl_off": "0",
    }


async def test_discovery_config_includes_state_and_command_mapping() -> None:
    _, switch = make_bound(
        RecordingProvider(),
        unique_id="relay_1",
        state_on="HIGH",
        state_off="LOW",
        command_on="ON_CMD",
        command_off="OFF_CMD",
    )

    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
        "stat_on": "HIGH",
        "stat_off": "LOW",
        "cmd_on": "ON_CMD",
        "cmd_off": "OFF_CMD",
    }


async def test_discovery_config_omits_mapping_matching_payloads() -> None:
    _, switch = make_bound(
        RecordingProvider(),
        unique_id="relay_1",
        state_on="ON",
        command_on="ON",
    )

    # stat_on/cmd_on match payload_on and are omitted; nothing is emitted.
    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, switch = make_bound(RecordingProvider(), unique_id="relay_1", optimistic=True)

    assert switch.discovery_config() == {
        "uniq_id": "relay_1",
        "p": "switch",
        "stat_t": "homeassistant/device/dev-1/relay_1/state",
        "cmd_t": "homeassistant/device/dev-1/relay_1/command",
        "opt": True,
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Switch(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, switch = make_bound(provider, unique_id="relay_1", name="Relay")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"relay_1": switch.discovery_config()}


async def _noop() -> None:
    return None
