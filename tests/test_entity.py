from __future__ import annotations

import gc

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.publish_topic import PublishTopic
from ha_mqtt_device.values.str_value import StrValue


def test_command_topic_for_builds_base_and_nested_topics() -> None:
    entity = Entity("relay")
    Device(
        RecordingProvider(),
        DeviceInfo(device_id="dev-1", name="Device", topic_prefix="custom/mqtt"),
        [entity],
    )

    assert entity.command_topic_for() == "custom/mqtt/relay/command"
    assert entity.command_topic_for("power") == "custom/mqtt/relay/command/power"
    assert entity.command_topic_for("") == "custom/mqtt/relay/command"
    assert entity.command_topic_for(None) == "custom/mqtt/relay/command"


def test_topic_prefix_requires_a_bound_entity() -> None:
    with pytest.raises(RuntimeError, match="bound to a Device"):
        Entity("relay").topic_prefix()


def test_topic_prefix_includes_the_entity_unique_id() -> None:
    entity = Entity("relay")
    Device(
        RecordingProvider(),
        DeviceInfo(device_id="dev-1", name="Device", topic_prefix="custom/mqtt"),
        [entity],
    )

    assert entity.topic_prefix() == "custom/mqtt/relay"


async def test_persistent_state_publishes_resolved_retained_topic() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    device = Device(
        provider, DeviceInfo(device_id="dev-1", name="Device"), entities=[entity]
    )
    state = entity._make_persistent_state(StrValue(), "state/power")

    await state.set_value("ON")
    await entity._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state/power", "ON", True),
        ("homeassistant/device/dev-1/relay/state/power", "", True),
    ]
    assert device.entities == (entity,)


async def test_momentary_state_is_not_retained_or_cleared() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])
    state = entity._make_momentary_state(StrValue(), "state/event")

    await state.set_value("pressed")
    await state.set_value("pressed")
    await entity._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state/event", "pressed", False),
        ("homeassistant/device/dev-1/relay/state/event", "pressed", False),
    ]


async def test_persistent_state_is_cleared_without_being_published() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    entity._make_persistent_state(StrValue(), "state")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])

    await entity._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state", "", True),
    ]


async def test_persistent_states_are_registered_per_entity() -> None:
    first = Entity("first")
    first._make_persistent_state(StrValue(), "state")
    second = Entity("second")
    provider = RecordingProvider()
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [first, second])

    await second._on_remove()

    assert provider.published == []


async def test_state_value_delegates_change_detection() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])
    state = entity._make_persistent_state(StrValue(), "state")

    await state.set_value("ON")
    await state.set_value("ON")

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state", "ON", True),
    ]


async def test_state_value_force_update_is_independent_of_retention() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])
    state = entity._make_state(
        StrValue(), "state/event", retain=True, force_update=True
    )

    await state.set_value("pressed")
    await state.set_value("pressed")
    await entity._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state/event", "pressed", True),
        ("homeassistant/device/dev-1/relay/state/event", "pressed", True),
        ("homeassistant/device/dev-1/relay/state/event", "", True),
    ]


def test_state_value_topic_uses_entity_prefix_and_suffix() -> None:
    entity = Entity("relay")
    Device(
        RecordingProvider(),
        DeviceInfo(device_id="dev-1", name="Device", topic_prefix="custom/mqtt"),
        [entity],
    )
    state = entity._make_state(
        StrValue(), "state/power", retain=True, force_update=False
    )

    assert state.topic() == PublishTopic("custom/mqtt/relay/state/power", True)


async def test_retained_state_cleanup_deduplicates_topics() -> None:
    provider = RecordingProvider()
    entity = Entity("relay")
    entity._make_persistent_state(StrValue(), "state")
    entity._make_persistent_state(StrValue(), "state")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])

    await entity._on_remove()

    assert provider.published == [
        ("homeassistant/device/dev-1/relay/state", "", True),
    ]


async def test_state_value_requires_a_bound_entity() -> None:
    entity = Entity("relay")
    state = entity._make_persistent_state(StrValue(), "state")

    with pytest.raises(RuntimeError, match="bound to a Device"):
        await state.set_value("ON")


async def test_state_value_raises_when_entity_is_gone() -> None:
    entity = Entity("relay")
    state = entity._make_persistent_state(StrValue(), "state")
    del entity
    gc.collect()

    with pytest.raises(RuntimeError, match="owning Entity"):
        await state.set_value("ON")


async def test_state_value_does_not_update_on_failed_publication() -> None:
    class FailingProvider(RecordingProvider):
        async def publish(
            self, topic: str, message: str | bytes, retain: bool = False
        ) -> None:
            raise RuntimeError("publish failed")

    provider = FailingProvider()
    entity = Entity("relay")
    Device(provider, DeviceInfo(device_id="dev-1", name="Device"), [entity])
    value = StrValue()
    state = entity._make_persistent_state(value, "state")

    with pytest.raises(RuntimeError, match="publish failed"):
        await state.set_value("ON")

    assert value.value is None
