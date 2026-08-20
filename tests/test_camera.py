"""Tests for Camera using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.camera import Camera
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Camera]:
    """Build a device and a bound camera with the given kwargs."""
    camera = Camera(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[camera],
    )
    return device, camera


async def test_image_topic_is_resolved() -> None:
    _, camera = make_bound(RecordingProvider(), unique_id="front_door")

    assert camera.image_topic == "homeassistant/device/dev-1/front_door/image"


async def test_set_image_publishes_payload_verbatim() -> None:
    provider = RecordingProvider()
    _, camera = make_bound(provider, unique_id="front_door")
    payload = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    await camera.set_image(payload)

    assert provider.published == [
        ("homeassistant/device/dev-1/front_door/image", payload, False)
    ]


async def test_set_image_republishes_identical_frames() -> None:
    provider = RecordingProvider()
    _, camera = make_bound(provider, unique_id="front_door")

    await camera.set_image(b"same-frame")
    await camera.set_image(b"same-frame")

    assert provider.published == [
        ("homeassistant/device/dev-1/front_door/image", b"same-frame", False),
        ("homeassistant/device/dev-1/front_door/image", b"same-frame", False),
    ]


async def test_set_image_publishes_verbatim_for_any_encoding() -> None:
    provider = RecordingProvider()
    _, camera = make_bound(provider, unique_id="front_door", encoding="binary")
    payload = b"\xff\xd8\xff\xe0jpeg-data"

    await camera.set_image(payload)

    assert provider.published == [
        ("homeassistant/device/dev-1/front_door/image", payload, False)
    ]


async def test_set_image_requires_binding() -> None:
    camera = Camera(unique_id="front_door")

    with pytest.raises(RuntimeError, match="not bound"):
        await camera.set_image(b"data")


async def test_set_image_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, camera = make_bound(provider, unique_id="front_door")

    await camera.set_image(b"data")

    assert provider.subscriptions == {}


async def test_discovery_config_defaults() -> None:
    _, camera = make_bound(RecordingProvider(), unique_id="front_door")

    # img_e is omitted because the documented default is raw image data.
    assert camera.discovery_config() == {
        "uniq_id": "front_door",
        "p": "camera",
        "t": "homeassistant/device/dev-1/front_door/image",
    }


async def test_discovery_config_includes_name() -> None:
    _, camera = make_bound(
        RecordingProvider(), unique_id="front_door", name="Front door camera"
    )

    assert camera.discovery_config() == {
        "uniq_id": "front_door",
        "p": "camera",
        "t": "homeassistant/device/dev-1/front_door/image",
        "name": "Front door camera",
    }


async def test_discovery_config_uses_image_encoding_key() -> None:
    _, camera = make_bound(
        RecordingProvider(),
        unique_id="front_door",
        encoding="b64",
    )

    assert camera.discovery_config() == {
        "uniq_id": "front_door",
        "p": "camera",
        "t": "homeassistant/device/dev-1/front_door/image",
        "img_e": "b64",
    }


async def test_discovery_config_omits_encoding_and_unsupported_content_type() -> None:
    _, camera = make_bound(
        RecordingProvider(),
        unique_id="front_door",
        content_type="image/png",
    )

    # Camera discovery has no documented content-type field.
    assert camera.discovery_config() == {
        "uniq_id": "front_door",
        "p": "camera",
        "t": "homeassistant/device/dev-1/front_door/image",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Camera(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, camera = make_bound(provider, unique_id="front_door", name="Front door")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"front_door": camera.discovery_config()}
