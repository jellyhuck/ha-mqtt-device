"""Tests for Cover using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.cover import Cover
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Cover]:
    """Build a device and a bound cover with the given kwargs."""
    cover = Cover(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[cover],
    )
    return device, cover


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_default_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.set_state("open")
    await cover.set_state("closing")
    await cover.set_state("closed")

    assert provider.published == [
        ("homeassistant/device/dev-1/blinds/state", "open", True),
        ("homeassistant/device/dev-1/blinds/state", "closing", True),
        ("homeassistant/device/dev-1/blinds/state", "closed", True),
    ]


async def test_set_state_uses_custom_state_payloads() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(
        provider,
        unique_id="blinds",
        state_open="OPENED",
        state_closed="SHUT",
    )

    await cover.set_state("open")
    await cover.set_state("closed")

    assert provider.published == [
        ("homeassistant/device/dev-1/blinds/state", "OPENED", True),
        ("homeassistant/device/dev-1/blinds/state", "SHUT", True),
    ]


async def test_set_state_requires_binding() -> None:
    cover = Cover(unique_id="blinds")

    with pytest.raises(RuntimeError, match="not bound"):
        await cover.set_state("open")


async def test_set_state_validates_state_name() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    with pytest.raises(ValueError, match="must be one of"):
        await cover.set_state("half")


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.set_state("open")

    assert provider.subscriptions == {}


async def test_set_position_publishes_stringified_value_to_position_topic() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.set_position(75)
    await cover.set_position(0)

    assert provider.published == [
        ("homeassistant/device/dev-1/blinds/state/position", "75", True),
        ("homeassistant/device/dev-1/blinds/state/position", "0", True),
    ]


async def test_retained_state_and_position_suppress_unchanged_values() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.set_state("open")
    await cover.set_state("open")
    await cover.set_position(75)
    await cover.set_position(75)

    assert provider.published == [
        ("homeassistant/device/dev-1/blinds/state", "open", True),
        ("homeassistant/device/dev-1/blinds/state/position", "75", True),
    ]


async def test_set_position_requires_binding() -> None:
    cover = Cover(unique_id="blinds")

    with pytest.raises(RuntimeError, match="not bound"):
        await cover.set_position(50)


async def test_set_position_rejects_values_outside_documented_range() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    with pytest.raises(ValueError, match="outside"):
        await cover.set_position(101)


async def test_dispatch_rejects_position_outside_documented_range() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command/position", "101")

    assert received[0].state is None


async def test_state_topic_is_resolved() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds")

    assert cover.state_topic == "homeassistant/device/dev-1/blinds/state"


async def test_command_topic_is_resolved() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds")

    assert cover.command_topic == "homeassistant/device/dev-1/blinds/command"


async def test_position_topic_is_resolved() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds")

    assert cover.position_topic == "homeassistant/device/dev-1/blinds/state/position"


async def test_set_position_topic_is_resolved() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds")

    assert (
        cover.set_position_topic == "homeassistant/device/dev-1/blinds/command/position"
    )


async def test_on_event_subscribes_to_resolved_command_and_set_position_topics() -> (
    None
):
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/blinds/command",
        "homeassistant/device/dev-1/blinds/command/position",
    ]


async def test_on_event_requires_binding() -> None:
    cover = Cover(unique_id="blinds")

    with pytest.raises(RuntimeError, match="not bound"):
        await cover.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    await cover.on_event(lambda event: _noop())
    await cover.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/blinds/command": [cover._dispatch_command],
        "homeassistant/device/dev-1/blinds/command/position": [
            cover._dispatch_set_position
        ],
    }


async def test_dispatch_delivers_command_events() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command", "OPEN")
    await provider.deliver("homeassistant/device/dev-1/blinds/command", "CLOSE")
    await provider.deliver("homeassistant/device/dev-1/blinds/command", "STOP")

    assert len(received) == 3
    first, second, third = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/blinds/command"
    assert first.message == "OPEN"
    assert first.state == "open"
    assert second.state == "close"
    assert third.state == "stop"


async def test_dispatch_command_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(
        provider,
        unique_id="blinds",
        payload_open="UP",
        payload_close="DOWN",
        payload_stop="HALT",
    )
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command", "UP")
    await provider.deliver("homeassistant/device/dev-1/blinds/command", "DOWN")
    await provider.deliver("homeassistant/device/dev-1/blinds/command", "HALT")
    await provider.deliver("homeassistant/device/dev-1/blinds/command", "OPEN")

    assert [event.state for event in received] == ["open", "close", "stop", None]


async def test_dispatch_delivers_set_position_event() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command/position", "75")

    assert len(received) == 1
    event = received[0]
    assert event.event_type == "set_position"
    assert event.topic_type == "set_position_topic"
    assert event.topic == "homeassistant/device/dev-1/blinds/command/position"
    assert event.message == "75"
    assert event.state == "75"


async def test_dispatch_delivers_unknown_payloads_with_null_state() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command", "TOGGLE")
    await provider.deliver(
        "homeassistant/device/dev-1/blinds/command/position", "RESET"
    )
    await provider.deliver("homeassistant/device/dev-1/blinds/command/position", "12.5")

    assert len(received) == 3
    assert [event.state for event in received] == [None, None, None]
    assert [event.event_type for event in received] == [
        "command",
        "set_position",
        "set_position",
    ]


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    received: list[Event] = []
    await cover.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/blinds/command", b"OPEN")

    assert received[0].message == "OPEN"
    assert received[0].state == "open"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")
    first: list[Event] = []
    second: list[Event] = []
    await cover.on_event(collector(first))
    await cover.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/blinds/command/position", "50")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, cover = make_bound(provider, unique_id="blinds")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await cover.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.cover"):
        await provider.deliver("homeassistant/device/dev-1/blinds/command", "OPEN")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds")

    # The cover's state topic key is ``stat_t`` and pl_open/pl_cls/pl_stop,
    # the state payloads, and the position bounds are
    # omitted because they match the discovery defaults.
    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, cover = make_bound(
        RecordingProvider(),
        unique_id="blinds",
        name="Blinds",
        device_class="blind",
    )

    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
        "name": "Blinds",
        "dev_cla": "blind",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, cover = make_bound(
        RecordingProvider(),
        unique_id="blinds",
        payload_open="UP",
        payload_close="DOWN",
        payload_stop="HALT",
    )

    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
        "pl_open": "UP",
        "pl_cls": "DOWN",
        "pl_stop": "HALT",
    }


async def test_discovery_config_includes_custom_state_payloads() -> None:
    _, cover = make_bound(
        RecordingProvider(),
        unique_id="blinds",
        state_open="OPENED",
        state_opening="OPENING_",
        state_closed="SHUT",
        state_closing="SHUTTING",
        state_stopped="PAUSED",
    )

    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
        "stat_open": "OPENED",
        "stat_opening": "OPENING_",
        "stat_clsd": "SHUT",
        "stat_closing": "SHUTTING",
        "stat_stopped": "PAUSED",
    }


async def test_discovery_config_includes_position_bounds() -> None:
    _, cover = make_bound(
        RecordingProvider(), unique_id="blinds", position_open=50, position_closed=1
    )

    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
        "pos_open": 50,
        "pos_clsd": 1,
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, cover = make_bound(RecordingProvider(), unique_id="blinds", optimistic=True)

    assert cover.discovery_config() == {
        "uniq_id": "blinds",
        "p": "cover",
        "stat_t": "homeassistant/device/dev-1/blinds/state",
        "cmd_t": "homeassistant/device/dev-1/blinds/command",
        "pos_t": "homeassistant/device/dev-1/blinds/state/position",
        "set_pos_t": "homeassistant/device/dev-1/blinds/command/position",
        "opt": True,
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Cover(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, cover = make_bound(provider, unique_id="blinds", name="Blinds")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"blinds": cover.discovery_config()}


async def _noop() -> None:
    return None
