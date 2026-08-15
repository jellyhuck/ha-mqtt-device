"""Tests for Humidifier using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.humidifier import Humidifier
from ha_mqtt_device.provider import Message, MqttMessageCallback


class RecordingProvider:
    """Minimal structural MqttProvider that records publishes and subscriptions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str | bytes]] = []
        self.subscriptions: dict[str, list[MqttMessageCallback]] = {}

    async def publish(self, topic: str, message: str | bytes) -> None:
        self.published.append((topic, message))

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        self.subscriptions.setdefault(topic, []).append(callback)

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def deliver(self, topic: str, payload: str | bytes) -> None:
        """Invoke every callback registered for ``topic`` with ``payload``."""
        raw = payload.encode() if isinstance(payload, str) else payload
        for callback in self.subscriptions.get(topic, []):
            await callback(Message(topic=topic, payload=raw))


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Humidifier]:
    """Build a device and a bound humidifier with the given kwargs."""
    humidifier = Humidifier(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[humidifier],
    )
    return device, humidifier


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.set_state(True)
    await humidifier.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/bedroom/state", "ON"),
        ("homeassistant/device/dev-1/bedroom/state", "OFF"),
    ]


async def test_set_state_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(
        provider, unique_id="bedroom", payload_on="1", payload_off="0"
    )

    await humidifier.set_state(True)
    await humidifier.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/bedroom/state", "1"),
        ("homeassistant/device/dev-1/bedroom/state", "0"),
    ]


async def test_set_state_requires_binding() -> None:
    humidifier = Humidifier(unique_id="bedroom")

    with pytest.raises(RuntimeError, match="not bound"):
        await humidifier.set_state(True)


async def test_set_target_humidity_publishes_to_topic() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.set_target_humidity(50)

    assert provider.published == [
        ("homeassistant/device/dev-1/bedroom/target_humidity", "50")
    ]


async def test_set_target_humidity_publishes_float() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.set_target_humidity(50.5)

    assert provider.published == [
        ("homeassistant/device/dev-1/bedroom/target_humidity", "50.5")
    ]


async def test_set_target_humidity_requires_binding() -> None:
    humidifier = Humidifier(unique_id="bedroom")

    with pytest.raises(RuntimeError, match="not bound"):
        await humidifier.set_target_humidity(50)


async def test_set_target_humidity_rejects_values_outside_configured_range() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(
        provider, unique_id="bedroom", min_humidity=30, max_humidity=80
    )

    with pytest.raises(ValueError, match="outside"):
        await humidifier.set_target_humidity(81)
    with pytest.raises(ValueError, match="finite"):
        await humidifier.set_target_humidity(float("nan"))


async def test_publish_methods_do_not_subscribe() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.set_state(True)
    await humidifier.set_target_humidity(50)

    assert provider.subscriptions == {}


async def test_topics_shorthand() -> None:
    _, humidifier = make_bound(RecordingProvider(), unique_id="bedroom")

    assert humidifier.state_topic == "~/bedroom/state"
    assert humidifier.command_topic == "~/bedroom/command"
    assert humidifier.target_humidity_state_topic == "~/bedroom/target_humidity"
    assert (
        humidifier.target_humidity_command_topic == "~/bedroom/target_humidity_command"
    )


async def test_on_event_subscribes_to_both_resolved_command_topics() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/bedroom/command",
        "homeassistant/device/dev-1/bedroom/target_humidity_command",
    ]


async def test_on_event_requires_binding() -> None:
    humidifier = Humidifier(unique_id="bedroom")

    with pytest.raises(RuntimeError, match="not bound"):
        await humidifier.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    await humidifier.on_event(lambda event: _noop())
    await humidifier.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/bedroom/command": [humidifier._dispatch_command],
        "homeassistant/device/dev-1/bedroom/target_humidity_command": [
            humidifier._dispatch_target_humidity
        ],
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "ON")
    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "OFF")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/bedroom/command"
    assert first.message == "ON"
    assert first.state == "on"
    assert second.state == "off"


async def test_dispatch_uses_payload_mapping() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(
        provider, unique_id="bedroom", payload_on="1", payload_off="0"
    )
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "1")
    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "0")
    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "ON")

    assert [event.state for event in received] == ["on", "off", None]


