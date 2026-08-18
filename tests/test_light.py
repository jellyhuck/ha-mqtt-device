"""Tests for Light using a recording fake provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Light


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Light]:
    light = Light(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), entities=[light]
    ), light


async def test_topics_and_publish() -> None:
    provider = RecordingProvider()
    _, light = bound(provider, unique_id="lamp", brightness_enabled=True)
    assert light.command_topic == "~/lamp/command/power"
    assert light.brightness_state_topic == "~/lamp/state/brightness"
    await light.set_state(True)
    await light.set_brightness(50)
    assert provider.published == [
        ("homeassistant/device/dev-1/lamp/state/power", "ON", True),
        ("homeassistant/device/dev-1/lamp/state/brightness", "50", True),
    ]


async def test_on_event_subscribes_enabled_features_and_parses_events() -> None:
    provider = RecordingProvider()
    _, light = bound(
        provider, unique_id="lamp", brightness_enabled=True, rgb_enabled=True
    )
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await light.on_event(collect)
    assert set(provider.subscriptions) == {
        "homeassistant/device/dev-1/lamp/command/power",
        "homeassistant/device/dev-1/lamp/command/brightness",
        "homeassistant/device/dev-1/lamp/command/rgb",
    }
    await provider.deliver("homeassistant/device/dev-1/lamp/command/power", "ON")
    await provider.deliver("homeassistant/device/dev-1/lamp/command/rgb", "1,2,3")
    assert received[0].state == "on"
    assert received[1].event_type == "rgb" and received[1].state == {
        "red": 1,
        "green": 2,
        "blue": 3,
    }


async def test_discovery_config() -> None:
    provider = RecordingProvider()
    device, _light = bound(
        provider,
        unique_id="lamp",
        name="Lamp",
        brightness_enabled=True,
        effect_enabled=True,
        effect_list=["rainbow"],
    )
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"]["lamp"] == {
        "uniq_id": "lamp",
        "p": "light",
        "stat_t": "~/lamp/state/power",
        "cmd_t": "~/lamp/command/power",
        "name": "Lamp",
        "bri_stat_t": "~/lamp/state/brightness",
        "bri_cmd_t": "~/lamp/command/brightness",
        "fx_stat_t": "~/lamp/state/effect",
        "fx_cmd_t": "~/lamp/command/effect",
        "fx_list": ["rainbow"],
    }


async def test_discovery_config_includes_documented_optional_keys() -> None:
    _, light = bound(
        RecordingProvider(),
        unique_id="lamp",
        brightness_enabled=True,
        color_temp_enabled=True,
        color_temp_kelvin=True,
        effect_enabled=True,
        effect_list=["rainbow"],
        white_enabled=True,
        white_scale=100,
    )

    assert light.discovery_config() == {
        "uniq_id": "lamp",
        "p": "light",
        "stat_t": "~/lamp/state/power",
        "cmd_t": "~/lamp/command/power",
        "bri_stat_t": "~/lamp/state/brightness",
        "bri_cmd_t": "~/lamp/command/brightness",
        "clr_temp_stat_t": "~/lamp/state/color_temp",
        "clr_temp_cmd_t": "~/lamp/command/color_temp",
        "fx_stat_t": "~/lamp/state/effect",
        "fx_cmd_t": "~/lamp/command/effect",
        "fx_list": ["rainbow"],
        "clr_temp_k": True,
        "whit_cmd_t": "~/lamp/command/white",
        "whit_scl": 100,
    }

    assert not any(key.startswith("white_") for key in light.discovery_config())


async def test_discovery_config_omits_disabled_optional_keys() -> None:
    _, light = bound(RecordingProvider(), unique_id="lamp")

    assert light.discovery_config() == {
        "uniq_id": "lamp",
        "p": "light",
        "stat_t": "~/lamp/state/power",
        "cmd_t": "~/lamp/command/power",
    }


async def test_disabled_feature_rejected() -> None:
    _, light = bound(RecordingProvider(), unique_id="lamp")
    with pytest.raises(ValueError):
        await light.set_brightness(1)


async def test_effect_and_numeric_events_reject_invalid_values() -> None:
    provider = RecordingProvider()
    _, light = bound(
        provider,
        unique_id="lamp",
        brightness_enabled=True,
        effect_enabled=True,
        effect_list=["rainbow"],
    )
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await light.on_event(collect)
    await provider.deliver("homeassistant/device/dev-1/lamp/command/brightness", "256")
    await provider.deliver("homeassistant/device/dev-1/lamp/command/effect", "other")

    assert [event.state for event in received] == [None, None]
