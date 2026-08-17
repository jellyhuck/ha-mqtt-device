"""Tests for Lock using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Lock


def make_bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Lock]:
    lock = Lock(**kwargs)
    device = Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [lock])
    return device, lock


async def test_state_and_discovery_defaults() -> None:
    provider = RecordingProvider()
    _, lock = make_bound(provider, unique_id="front_door")

    await lock.set_state("locked")

    assert provider.published == [
        ("homeassistant/device/dev-1/front_door/state", "LOCKED", False)
    ]
    assert lock.discovery_config() == {
        "uniq_id": "front_door",
        "p": "lock",
        "cmd_t": "~/front_door/command",
        "stat_t": "~/front_door/state",
    }


async def test_custom_lock_configuration() -> None:
    _, lock = make_bound(
        RecordingProvider(),
        unique_id="front_door",
        payload_lock="CLOSE",
        payload_unlock="OPEN_LATCH",
        payload_open="OPEN_DOOR",
        payload_reset="RESET",
        state_locked="CLOSED",
        code_format=r"[0-9]{4}",
        command_template="{{ value }}:{{ code }}",
        value_template="{{ value_json.state }}",
        optimistic=True,
    )

    assert lock.discovery_config() == {
        "uniq_id": "front_door",
        "p": "lock",
        "cmd_t": "~/front_door/command",
        "stat_t": "~/front_door/state",
        "pl_lock": "CLOSE",
        "pl_unlk": "OPEN_LATCH",
        "pl_open": "OPEN_DOOR",
        "pl_rst": "RESET",
        "stat_locked": "CLOSED",
        "cod_fmt": r"[0-9]{4}",
        "cmd_tpl": "{{ value }}:{{ code }}",
        "val_tpl": "{{ value_json.state }}",
        "opt": True,
    }


async def test_commands_are_subscribed_once_and_mapped() -> None:
    provider = RecordingProvider()
    _, lock = make_bound(provider, unique_id="front_door", payload_open="OPEN")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await lock.on_event(collect)
    await lock.on_event(collect)
    await provider.deliver("homeassistant/device/dev-1/front_door/command", "LOCK")
    await provider.deliver("homeassistant/device/dev-1/front_door/command", "OPEN")
    await provider.deliver("homeassistant/device/dev-1/front_door/command", "OTHER")

    assert (
        len(provider.subscriptions["homeassistant/device/dev-1/front_door/command"])
        == 1
    )
    assert [event.state for event in received] == [
        "lock",
        "lock",
        "open",
        "open",
        None,
        None,
    ]
    assert received[0].message == "LOCK"


async def test_lock_validation_and_unbound_errors() -> None:
    lock = Lock(unique_id="front_door")
    with pytest.raises(RuntimeError, match="not bound"):
        await lock.set_state("locked")

    provider = RecordingProvider()
    _, lock = make_bound(provider, unique_id="front_door")
    with pytest.raises(ValueError, match="unknown lock state"):
        await lock.set_state("bad")
    with pytest.raises(ValueError, match="invalid code_format"):
        Lock(unique_id="bad_lock", code_format="[")


async def test_device_configure_includes_lock_component() -> None:
    provider = RecordingProvider()
    device, lock = make_bound(provider, unique_id="front_door")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"front_door": lock.discovery_config()}
