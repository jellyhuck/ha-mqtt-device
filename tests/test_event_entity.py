"""Tests for EventEntity using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event_entity import EventEntity


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, EventEntity]:
    """Build a device and a bound event entity with the given kwargs."""
    event = EventEntity(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[event],
    )
    return device, event


async def test_set_event_publishes_to_state_topic() -> None:
    provider = RecordingProvider()
    _, doorbell = make_bound(
        provider,
        unique_id="doorbell",
        event_types=["doorbell_pressed", "doorbell_long_press"],
    )

    await doorbell.set_event("doorbell_pressed")
    await doorbell.set_event("doorbell_long_press")

    assert provider.published == [
        ("homeassistant/device/dev-1/doorbell/state", "doorbell_pressed", False),
        ("homeassistant/device/dev-1/doorbell/state", "doorbell_long_press", False),
    ]


async def test_state_topic_is_resolved() -> None:
    _, doorbell = make_bound(
        RecordingProvider(),
        unique_id="doorbell",
        event_types=["doorbell_pressed"],
    )

    assert doorbell.state_topic == "homeassistant/device/dev-1/doorbell/state"


async def test_set_event_republishes_identical_events() -> None:
    provider = RecordingProvider()
    _, doorbell = make_bound(
        provider, unique_id="doorbell", event_types=["doorbell_pressed"]
    )

    await doorbell.set_event("doorbell_pressed")
    await doorbell.set_event("doorbell_pressed")

    expected = ("homeassistant/device/dev-1/doorbell/state", "doorbell_pressed", False)
    assert provider.published == [expected, expected]


async def test_set_event_requires_binding() -> None:
    doorbell = EventEntity(unique_id="doorbell", event_types=["doorbell_pressed"])

    with pytest.raises(RuntimeError, match="not bound"):
        await doorbell.set_event("doorbell_pressed")


async def test_set_event_rejects_undeclared_event_type() -> None:
    provider = RecordingProvider()
    _, doorbell = make_bound(
        provider, unique_id="doorbell", event_types=["doorbell_pressed"]
    )

    with pytest.raises(ValueError, match="not in event_types"):
        await doorbell.set_event("doorbell_long_press")

    assert provider.published == []


async def test_event_types_required() -> None:
    with pytest.raises(ValueError, match="at least one event type"):
        EventEntity(unique_id="doorbell", event_types=[])


async def test_templates_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        EventEntity(
            unique_id="doorbell",
            event_types=["doorbell_pressed"],
            event_type_template="{{ value }}",
            value_template="{{ value }}",
        )


async def test_discovery_config_defaults() -> None:
    _, doorbell = make_bound(
        RecordingProvider(),
        unique_id="doorbell",
        event_types=["doorbell_pressed", "doorbell_long_press"],
    )

    assert doorbell.discovery_config() == {
        "uniq_id": "doorbell",
        "p": "event",
        "stat_t": "homeassistant/device/dev-1/doorbell/state",
        "evt_typ": ["doorbell_pressed", "doorbell_long_press"],
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, doorbell = make_bound(
        RecordingProvider(),
        unique_id="doorbell",
        name="Doorbell",
        device_class="doorbell",
        event_types=["doorbell_pressed"],
    )

    assert doorbell.discovery_config() == {
        "uniq_id": "doorbell",
        "p": "event",
        "stat_t": "homeassistant/device/dev-1/doorbell/state",
        "evt_typ": ["doorbell_pressed"],
        "name": "Doorbell",
        "dev_cla": "doorbell",
    }


async def test_discovery_config_includes_event_type_template() -> None:
    _, doorbell = make_bound(
        RecordingProvider(),
        unique_id="doorbell",
        event_types=["doorbell_pressed"],
        event_type_template="{{ value.split('_')[0] }}",
    )

    assert doorbell.discovery_config() == {
        "uniq_id": "doorbell",
        "p": "event",
        "stat_t": "homeassistant/device/dev-1/doorbell/state",
        "evt_typ": ["doorbell_pressed"],
        "eve_tt": "{{ value.split('_')[0] }}",
    }


async def test_discovery_config_includes_value_template() -> None:
    _, doorbell = make_bound(
        RecordingProvider(),
        unique_id="doorbell",
        event_types=["doorbell_pressed"],
        value_template="{{ value }}",
    )

    assert doorbell.discovery_config() == {
        "uniq_id": "doorbell",
        "p": "event",
        "stat_t": "homeassistant/device/dev-1/doorbell/state",
        "evt_typ": ["doorbell_pressed"],
        "val_tpl": "{{ value }}",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        EventEntity(unique_id="bad id!", event_types=["doorbell_pressed"])


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, doorbell = make_bound(
        provider,
        unique_id="doorbell",
        name="Doorbell",
        event_types=["doorbell_pressed"],
    )

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"doorbell": doorbell.discovery_config()}