async def test_dispatch_delivers_unknown_command_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "TOGGLE")

    assert len(received) == 1
    assert received[0].message == "TOGGLE"
    assert received[0].state is None


async def test_dispatch_delivers_target_humidity_event() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/bedroom/target_humidity_command", "50"
    )

    assert len(received) == 1
    event = received[0]
    assert event.event_type == "target_humidity"
    assert event.topic_type == "target_humidity_command_topic"
    assert event.topic == "homeassistant/device/dev-1/bedroom/target_humidity_command"
    assert event.message == "50"
    assert event.state == "50"


async def test_dispatch_target_humidity_unknown_payload_has_null_state() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/bedroom/target_humidity_command", "high"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/bedroom/target_humidity_command", ""
    )

    assert [event.state for event in received] == [None, None]


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    received: list[Event] = []
    await humidifier.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/bedroom/target_humidity_command", b"50"
    )

    assert received[0].message == "50"
    assert received[0].state == "50"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")
    first: list[Event] = []
    second: list[Event] = []
    await humidifier.on_event(collector(first))
    await humidifier.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/bedroom/command", "ON")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, humidifier = make_bound(provider, unique_id="bedroom")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await humidifier.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.humidifier"):
        await provider.deliver("homeassistant/device/dev-1/bedroom/command", "ON")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, humidifier = make_bound(RecordingProvider(), unique_id="bedroom")

    # pl_on/pl_off and min_hum/max_hum are omitted because they match the
    # discovery defaults.
    assert humidifier.discovery_config() == {
        "uniq_id": "bedroom",
        "stat_t": "~/bedroom/state",
        "cmd_t": "~/bedroom/command",
        "tgt_hum_stat_t": "~/bedroom/target_humidity",
        "tgt_hum_cmd_t": "~/bedroom/target_humidity_command",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, humidifier = make_bound(
        RecordingProvider(),
        unique_id="bedroom",
        name="Bedroom humidifier",
        device_class="humidifier",
    )

    assert humidifier.discovery_config() == {
        "uniq_id": "bedroom",
        "stat_t": "~/bedroom/state",
        "cmd_t": "~/bedroom/command",
        "tgt_hum_stat_t": "~/bedroom/target_humidity",
        "tgt_hum_cmd_t": "~/bedroom/target_humidity_command",
        "name": "Bedroom humidifier",
        "dev_cla": "humidifier",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, humidifier = make_bound(
        RecordingProvider(),
        unique_id="bedroom",
        payload_on="1",
        payload_off="0",
    )

    assert humidifier.discovery_config() == {
        "uniq_id": "bedroom",
        "stat_t": "~/bedroom/state",
        "cmd_t": "~/bedroom/command",
        "tgt_hum_stat_t": "~/bedroom/target_humidity",
        "tgt_hum_cmd_t": "~/bedroom/target_humidity_command",
        "pl_on": "1",
        "pl_off": "0",
    }


async def test_discovery_config_includes_humidity_range() -> None:
    _, humidifier = make_bound(
        RecordingProvider(),
        unique_id="bedroom",
        min_humidity=30,
        max_humidity=80,
    )

    assert humidifier.discovery_config() == {
        "uniq_id": "bedroom",
        "stat_t": "~/bedroom/state",
        "cmd_t": "~/bedroom/command",
        "tgt_hum_stat_t": "~/bedroom/target_humidity",
        "tgt_hum_cmd_t": "~/bedroom/target_humidity_command",
        "min_hum": 30,
        "max_hum": 80,
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, humidifier = make_bound(
        RecordingProvider(), unique_id="bedroom", optimistic=True
    )

    assert humidifier.discovery_config() == {
        "uniq_id": "bedroom",
        "stat_t": "~/bedroom/state",
        "cmd_t": "~/bedroom/command",
        "tgt_hum_stat_t": "~/bedroom/target_humidity",
        "tgt_hum_cmd_t": "~/bedroom/target_humidity_command",
        "opt": True,
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Humidifier(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, humidifier = make_bound(provider, unique_id="bedroom", name="Bedroom")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"humidifier": {"bedroom": humidifier.discovery_config()}}


async def _noop() -> None:
    return None
