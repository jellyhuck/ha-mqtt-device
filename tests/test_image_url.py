"""Tests for ImageUrl using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.image_url import ImageUrl


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, ImageUrl]:
    """Build a device and a bound URL image entity with the given kwargs."""
    image = ImageUrl(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[image],
    )
    return device, image


async def test_url_topic_is_resolved_from_state_value() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera")

    assert image.url_topic == "homeassistant/device/dev-1/camera/url"
    assert image.url_topic == image._url_value.topic().topic


async def test_set_url_publishes_retained_payload_verbatim() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera")
    url = "https://example.com/images/camera.jpg?token=abc"

    await image.set_url(url)

    assert provider.published == [("homeassistant/device/dev-1/camera/url", url, True)]


async def test_set_url_suppresses_an_unchanged_retained_url() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera")

    await image.set_url("https://example.com/same.jpg")
    await image.set_url("https://example.com/same.jpg")

    assert provider.published == [
        ("homeassistant/device/dev-1/camera/url", "https://example.com/same.jpg", True)
    ]


async def test_set_url_requires_a_string() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera")

    with pytest.raises(TypeError, match="StrValue requires a string"):
        await image.set_url(123)  # type: ignore[arg-type]


async def test_set_url_requires_binding() -> None:
    image = ImageUrl(unique_id="camera")

    with pytest.raises(RuntimeError, match="not bound"):
        await image.set_url("https://example.com/image.jpg")


async def test_set_url_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, image = make_bound(provider, unique_id="camera")

    await image.set_url("https://example.com/image.jpg")

    assert provider.subscriptions == {}


async def test_discovery_config_defaults() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera")

    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "url_t": "homeassistant/device/dev-1/camera/url",
    }


async def test_discovery_config_includes_name() -> None:
    _, image = make_bound(RecordingProvider(), unique_id="camera", name="Camera")

    assert image.discovery_config() == {
        "uniq_id": "camera",
        "p": "image",
        "url_t": "homeassistant/device/dev-1/camera/url",
        "name": "Camera",
    }


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, image = make_bound(provider, unique_id="camera", name="Camera")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"camera": image.discovery_config()}


async def test_remove_clears_retained_url() -> None:
    provider = RecordingProvider()
    device, image = make_bound(provider, unique_id="camera")

    await image.set_url("https://example.com/image.jpg")
    await device.remove()

    assert provider.published == [
        (
            "homeassistant/device/dev-1/camera/url",
            "https://example.com/image.jpg",
            True,
        ),
        ("homeassistant/device/dev-1/config", "", True),
        ("homeassistant/device/dev-1/status", "", True),
        ("homeassistant/device/dev-1/camera/url", "", True),
    ]
