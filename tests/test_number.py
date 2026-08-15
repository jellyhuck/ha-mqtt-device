"""Tests for Number using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.number import Number
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
) -> tuple[Device, Number]:
    """Build a device and a bound number with the given kwargs."""
    number = Number(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[number],
    )
    return device, number


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_stringified_values_to_state_topic() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")

    await number.set_state(75.0)
    await number.set_state(42)
    await number.set_state(21.5)

    assert provider.published == [
        ("homeassistant/device/dev-1/dimmer/state", "75.0"),
        ("homeassistant/device/dev-1/dimmer/state", "42"),
        ("homeassistant/device/dev-1/dimmer/state", "21.5"),
    ]


async def test_set_state_requires_binding() -> None:
    number = Number(unique_id="dimmer")

    with pytest.raises(RuntimeError, match="not bound"):
        await number.set_state(75.0)


async def test_set_state_rejects_non_finite_and_out_of_range_values() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer", min_value=10, max_value=20)

    with pytest.raises(ValueError, match="outside"):
        await number.set_state(21)
    with pytest.raises(ValueError, match="finite"):
        await number.set_state(float("inf"))


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")

    await number.set_state(75.0)

    assert provider.subscriptions == {}


async def test_command_topic_shorthand() -> None:
    _, number = make_bound(RecordingProvider(), unique_id="dimmer")

    assert number.command_topic == "~/dimmer/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")

    await number.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == ["homeassistant/device/dev-1/dimmer/command"]


async def test_on_event_requires_binding() -> None:
    number = Number(unique_id="dimmer")

    with pytest.raises(RuntimeError, match="not bound"):
        await number.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")

    await number.on_event(lambda event: _noop())
    await number.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/dimmer/command": [number._dispatch]
    }


async def test_dispatch_delivers_command_event() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")
    received: list[Event] = []
    await number.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/dimmer/command", "75")
    await provider.deliver("homeassistant/device/dev-1/dimmer/command", "21.5")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/dimmer/command"
    assert first.message == "75"
    assert first.state == "75"
    assert second.state == "21.5"


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")
    received: list[Event] = []
    await number.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/dimmer/command", "RESET")

    assert len(received) == 1
    assert received[0].message == "RESET"
    assert received[0].state is None


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")
    received: list[Event] = []
    await number.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/dimmer/command", b"75")

    assert received[0].message == "75"
    assert received[0].state == "75"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")
    first: list[Event] = []
    second: list[Event] = []
    await number.on_event(collector(first))
    await number.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/dimmer/command", "75")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, number = make_bound(provider, unique_id="dimmer")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await number.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.number"):
        await provider.deliver("homeassistant/device/dev-1/dimmer/command", "75")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, number = make_bound(RecordingProvider(), unique_id="dimmer")

    # min/max/step/mode are omitted because they match the discovery defaults.
    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, number = make_bound(
        RecordingProvider(),
        unique_id="dimmer",
        name="Dimmer",
        device_class="power",
    )

    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
        "name": "Dimmer",
        "dev_cla": "power",
    }


async def test_discovery_config_includes_bounds_step_and_mode() -> None:
    _, number = make_bound(
        RecordingProvider(),
        unique_id="dimmer",
        min_value=0.5,
        max_value=50.0,
        step=0.5,
        mode="box",
    )

    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
        "min": 0.5,
        "max": 50.0,
        "step": 0.5,
        "mode": "box",
    }


async def test_discovery_config_omits_default_bounds_step_and_mode() -> None:
    _, number = make_bound(
        RecordingProvider(),
        unique_id="dimmer",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        mode="auto",
    )

    # Every value matches a discovery default and is omitted.
    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, number = make_bound(RecordingProvider(), unique_id="dimmer", optimistic=True)

    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
        "opt": True,
    }


async def test_discovery_config_includes_payload_reset() -> None:
    _, number = make_bound(RecordingProvider(), unique_id="dimmer", payload_reset="0")

    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
        "pl_reset": "0",
    }


async def test_discovery_config_omits_default_payload_reset() -> None:
    _, number = make_bound(
        RecordingProvider(), unique_id="dimmer", payload_reset="None"
    )

    # pl_reset matches the discovery default and is omitted.
    assert number.discovery_config() == {
        "uniq_id": "dimmer",
        "p": "~/dimmer/state",
        "cmd_t": "~/dimmer/command",
    }


async def test_discovery_config_includes_unit_and_expiry_fields() -> None:
    _, number = make_bound(
        RecordingProvider(),
        unique_id="temperature",
        unit_of_measurement="°C",
        expire_after=300,
        force_update=True,
    )

    assert number.discovery_config() == {
        "uniq_id": "temperature",
        "p": "~/temperature/state",
        "cmd_t": "~/temperature/command",
        "unit_of_meas": "°C",
        "exp_aft": 300,
        "frc_upd": True,
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Number(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, number = make_bound(provider, unique_id="dimmer", name="Dimmer")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"number": {"dimmer": number.discovery_config()}}


async def _noop() -> None:
    return None
