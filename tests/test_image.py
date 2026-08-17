"""Tests for Image using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.image import Image


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Image]:
    """Build a device and a bound image entity with the given kwargs."""
    image = Image(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[image],
    )
    return device, image


async def test_image_topic_shorthand() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera")

    assert image.image_topic == "~/camera/image"


async def test_set_image_publishes_payload_verbatim() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera")
    payload = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    await image.set_image(payload)

    assert provider.published == [
        ("homeassistant/device/dev-1/camera/image", payload, False)
    ]


async def test_set_image_publishes_verbatim_for_any_encoding() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera", encoding="binary")
    payload = b"\xff\xd8\xff\xe0jpeg-data"

    await image.set_image(payload)

    assert provider.published == [
        ("homeassistant/device/dev-1/camera/image", payload, False)
    ]


async def test_set_image_requires_binding() -> None:
    image = Image(unique_id="camera")

    with pytest.raises(RuntimeError, match="not bound"):
        await image.set_image(b"data")


async def test_set_image_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera")

    await image.set_image(b"data")

    assert provider.subscriptions == {}


async def test_discovery_config_defaults() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera")

    # img_e and cont_type are omitted because the documented defaults are raw
    # image data and image/jpeg.
    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "img_t": "~/camera/image",
    }


async def test_discovery_config_includes_name() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera", name="Camera")

    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "img_t": "~/camera/image",
        "name": "Camera",
    }


async def test_discovery_config_uses_image_encoding_and_content_type_keys() -> None:
    _, image = make_bound(
        RecordingProvider(),
        unique_id="camera",
        encoding="b64",
        content_type="image/png",
    )

    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "img_t": "~/camera/image",
        "img_e": "b64",
        "cont_type": "image/png",
    }


async def test_discovery_config_omits_encoding_with_non_default_content_type() -> None:
    _, image = make_bound(
        RecordingProvider(),
        unique_id="camera",
        content_type="image/png",
    )

    # The raw-image default is omitted while the explicit content type remains.
    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "img_t": "~/camera/image",
        "cont_type": "image/png",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Image(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, image = make_bound(provider, unique_id="camera", name="Camera")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"camera": image.discovery_config()}
