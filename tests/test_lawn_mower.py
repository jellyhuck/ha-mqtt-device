"""Tests for LawnMower using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.lawn_mower import LawnMower
from ha_mqtt_device.provider import Message, MqttMessageCallback


class RecordingProvider:
    """Minimal structural MqttProvider that records publishes and subscriptions."""

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

    async def deliver(self, topic: str, payload: str | bytes) -> None:
        """Invoke every callback registered for ``topic`` with ``payload``."""
        raw = payload.encode() if isinstance(payload, str) else payload
        for callback in self.subscriptions.get(topic, []):
            await callback(Message(topic=topic, payload=raw))


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, LawnMower]:
    """Build a device and a bound lawn mower with the given kwargs."""
    mower = LawnMower(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[mower],
    )
    return device, mower


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_plain_activity_to_state_topic() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    await mower.set_state("mowing")
    await mower.set_state("docked")

    assert provider.published == [
        ("homeassistant/device/dev-1/mower_1/state", "mowing"),
        ("homeassistant/device/dev-1/mower_1/state", "docked"),
    ]


async def test_set_state_rejects_unknown_activity() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    with pytest.raises(ValueError, match="must be one of"):
        await mower.set_state("custom_activity")


async def test_set_state_uses_custom_state_payloads() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(
        provider, unique_id="mower_1", state_mowing="MOWING", state_docked="DOCKED"
    )

    await mower.set_state("mowing")
    await mower.set_state("docked")

    assert provider.published == [
        ("homeassistant/device/dev-1/mower_1/state", "MOWING"),
        ("homeassistant/device/dev-1/mower_1/state", "DOCKED"),
    ]


async def test_set_state_requires_binding() -> None:
    mower = LawnMower(unique_id="mower_1")

    with pytest.raises(RuntimeError, match="not bound"):
        await mower.set_state("mowing")


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    await mower.set_state("mowing")

    assert provider.subscriptions == {}


async def test_state_and_command_topic_shorthand() -> None:
    _, mower = make_bound(RecordingProvider(), unique_id="mower_1")

    assert mower.state_topic == "~/mower_1/state"
    assert mower.command_topic == "~/mower_1/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    await mower.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == ["homeassistant/device/dev-1/mower_1/command"]


async def test_on_event_requires_binding() -> None:
    mower = LawnMower(unique_id="mower_1")

    with pytest.raises(RuntimeError, match="not bound"):
        await mower.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    await mower.on_event(lambda event: _noop())
    await mower.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/mower_1/command": [mower._dispatch]
    }


async def test_dispatch_delivers_plain_command_events() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")
    received: list[Event] = []
    await mower.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/mower_1/command", "start_mowing")
    await provider.deliver("homeassistant/device/dev-1/mower_1/command", "pause")
    await provider.deliver("homeassistant/device/dev-1/mower_1/command", "dock")

    assert len(received) == 3
    states = [event.state for event in received]
    topic_types = [event.topic_type for event in received]
    assert states == ["start_mowing", "pause", "dock"]
    assert topic_types == [
        "start_mowing_command_topic",
        "pause_command_topic",
        "dock_command_topic",
    ]
    first = received[0]
    assert first.event_type == "command"
    assert first.topic == "homeassistant/device/dev-1/mower_1/command"
    assert first.message == "start_mowing"


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")
    received: list[Event] = []
    await mower.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/mower_1/command", '{"activity": "unknown"}'
    )
    await provider.deliver("homeassistant/device/dev-1/mower_1/command", "not json")

    assert len(received) == 2
    assert received[0].message == '{"activity": "unknown"}'
    assert received[0].state is None
    assert received[1].state is None


async def test_dispatch_accepts_legacy_json_command_payload() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")
    received: list[Event] = []
    await mower.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/mower_1/command",
        '{"activity": "start_mowing"}',
    )

    assert received[0].state == "start_mowing"


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")
    received: list[Event] = []
    await mower.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/mower_1/command",
        b'{"activity": "start_mowing"}',
    )

    assert received[0].message == '{"activity": "start_mowing"}'
    assert received[0].state == "start_mowing"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")
    first: list[Event] = []
    second: list[Event] = []
    await mower.on_event(collector(first))
    await mower.on_event(collector(second))

    await provider.deliver(
        "homeassistant/device/dev-1/mower_1/command",
        '{"activity": "pause"}',
    )

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, mower = make_bound(provider, unique_id="mower_1")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await mower.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.lawn_mower"):
        await provider.deliver(
            "homeassistant/device/dev-1/mower_1/command",
            '{"activity": "dock"}',
        )

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, mower = make_bound(RecordingProvider(), unique_id="mower_1")

    # pl_strt/pl_pau/pl_doc and sta_mow/sta_pau/sta_doc/sta_err are omitted
    # because they match the discovery defaults.
    assert mower.discovery_config() == {
        "uniq_id": "mower_1",
        "p": "lawn_mower",
        "activity_state_topic": "~/mower_1/state",
        "start_mowing_command_topic": "~/mower_1/command",
        "pause_command_topic": "~/mower_1/command",
        "dock_command_topic": "~/mower_1/command",
    }


async def test_discovery_config_includes_name() -> None:
    _, mower = make_bound(
        RecordingProvider(),
        unique_id="mower_1",
        name="Lawn Mower",
    )

    assert mower.discovery_config() == {
        "uniq_id": "mower_1",
        "p": "lawn_mower",
        "activity_state_topic": "~/mower_1/state",
        "start_mowing_command_topic": "~/mower_1/command",
        "pause_command_topic": "~/mower_1/command",
        "dock_command_topic": "~/mower_1/command",
        "name": "Lawn Mower",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, mower = make_bound(
        RecordingProvider(),
        unique_id="mower_1",
        payload_start_mowing='{"cmd": "start"}',
        payload_pause='{"cmd": "pause"}',
        payload_dock='{"cmd": "dock"}',
    )

    assert mower.discovery_config() == {
        "uniq_id": "mower_1",
        "p": "lawn_mower",
        "activity_state_topic": "~/mower_1/state",
        "start_mowing_command_topic": "~/mower_1/command",
        "pause_command_topic": "~/mower_1/command",
        "dock_command_topic": "~/mower_1/command",
        "pl_strt": '{"cmd": "start"}',
        "pl_pau": '{"cmd": "pause"}',
        "pl_doc": '{"cmd": "dock"}',
    }


async def test_discovery_config_includes_custom_states() -> None:
    _, mower = make_bound(
        RecordingProvider(),
        unique_id="mower_1",
        state_mowing="MOWING",
        state_paused="PAUSED",
        state_docked="DOCKED",
        state_error="ERROR",
    )

    assert mower.discovery_config() == {
        "uniq_id": "mower_1",
        "p": "lawn_mower",
        "activity_state_topic": "~/mower_1/state",
        "start_mowing_command_topic": "~/mower_1/command",
        "pause_command_topic": "~/mower_1/command",
        "dock_command_topic": "~/mower_1/command",
        "sta_mow": "MOWING",
        "sta_pau": "PAUSED",
        "sta_doc": "DOCKED",
        "sta_err": "ERROR",
    }


async def test_discovery_config_omits_states_matching_defaults() -> None:
    _, mower = make_bound(
        RecordingProvider(),
        unique_id="mower_1",
        state_mowing="mowing",
        state_paused="paused",
    )

    # state_mowing/state_paused match the defaults and are omitted.
    assert mower.discovery_config() == {
        "uniq_id": "mower_1",
        "p": "lawn_mower",
        "activity_state_topic": "~/mower_1/state",
        "start_mowing_command_topic": "~/mower_1/command",
        "pause_command_topic": "~/mower_1/command",
        "dock_command_topic": "~/mower_1/command",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        LawnMower(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, mower = make_bound(provider, unique_id="mower_1", name="Lawn Mower")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"mower_1": mower.discovery_config()}


async def _noop() -> None:
    return None
