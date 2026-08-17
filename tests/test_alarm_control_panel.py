"""Tests for AlarmControlPanel using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import AlarmControlPanel, Device, DeviceInfo, Event


def make_bound(
    provider: RecordingProvider, **kwargs: Any
) -> tuple[Device, AlarmControlPanel]:
    panel = AlarmControlPanel(**kwargs)
    device = Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [panel])
    return device, panel


async def test_state_and_discovery_defaults() -> None:
    provider = RecordingProvider()
    _, panel = make_bound(provider, unique_id="alarm")

    await panel.set_state("armed_home")

    assert provider.published == [
        ("homeassistant/device/dev-1/alarm/state", "armed_home", False)
    ]
    assert panel.discovery_config() == {
        "uniq_id": "alarm",
        "p": "alarm_control_panel",
        "cmd_t": "~/alarm/command",
        "stat_t": "~/alarm/state",
    }


async def test_discovery_custom_payloads_codes_and_templates() -> None:
    _, panel = make_bound(
        RecordingProvider(),
        unique_id="alarm",
        payload_arm_home="HOME",
        code_arm_required=True,
        code_disarm_required=True,
        command_template="{{ value }}:{{ code }}",
        value_template="{{ value_json.state }}",
        optimistic=True,
    )

    assert panel.discovery_config() == {
        "uniq_id": "alarm",
        "p": "alarm_control_panel",
        "cmd_t": "~/alarm/command",
        "stat_t": "~/alarm/state",
        "pl_arm_home": "HOME",
        "cod_arm_req": True,
        "cod_dis_req": True,
        "cmd_tpl": "{{ value }}:{{ code }}",
        "val_tpl": "{{ value_json.state }}",
        "opt": True,
    }


async def test_commands_are_subscribed_once_and_mapped() -> None:
    provider = RecordingProvider()
    _, panel = make_bound(provider, unique_id="alarm")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await panel.on_event(collect)
    await panel.on_event(collect)
    await provider.deliver("homeassistant/device/dev-1/alarm/command", "ARM_HOME")
    await provider.deliver("homeassistant/device/dev-1/alarm/command", "UNKNOWN")

    assert len(provider.subscriptions["homeassistant/device/dev-1/alarm/command"]) == 1
    assert [event.state for event in received] == [
        "armed_home",
        "armed_home",
        None,
        None,
    ]
    assert received[0].event_type == "command"
    assert received[0].topic_type == "command_topic"
    assert received[0].message == "ARM_HOME"


async def test_state_validation_and_unbound_errors() -> None:
    panel = AlarmControlPanel(unique_id="alarm")
    with pytest.raises(RuntimeError, match="not bound"):
        await panel.set_state("armed_home")

    provider = RecordingProvider()
    _, panel = make_bound(provider, unique_id="alarm")
    with pytest.raises(ValueError, match="unknown alarm state"):
        await panel.set_state("bad")


async def test_device_configure_includes_alarm_component() -> None:
    provider = RecordingProvider()
    device, panel = make_bound(provider, unique_id="alarm")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"alarm": panel.discovery_config()}
