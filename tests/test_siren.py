"""Tests for Siren using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Siren


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Siren]:
    siren = Siren(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [siren]
    ), siren


async def test_state_and_feature_commands_publish_json_to_resolved_topics() -> None:
    provider = RecordingProvider()
    _, siren = bound(
        provider,
        unique_id="alarm",
        available_tones=["bell", "siren"],
    )

    await siren.set_state(True, tone="bell", duration=10, volume_level=0.5)
    await siren.set_tone("siren")
    await siren.set_duration(20)
    await siren.set_volume(1.0)

    assert provider.published[0][0] == "homeassistant/device/dev-1/alarm/state"
    assert json.loads(provider.published[0][1]) == {
        "state": "ON",
        "tone": "bell",
        "duration": 10,
        "volume_level": 0.5,
    }
    assert [topic for topic, _, _ in provider.published[1:]] == [
        "homeassistant/device/dev-1/alarm/command",
        "homeassistant/device/dev-1/alarm/command",
        "homeassistant/device/dev-1/alarm/command",
    ]
    assert json.loads(provider.published[1][1]) == {"tone": "siren"}
    assert json.loads(provider.published[2][1]) == {"duration": 20}
    assert json.loads(provider.published[3][1]) == {"volume_level": 1.0}


async def test_discovery_defaults_omit_documented_defaults() -> None:
    _, siren = bound(RecordingProvider(), unique_id="alarm")

    assert siren.discovery_config() == {
        "uniq_id": "alarm",
        "p": "siren",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
    }


async def test_discovery_includes_features_templates_payloads_and_availability() -> (
    None
):
    _, siren = bound(
        RecordingProvider(),
        unique_id="alarm",
        available_tones=["bell"],
        support_duration=False,
        support_volume_set=False,
        command_template="{{ value }}",
        command_off_template="OFF",
        value_template="{{ value_json.state }}",
        state_value_template="{{ value_json.state }}",
        payload_on="START",
        payload_off="STOP",
        state_on="RUNNING",
        state_off="IDLE",
        availability_topic="~/availability",
        availability_template="{{ value }}",
        payload_available="ready",
        payload_not_available="lost",
        optimistic=True,
    )

    assert siren.discovery_config() == {
        "uniq_id": "alarm",
        "p": "siren",
        "stat_t": "homeassistant/device/dev-1/alarm/state",
        "cmd_t": "homeassistant/device/dev-1/alarm/command",
        "av_tones": ["bell"],
        "cmd_tpl": "{{ value }}",
        "cmd_off_tpl": "OFF",
        "val_tpl": "{{ value_json.state }}",
        "stat_val_tpl": "{{ value_json.state }}",
        "sup_dur": False,
        "sup_vol": False,
        "pl_on": "START",
        "pl_off": "STOP",
        "stat_on": "RUNNING",
        "stat_off": "IDLE",
        "opt": True,
        "avty_t": "homeassistant/device/dev-1/availability",
        "avty_tpl": "{{ value }}",
        "pl_avail": "ready",
        "pl_not_avail": "lost",
    }


async def test_commands_are_subscribed_once_and_json_events_are_preserved() -> None:
    provider = RecordingProvider()
    _, siren = bound(provider, unique_id="alarm")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await siren.on_event(collect)
    await siren.on_event(collect)
    topic = "homeassistant/device/dev-1/alarm/command"
    await provider.deliver(topic, '{"state":"ON","tone":"bell"}')
    await provider.deliver(topic, "OFF")
    await provider.deliver(topic, "UNKNOWN")

    assert len(provider.subscriptions[topic]) == 1
    assert received[0].state == {"state": "ON", "tone": "bell"}
    assert received[1].state == received[0].state
    assert received[2].state == "off"
    assert received[3].state == "off"
    assert received[4].state is None
    assert received[5].state is None
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"
    assert received[0].message == '{"state":"ON","tone":"bell"}'


async def test_siren_validation_and_disabled_features() -> None:
    provider = RecordingProvider()
    _, siren = bound(
        provider,
        unique_id="alarm",
        available_tones=["bell"],
        support_duration=False,
        support_volume_set=False,
    )
    with pytest.raises(ValueError, match="not in available_tones"):
        await siren.set_tone("other")
    with pytest.raises(ValueError, match="duration support"):
        await siren.set_duration(1)
    with pytest.raises(ValueError, match="volume support"):
        await siren.set_volume(0.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        await Siren(unique_id="other").set_volume(2.0)


async def test_unbound_operations_and_device_configuration() -> None:
    siren = Siren(unique_id="alarm")
    with pytest.raises(RuntimeError, match="not bound"):
        await siren.set_state(True)
    with pytest.raises(RuntimeError, match="not bound"):
        await siren.on_event(lambda event: _noop())

    provider = RecordingProvider()
    device, siren = bound(provider, unique_id="alarm")
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"alarm": siren.discovery_config()}


async def _noop() -> None:
    return None
