"""Tests for Date using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest

from ha_mqtt_device.date import Date
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
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
) -> tuple[Device, Date]:
    """Build a device and a bound date with the given kwargs."""
    entity = Date(**entity_kwargs)
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


async def test_set_state_publishes_iso_dates_to_state_topic() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")

    await entity.set_state(date(2024, 2, 14))
    await entity.set_state("2024-02-14")
    await entity.set_state(date(2024, 12, 31))

    assert provider.published == [
        ("homeassistant/device/dev-1/vacation/state", "2024-02-14"),
        ("homeassistant/device/dev-1/vacation/state", "2024-02-14"),
        ("homeassistant/device/dev-1/vacation/state", "2024-12-31"),
    ]


async def test_set_state_rejects_non_canonical_strings() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation")

    for value in ("20240214", "2024-2-14", "2024-13-45", "not-a-date"):
        with pytest.raises(ValueError, match="date value"):
            await entity.set_state(value)


async def test_set_state_rejects_datetime() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation")

    with pytest.raises(TypeError, match="date value"):
        await entity.set_state(datetime(2024, 2, 14, 12, 30, tzinfo=UTC))


async def test_set_state_requires_binding() -> None:
    entity = Date(unique_id="vacation")

    with pytest.raises(RuntimeError, match="not bound"):
        await entity.set_state(date(2024, 2, 14))


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")

    await entity.set_state(date(2024, 2, 14))

    assert provider.subscriptions == {}


async def test_command_topic_shorthand() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation")

    assert entity.command_topic == "~/vacation/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")

    await entity.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/vacation/command"
    ]


async def test_on_event_requires_binding() -> None:
    entity = Date(unique_id="vacation")

    with pytest.raises(RuntimeError, match="not bound"):
        await entity.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")

    await entity.on_event(lambda event: _noop())
    await entity.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/vacation/command": [entity._dispatch]
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/vacation/command", "2024-02-14")
    await provider.deliver("homeassistant/device/dev-1/vacation/command", "2024-12-31")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/vacation/command"
    assert first.message == "2024-02-14"
    assert first.state == "2024-02-14"
    assert second.state == "2024-12-31"


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/vacation/command", "RESET")
    await provider.deliver("homeassistant/device/dev-1/vacation/command", "2024-13-45")
    await provider.deliver("homeassistant/device/dev-1/vacation/command", "20240214")

    assert len(received) == 3
    assert [event.state for event in received] == [None, None, None]


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/vacation/command", b"2024-02-14")

    assert received[0].message == "2024-02-14"
    assert received[0].state == "2024-02-14"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")
    first: list[Event] = []
    second: list[Event] = []
    await entity.on_event(collector(first))
    await entity.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/vacation/command", "2024-02-14")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="vacation")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await entity.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.date"):
        await provider.deliver(
            "homeassistant/device/dev-1/vacation/command", "2024-02-14"
        )

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation")

    # opt/frc_upd are omitted because they match the discovery defaults.
    assert entity.discovery_config() == {
        "uniq_id": "vacation",
        "p": "~/vacation/state",
        "cmd_t": "~/vacation/command",
    }


async def test_discovery_config_includes_name() -> None:
    _, entity = make_bound(
        RecordingProvider(),
        unique_id="vacation",
        name="Vacation start",
    )

    assert entity.discovery_config() == {
        "uniq_id": "vacation",
        "p": "~/vacation/state",
        "cmd_t": "~/vacation/command",
        "name": "Vacation start",
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation", optimistic=True)

    assert entity.discovery_config() == {
        "uniq_id": "vacation",
        "p": "~/vacation/state",
        "cmd_t": "~/vacation/command",
        "opt": True,
    }


async def test_discovery_config_includes_force_update() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="vacation", force_update=True)

    assert entity.discovery_config() == {
        "uniq_id": "vacation",
        "p": "~/vacation/state",
        "cmd_t": "~/vacation/command",
        "frc_upd": True,
    }


async def test_discovery_config_omits_default_flags() -> None:
    _, entity = make_bound(
        RecordingProvider(),
        unique_id="vacation",
        optimistic=False,
        force_update=False,
    )

    # Both flags match the discovery defaults and are omitted.
    assert entity.discovery_config() == {
        "uniq_id": "vacation",
        "p": "~/vacation/state",
        "cmd_t": "~/vacation/command",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Date(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, entity = make_bound(provider, unique_id="vacation", name="Vacation start")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"date": {"vacation": entity.discovery_config()}}


async def _noop() -> None:
    return None
