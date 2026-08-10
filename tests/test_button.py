"""Tests for Button using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.button import Button
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
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
) -> tuple[Device, Button]:
    """Build a device and a bound button with the given kwargs."""
    button = Button(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[button],
    )
    return device, button


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_command_topic_shorthand() -> None:
    _, button = make_bound(RecordingProvider(), unique_id="restart_1")

    assert button.command_topic == "~/restart_1/command"


async def test_on_event_subscribes_to_resolved_command_topic() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")

    await button.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/restart_1/command"
    ]


async def test_on_event_requires_binding() -> None:
    button = Button(unique_id="restart_1")

    with pytest.raises(RuntimeError, match="not bound"):
        await button.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")

    await button.on_event(lambda event: _noop())
    await button.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/restart_1/command": [button._dispatch]
    }


async def test_dispatch_delivers_press_event() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")
    received: list[Event] = []
    await button.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/restart_1/command", "PRESS")

    assert len(received) == 1
    event = received[0]
    assert event.event_type == "press"
    assert event.topic_type == "command_topic"
    assert event.topic == "homeassistant/device/dev-1/restart_1/command"
    assert event.message == "PRESS"
    assert event.state == "press"


async def test_dispatch_uses_custom_payload() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1", payload_press="RESTART")
    received: list[Event] = []
    await button.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/restart_1/command", "RESTART")
    await provider.deliver("homeassistant/device/dev-1/restart_1/command", "PRESS")

    assert [event.state for event in received] == ["press", None]


async def test_dispatch_delivers_unknown_payload_with_null_state() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")
    received: list[Event] = []
    await button.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/restart_1/command", "TOGGLE")

    assert len(received) == 1
    assert received[0].message == "TOGGLE"
    assert received[0].state is None


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")
    received: list[Event] = []
    await button.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/restart_1/command", b"PRESS")

    assert received[0].message == "PRESS"
    assert received[0].state == "press"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")
    first: list[Event] = []
    second: list[Event] = []
    await button.on_event(collector(first))
    await button.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/restart_1/command", "PRESS")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, button = make_bound(provider, unique_id="restart_1")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await button.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.button"):
        await provider.deliver("homeassistant/device/dev-1/restart_1/command", "PRESS")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, button = make_bound(RecordingProvider(), unique_id="restart_1")

    # There is no state topic: only uniq_id and cmd_t, no "p" key.
    # pl_prs is omitted because it matches the discovery default.
    assert button.discovery_config() == {
        "uniq_id": "restart_1",
        "cmd_t": "~/restart_1/command",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, button = make_bound(
        RecordingProvider(),
        unique_id="restart_1",
        name="Restart",
        device_class="restart",
    )

    assert button.discovery_config() == {
        "uniq_id": "restart_1",
        "cmd_t": "~/restart_1/command",
        "name": "Restart",
        "dev_cla": "restart",
    }


async def test_discovery_config_includes_custom_payload() -> None:
    _, button = make_bound(
        RecordingProvider(), unique_id="restart_1", payload_press="R"
    )

    assert button.discovery_config() == {
        "uniq_id": "restart_1",
        "cmd_t": "~/restart_1/command",
        "pl_prs": "R",
    }


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Button(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, button = make_bound(provider, unique_id="restart_1", name="Restart")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"button": {"restart_1": button.discovery_config()}}


async def _noop() -> None:
    return None
