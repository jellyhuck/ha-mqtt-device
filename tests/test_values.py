"""Tests for reusable MQTT-published values."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device import (
    DateTimeValue,
    DateValue,
    FloatValue,
    IntValue,
    StrEnumValue,
    StrValue,
    Value,
)
from ha_mqtt_device.publish_topic import PublishTopic


def topic() -> PublishTopic:
    return PublishTopic("home/device/value", retain=True)


@pytest.mark.parametrize(
    "value_class",
    [StrValue, IntValue, FloatValue, DateValue, DateTimeValue],
)
def test_values_start_unset(value_class: type[Value[object]]) -> None:
    value = value_class(topic())

    assert value.value is None
    assert value.publish_topic == topic()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "payload", "value_class"),
    [
        ("hello", "hello", StrValue),
        (3, "3", IntValue),
        (3.5, "3.5", FloatValue),
        (date(2024, 2, 14), "2024-02-14", DateValue),
        (
            datetime(2024, 2, 14, 10, 30, 15, tzinfo=UTC),
            "2024-02-14 10:30:15",
            DateTimeValue,
        ),
    ],
)
async def test_first_set_publishes_and_updates_value(
    value: object,
    payload: str,
    value_class: type[Value[object]],
) -> None:
    provider = RecordingProvider()
    typed_value = value_class(topic())

    await typed_value.set_value(value, provider)  # type: ignore[arg-type]

    assert typed_value.value == value
    assert provider.published == [("home/device/value", payload, True)]


@pytest.mark.asyncio
async def test_unchanged_value_is_not_published_unless_forced() -> None:
    provider = RecordingProvider()
    value = StrValue(topic())

    await value.set_value("same", provider)
    await value.set_value("same", provider)
    await value.set_value("same", provider, force_publish=True)

    assert provider.published == [
        ("home/device/value", "same", True),
        ("home/device/value", "same", True),
    ]


@pytest.mark.asyncio
async def test_changed_value_is_published() -> None:
    provider = RecordingProvider()
    value = IntValue(topic())

    await value.set_value(1, provider)
    await value.set_value(2, provider)

    assert value.value == 2
    assert provider.published == [
        ("home/device/value", "1", True),
        ("home/device/value", "2", True),
    ]


class Status(StrEnum):
    READY = "ready"
    OFFLINE = "offline"


@pytest.mark.asyncio
async def test_str_enum_value_publishes_values_and_stores_members() -> None:
    provider = RecordingProvider()
    value = StrEnumValue[Status](topic())

    await value.set_value(Status.READY, provider)
    await value.set_value(Status.READY, provider)
    await value.set_value(Status.OFFLINE, provider)

    assert value.value is Status.OFFLINE
    assert provider.published == [
        ("home/device/value", "ready", True),
        ("home/device/value", "offline", True),
    ]


@pytest.mark.asyncio
async def test_str_enum_value_rejects_plain_strings() -> None:
    provider = RecordingProvider()
    value = StrEnumValue[Status](topic())

    with pytest.raises(TypeError, match="StrEnum"):
        await value.set_value("ready", provider)  # type: ignore[arg-type]

    assert value.value is None
    assert provider.published == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value_class",
    [StrValue, IntValue, FloatValue, DateValue, DateTimeValue],
)
async def test_none_is_rejected(value_class: type[Value[object]]) -> None:
    provider = RecordingProvider()
    value = value_class(topic())

    with pytest.raises(TypeError, match="None"):
        await value.set_value(None, provider)  # type: ignore[arg-type]

    assert value.value is None
    assert provider.published == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value_class", "invalid"),
    [
        (StrValue, 1),
        (IntValue, True),
        (IntValue, 1.0),
        (FloatValue, 1),
        (DateValue, datetime(2024, 2, 14, tzinfo=UTC)),
        (DateTimeValue, date(2024, 2, 14)),
    ],
)
async def test_strict_types_are_rejected(
    value_class: type[Value[object]], invalid: object
) -> None:
    provider = RecordingProvider()
    value = value_class(topic())

    with pytest.raises(TypeError):
        await value.set_value(invalid, provider)  # type: ignore[arg-type]

    assert value.value is None
    assert provider.published == []


@pytest.mark.asyncio
async def test_failed_publication_does_not_update_value() -> None:
    class FailingProvider(RecordingProvider):
        async def publish(
            self, topic: str, message: str | bytes, retain: bool = False
        ) -> None:
            raise RuntimeError("publish failed")

    value = StrValue(topic())

    with pytest.raises(RuntimeError, match="publish failed"):
        await value.set_value("new", FailingProvider())

    assert value.value is None


@pytest.mark.asyncio
async def test_public_generic_base_supports_custom_serializers() -> None:
    class UpperValue(Value[str]):
        def _serialize_value(self, value: str) -> str:
            if not isinstance(value, str):
                raise TypeError("UpperValue requires a string")
            return value.upper()

    provider = RecordingProvider()
    value = UpperValue(topic())

    await value.set_value("hello", provider)

    assert value.value == "hello"
    assert provider.published == [("home/device/value", "HELLO", True)]


def test_public_value_exports() -> None:
    import ha_mqtt_device
    from ha_mqtt_device import values

    for name in (
        "Value",
        "StrValue",
        "IntValue",
        "FloatValue",
        "DateValue",
        "DateTimeValue",
        "StrEnumValue",
    ):
        assert getattr(ha_mqtt_device, name) is getattr(values, name)
        assert name in ha_mqtt_device.__all__
        assert name in values.__all__
