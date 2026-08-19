"""Tests for DateTime using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.date_time import DateTime
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, DateTime]:
    """Build a device and a bound datetime with the given kwargs."""
    entity = DateTime(**entity_kwargs)
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


async def test_set_state_publishes_iso_datetimes_to_state_topic() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    await entity.set_state(datetime(2024, 2, 14, 10, 30, tzinfo=UTC))
    await entity.set_state("2024-02-14 10:30:00")
    await entity.set_state(datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC))

    assert provider.published == [
        ("homeassistant/device/dev-1/alarm/state", "2024-02-14 10:30:00", True),
        ("homeassistant/device/dev-1/alarm/state", "2024-02-14 10:30:00", True),
        ("homeassistant/device/dev-1/alarm/state", "2024-12-31 23:59:59", True),
    ]


async def test_set_state_publishes_timezone_aware_datetime_verbatim() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    # The wall-clock components are published as-is; no timezone conversion.
    await entity.set_state(datetime(2024, 2, 14, 10, 30, 15, tzinfo=UTC))

    assert provider.published == [
        ("homeassistant/device/dev-1/alarm/state", "2024-02-14 10:30:15", True),
    ]


async def test_set_state_rejects_non_canonical_strings() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm")

    for value in (
        "2024-02-14T10:30:00",
        "20240214103000",
        "2024-2-14 10:30:00",
        "2024-13-45 25:99:99",
        "not-a-datetime",
    ):
        with pytest.raises(ValueError, match="datetime value"):
            await entity.set_state(value)


async def test_set_state_rejects_plain_date() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm")

    with pytest.raises(TypeError, match="datetime value"):
        await entity.set_state(date(2024, 2, 14))  # type: ignore[arg-type]


async def test_set_state_requires_binding() -> None:
    entity = DateTime(unique_id="alarm")

    with pytest.raises(RuntimeError, match="not bound"):
        await entity.set_state(datetime(2024, 2, 14, 10, 30, tzinfo=UTC))


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    await entity.set_state(datetime(2024, 2, 14, 10, 30, tzinfo=UTC))

    assert provider.subscriptions == {}


async def test_command_topic_shorthand() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm")

    assert entity.command_topic == "~/alarm/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    await entity.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == ["homeassistant/device/dev-1/alarm/command"]


async def test_on_event_requires_binding() -> None:
    entity = DateTime(unique_id="alarm")

    with pytest.raises(RuntimeError, match="not bound"):
        await entity.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    await entity.on_event(lambda event: _noop())
    await entity.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/alarm/command": [entity._dispatch]
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", "2024-02-14 10:30:00"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", "2024-12-31 23:59:59"
    )

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/alarm/command"
    assert first.message == "2024-02-14 10:30:00"
    assert first.state == "2024-02-14 10:30:00"
    assert second.state == "2024-12-31 23:59:59"


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/alarm/command", "RESET")
    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", "2024-13-45 25:99:99"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", "2024-02-14T10:30:00"
    )

    assert len(received) == 3
    assert [event.state for event in received] == [None, None, None]


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")
    received: list[Event] = []
    await entity.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", b"2024-02-14 10:30:00"
    )

    assert received[0].message == "2024-02-14 10:30:00"
    assert received[0].state == "2024-02-14 10:30:00"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")
    first: list[Event] = []
    second: list[Event] = []
    await entity.on_event(collector(first))
    await entity.on_event(collector(second))

    await provider.deliver(
        "homeassistant/device/dev-1/alarm/command", "2024-02-14 10:30:00"
    )

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, entity = make_bound(provider, unique_id="alarm")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await entity.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.date_time"):
        await provider.deliver(
            "homeassistant/device/dev-1/alarm/command", "2024-02-14 10:30:00"
        )

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm")

    # opt/frc_upd are omitted because they match the discovery defaults.
    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "datetime",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
    }


async def test_discovery_config_includes_name() -> None:
    _, entity = make_bound(
        RecordingProvider(),
        unique_id="alarm",
        name="Morning alarm",
    )

    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "datetime",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
        "name": "Morning alarm",
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm", optimistic=True)

    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "datetime",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
        "opt": True,
    }


async def test_discovery_config_includes_force_update() -> None:
    _, entity = make_bound(RecordingProvider(), unique_id="alarm", force_update=True)

    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "datetime",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
        "frc_upd": True,
    }


async def test_discovery_config_omits_default_flags() -> None:
    _, entity = make_bound(
        RecordingProvider(),
        unique_id="alarm",
        optimistic=False,
        force_update=False,
    )

    # Both flags match the discovery defaults and are omitted.
    assert entity.discovery_config() == {
        "uniq_id": "alarm",
        "p": "datetime",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        DateTime(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, entity = make_bound(provider, unique_id="alarm", name="Morning alarm")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"alarm": entity.discovery_config()}


async def _noop() -> None:
    return None
