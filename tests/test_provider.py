"""Tests for the MqttProvider interface and the Message type."""

from __future__ import annotations

import pytest

from ha_mqtt_device.provider import Message, MqttMessageCallback, MqttProvider


class DummyProvider:
    """A minimal structural implementation of MqttProvider."""

    async def publish(
        self, topic: str, message: str | bytes, retain: bool = False
    ) -> None:
        return None

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        return None

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def test_message_fields() -> None:
    message = Message(topic="home/sensor/temperature", payload=b"21.5")
    assert message.topic == "home/sensor/temperature"
    assert message.payload == b"21.5"


def test_message_is_immutable() -> None:
    message = Message(topic="t", payload=b"p")
    with pytest.raises(AttributeError):
        message.payload = b"other"  # type: ignore[misc]


def test_message_equality() -> None:
    assert Message(topic="t", payload=b"p") == Message(topic="t", payload=b"p")
    assert Message(topic="t", payload=b"p") != Message(topic="t", payload=b"q")


def test_dummy_provider_satisfies_protocol() -> None:
    assert isinstance(DummyProvider(), MqttProvider)


@pytest.mark.asyncio
async def test_dummy_provider_accepts_retain_option() -> None:
    await DummyProvider().publish("home/device/state", "on", retain=True)


def test_mqtt_message_callback_alias() -> None:
    async def handler(message: Message) -> None:
        return None

    callback: MqttMessageCallback = handler
    assert callable(callback)
