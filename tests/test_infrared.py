"""Tests for InfraredEmitter and InfraredReceiver using a recording fake MqttProvider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.infrared import InfraredEmitter, InfraredReceiver


def make_bound(
    provider: RecordingProvider, cls: type, **entity_kwargs: Any
) -> tuple[Device, Any]:
    """Build a device and a bound infrared entity of ``cls`` with the given kwargs."""
    entity = cls(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[entity],
    )
    return device, entity


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


# --- InfraredEmitter --------------------------------------------------------


async def test_command_topic_shorthand() -> None:
    _, emitter = make_bound(RecordingProvider(), InfraredEmitter, unique_id="tv_power")

    assert emitter.command_topic == "~/tv_power/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")

    await emitter.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/tv_power/command"
    ]


async def test_on_event_requires_binding() -> None:
    emitter = InfraredEmitter(unique_id="tv_power")

    with pytest.raises(RuntimeError, match="not bound"):
        await emitter.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")

    await emitter.on_event(lambda event: _noop())
    await emitter.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/tv_power/command": [emitter._dispatch]
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    received: list[Event] = []
    await emitter.on_event(collector(received))

    payload = json.dumps(
        {"timings": [9000, -4500, 562, -1687], "modulation": 38000, "repeat_count": 0}
    )
    await provider.deliver("homeassistant/device/dev-1/tv_power/command", payload)

    assert len(received) == 1
    event = received[0]
    assert event.event_type == "command"
    assert event.topic_type == "command_topic"
    assert event.topic == "homeassistant/device/dev-1/tv_power/command"
    assert event.message == payload
    assert event.state == {
        "timings": [9000, -4500, 562, -1687],
        "modulation": 38000,
        "repeat_count": 0,
    }


async def test_dispatch_parses_minimal_signal() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    received: list[Event] = []
    await emitter.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/tv_power/command",
        json.dumps({"timings": [9000, -4500]}),
    )

    assert received[0].state == {"timings": [9000, -4500]}


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    received: list[Event] = []
    await emitter.on_event(collector(received))

    payload = "not-json-or-a-signal"
    await provider.deliver("homeassistant/device/dev-1/tv_power/command", payload)

    assert len(received) == 1
    assert received[0].message == payload
    assert received[0].state is None


async def test_dispatch_rejects_signal_without_timings() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    received: list[Event] = []
    await emitter.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/tv_power/command",
        json.dumps({"modulation": 38000}),
    )

    assert received[0].state is None


async def test_dispatch_rejects_empty_and_boolean_signal_values() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    received: list[Event] = []
    await emitter.on_event(collector(received))

    signals: tuple[dict[str, object], ...] = (
        {"timings": []},
        {"timings": [True]},
        {"timings": [9000, -4500], "modulation": True},
    )
    for signal in signals:
        await provider.deliver(
            "homeassistant/device/dev-1/tv_power/command", json.dumps(signal)
        )

    assert [event.state for event in received] == [None, None, None]


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")
    first: list[Event] = []
    second: list[Event] = []
    await emitter.on_event(collector(first))
    await emitter.on_event(collector(second))

    payload = json.dumps({"timings": [9000, -4500]})
    await provider.deliver("homeassistant/device/dev-1/tv_power/command", payload)

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, emitter = make_bound(provider, InfraredEmitter, unique_id="tv_power")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await emitter.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.infrared"):
        await provider.deliver(
            "homeassistant/device/dev-1/tv_power/command",
            json.dumps({"timings": [9000, -4500]}),
        )

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, emitter = make_bound(RecordingProvider(), InfraredEmitter, unique_id="tv_power")

    assert emitter.discovery_config() == {
        "uniq_id": "tv_power",
        "p": "infrared",
        "cmd_t": "~/tv_power/command",
        "schema": "emitter",
    }


async def test_discovery_config_includes_name() -> None:
    _, emitter = make_bound(
        RecordingProvider(), InfraredEmitter, unique_id="tv_power", name="TV power"
    )

    assert emitter.discovery_config() == {
        "uniq_id": "tv_power",
        "p": "infrared",
        "cmd_t": "~/tv_power/command",
        "schema": "emitter",
        "name": "TV power",
    }


# --- InfraredReceiver -------------------------------------------------------


async def test_set_state_publishes_json_to_state_topic() -> None:
    provider = RecordingProvider()
    _, receiver = make_bound(provider, InfraredReceiver, unique_id="living_room_ir")

    signal = {"timings": [9000, -4500, 562, -1687], "modulation": 38000}
    await receiver.set_state(signal)

    assert provider.published == [
        ("homeassistant/device/dev-1/living_room_ir/state", json.dumps(signal), False)
    ]


async def test_set_state_rejects_missing_timings() -> None:
    provider = RecordingProvider()
    _, receiver = make_bound(provider, InfraredReceiver, unique_id="living_room_ir")

    with pytest.raises(ValueError, match="timings"):
        await receiver.set_state({"modulation": 38000})
    with pytest.raises(ValueError, match="timings"):
        await receiver.set_state({"timings": []})
    with pytest.raises(TypeError, match="modulation"):
        await receiver.set_state({"timings": [9000, -4500], "modulation": True})


async def test_set_state_rejects_non_dict() -> None:
    provider = RecordingProvider()
    _, receiver = make_bound(provider, InfraredReceiver, unique_id="living_room_ir")

    with pytest.raises(TypeError, match="dict"):
        await receiver.set_state("not a dict")


async def test_set_state_requires_binding() -> None:
    receiver = InfraredReceiver(unique_id="living_room_ir")

    with pytest.raises(RuntimeError, match="not bound"):
        await receiver.set_state({"timings": [9000, -4500]})


async def test_receiver_discovery_config_defaults() -> None:
    _, receiver = make_bound(
        RecordingProvider(), InfraredReceiver, unique_id="living_room_ir"
    )

    assert receiver.discovery_config() == {
        "uniq_id": "living_room_ir",
        "p": "infrared",
        "stat_t": "~/living_room_ir/state",
        "schema": "receiver",
    }


async def test_receiver_discovery_config_includes_name() -> None:
    _, receiver = make_bound(
        RecordingProvider(),
        InfraredReceiver,
        unique_id="living_room_ir",
        name="Living room IR",
    )

    assert receiver.discovery_config() == {
        "uniq_id": "living_room_ir",
        "p": "infrared",
        "stat_t": "~/living_room_ir/state",
        "schema": "receiver",
        "name": "Living room IR",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        InfraredEmitter(unique_id="bad id!")


async def test_configure_includes_cmps_for_emitter() -> None:
    provider = RecordingProvider()
    device, emitter = make_bound(
        provider, InfraredEmitter, unique_id="tv_power", name="TV power"
    )

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"tv_power": emitter.discovery_config()}


async def test_configure_includes_cmps_for_receiver() -> None:
    provider = RecordingProvider()
    device, receiver = make_bound(
        provider, InfraredReceiver, unique_id="living_room_ir", name="Living room IR"
    )

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"living_room_ir": receiver.discovery_config()}


async def _noop() -> None:
    return None
