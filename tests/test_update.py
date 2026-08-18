"""Tests for Update using a recording provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import Device, DeviceInfo, Event, Update


def bound(provider: RecordingProvider, **kwargs: Any) -> tuple[Device, Update]:
    entity = Update(**kwargs)
    return Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), [entity]
    ), entity


async def test_state_publishes_documented_json_fields() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="firmware")

    await entity.set_state(
        "1.21.0",
        latest_version="1.22.0",
        title="Device Firmware",
        release_summary="Bug fixes",
        release_url="https://example.com/release",
        entity_picture="https://example.com/icon.png",
        in_progress=True,
        update_percentage=78,
    )

    assert provider.published == [
        (
            "homeassistant/device/dev-1/firmware/state",
            json.dumps(
                {
                    "installed_version": "1.21.0",
                    "latest_version": "1.22.0",
                    "title": "Device Firmware",
                    "release_summary": "Bug fixes",
                    "release_url": "https://example.com/release",
                    "entity_picture": "https://example.com/icon.png",
                    "in_progress": True,
                    "update_percentage": 78,
                }
            ),
            True,
        )
    ]


async def test_discovery_defaults_and_optional_configuration() -> None:
    _, defaults = bound(RecordingProvider(), unique_id="firmware")
    assert defaults.discovery_config() == {
        "uniq_id": "firmware",
        "p": "update",
        "stat_t": "~/firmware/state",
        "cmd_t": "~/firmware/command",
    }

    _, configured = bound(
        RecordingProvider(),
        unique_id="firmware",
        title="Firmware",
        device_class="firmware",
        release_summary="Notes",
        release_url="https://example.com/release",
        entity_picture="https://example.com/icon.png",
        value_template="{{ value_json.installed_version }}",
        latest_version_enabled=True,
        latest_version_template="{{ value_json.latest_version }}",
        payload_install="update_fw",
    )
    assert configured.discovery_config() == {
        "uniq_id": "firmware",
        "p": "update",
        "stat_t": "~/firmware/state",
        "cmd_t": "~/firmware/command",
        "l_ver_t": "~/firmware/state/latest",
        "pl_inst": "update_fw",
        "tit": "Firmware",
        "dev_cla": "firmware",
        "rel_s": "Notes",
        "rel_u": "https://example.com/release",
        "ent_pic": "https://example.com/icon.png",
        "val_tpl": "{{ value_json.installed_version }}",
        "l_ver_tpl": "{{ value_json.latest_version }}",
    }


async def test_latest_version_and_install_publish_to_resolved_topics() -> None:
    provider = RecordingProvider()
    _, entity = bound(
        provider,
        unique_id="firmware",
        latest_version_enabled=True,
        payload_install="update_fw",
    )

    await entity.set_latest_version("1.22.0")
    await entity.install()

    assert provider.published == [
        ("homeassistant/device/dev-1/firmware/state/latest", "1.22.0", True),
        ("homeassistant/device/dev-1/firmware/command", "update_fw", False),
    ]


async def test_install_events_subscribe_once_and_preserve_unknown_payloads() -> None:
    provider = RecordingProvider()
    _, entity = bound(provider, unique_id="firmware", payload_install="update_fw")
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    await entity.on_event(collect)
    await entity.on_event(collect)
    topic = "homeassistant/device/dev-1/firmware/command"
    await provider.deliver(topic, "update_fw")
    await provider.deliver(topic, "other")

    assert len(provider.subscriptions[topic]) == 1
    assert [event.state for event in received] == ["install", "install", None, None]
    assert received[0].message == "update_fw"
    assert received[0].topic_type == "command_topic"


async def test_update_state_validation_and_device_integration() -> None:
    provider = RecordingProvider()
    device, entity = bound(provider, unique_id="firmware")
    await device.configure()
    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"firmware": entity.discovery_config()}

    with pytest.raises(ValueError, match="percentage"):
        await entity.set_state("1.0", update_percentage=101)
    with pytest.raises(ValueError, match="unsupported update state"):
        await entity.publish_state({"installed_version": "1.0", "unknown": "x"})
    with pytest.raises(ValueError, match="requires installed_version"):
        await entity.publish_state({"latest_version": "1.1"})
    with pytest.raises(ValueError, match="non-empty"):
        await entity.set_state("")

    disabled = Update(unique_id="disabled", install_enabled=False)
    with pytest.raises(RuntimeError, match="not bound"):
        await disabled.install()
