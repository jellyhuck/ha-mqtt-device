"""Tests for Fan using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.fan import Fan
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


def make_bound(provider: RecordingProvider, **entity_kwargs: Any) -> tuple[Device, Fan]:
    """Build a device and a bound fan with the given kwargs."""
    fan = Fan(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[fan],
    )
    return device, fan


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_state_publishes_payloads_to_state_topic() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    await fan.set_state(True)
    await fan.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state", "ON"),
        ("homeassistant/device/dev-1/ceiling_fan/state", "OFF"),
    ]


async def test_set_state_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider, unique_id="ceiling_fan", payload_on="1", payload_off="0"
    )

    await fan.set_state(True)
    await fan.set_state(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state", "1"),
        ("homeassistant/device/dev-1/ceiling_fan/state", "0"),
    ]


async def test_set_state_requires_binding() -> None:
    fan = Fan(unique_id="ceiling_fan")

    with pytest.raises(RuntimeError, match="not bound"):
        await fan.set_state(True)


async def test_set_percentage_publishes_stringified_value() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    await fan.set_percentage(60)
    await fan.set_percentage(1)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/percentage", "60"),
        ("homeassistant/device/dev-1/ceiling_fan/state/percentage", "1"),
    ]


async def test_set_percentage_requires_binding() -> None:
    fan = Fan(unique_id="ceiling_fan")

    with pytest.raises(RuntimeError, match="not bound"):
        await fan.set_percentage(50)


async def test_set_percentage_rejects_values_outside_speed_range() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    with pytest.raises(ValueError, match="speed range"):
        await fan.set_percentage(0)


async def test_set_percentage_requires_enabled() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", percentage_enabled=False)

    with pytest.raises(ValueError, match="percentage control disabled"):
        await fan.set_percentage(50)


async def test_set_preset_mode_publishes_preset() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", preset_mode_enabled=True)

    await fan.set_preset_mode("auto")

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/preset_mode", "auto")
    ]


async def test_set_preset_mode_none_publishes_reset_payload() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", preset_mode_enabled=True)

    await fan.set_preset_mode(None)

    assert provider.published == [
        (
            "homeassistant/device/dev-1/ceiling_fan/state/preset_mode",
            "reset_percentage",
        )
    ]


async def test_set_preset_mode_uses_custom_reset_payload() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        preset_mode_enabled=True,
        payload_reset_percentage="speed",
    )

    await fan.set_preset_mode(None)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/preset_mode", "speed")
    ]


async def test_set_preset_mode_rejects_unknown_preset() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", preset_mode_enabled=True)

    with pytest.raises(ValueError, match="not in preset_modes"):
        await fan.set_preset_mode("turbo")


async def test_set_preset_mode_requires_enabled() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    with pytest.raises(ValueError, match="preset_mode control disabled"):
        await fan.set_preset_mode("auto")


async def test_set_oscillation_publishes_payloads() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", oscillation_enabled=True)

    await fan.set_oscillation(True)
    await fan.set_oscillation(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/oscillation", "oscillate_on"),
        ("homeassistant/device/dev-1/ceiling_fan/state/oscillation", "oscillate_off"),
    ]


async def test_set_oscillation_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        oscillation_enabled=True,
        payload_oscillation_on="yes",
        payload_oscillation_off="no",
    )

    await fan.set_oscillation(True)
    await fan.set_oscillation(False)

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/oscillation", "yes"),
        ("homeassistant/device/dev-1/ceiling_fan/state/oscillation", "no"),
    ]


async def test_set_oscillation_requires_enabled() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    with pytest.raises(ValueError, match="oscillation control disabled"):
        await fan.set_oscillation(True)


async def test_set_direction_publishes_direction() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", direction_enabled=True)

    await fan.set_direction("forward")
    await fan.set_direction("reverse")

    assert provider.published == [
        ("homeassistant/device/dev-1/ceiling_fan/state/direction", "forward"),
        ("homeassistant/device/dev-1/ceiling_fan/state/direction", "reverse"),
    ]


async def test_set_direction_rejects_unknown_direction() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", direction_enabled=True)

    with pytest.raises(ValueError, match="forward.*reverse"):
        await fan.set_direction("sideways")


async def test_set_direction_requires_enabled() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    with pytest.raises(ValueError, match="direction control disabled"):
        await fan.set_direction("forward")


async def test_set_state_does_not_subscribe() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    await fan.set_state(True)

    assert provider.subscriptions == {}


async def test_command_topic_shorthand() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    assert fan.command_topic == "~/ceiling_fan/command"


async def test_percentage_topic_shorthands() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    assert fan.percentage_state_topic == "~/ceiling_fan/state/percentage"
    assert fan.percentage_command_topic == "~/ceiling_fan/command/percentage"


async def test_preset_mode_topic_shorthands() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    assert fan.preset_mode_state_topic == "~/ceiling_fan/state/preset_mode"
    assert fan.preset_mode_command_topic == "~/ceiling_fan/command/preset_mode"


async def test_oscillation_topic_shorthands() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    assert fan.oscillation_state_topic == "~/ceiling_fan/state/oscillation"
    assert fan.oscillation_command_topic == "~/ceiling_fan/command/oscillation"


async def test_direction_topic_shorthands() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    assert fan.direction_state_topic == "~/ceiling_fan/state/direction"
    assert fan.direction_command_topic == "~/ceiling_fan/command/direction"


async def test_on_event_subscribes_to_command_and_enabled_feature_topics() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    await fan.on_event(lambda event: _noop())

    # Percentage control is enabled by default; preset/oscillation/direction are off.
    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/ceiling_fan/command",
        "homeassistant/device/dev-1/ceiling_fan/command/percentage",
    ]


async def test_on_event_subscribes_to_every_enabled_command_topic() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        preset_mode_enabled=True,
        oscillation_enabled=True,
        direction_enabled=True,
    )

    await fan.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/ceiling_fan/command",
        "homeassistant/device/dev-1/ceiling_fan/command/percentage",
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode",
        "homeassistant/device/dev-1/ceiling_fan/command/oscillation",
        "homeassistant/device/dev-1/ceiling_fan/command/direction",
    ]


async def test_on_event_subscribes_to_command_only_when_all_disabled() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        percentage_enabled=False,
        preset_mode_enabled=False,
        oscillation_enabled=False,
        direction_enabled=False,
    )

    await fan.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/ceiling_fan/command"
    ]


async def test_on_event_requires_binding() -> None:
    fan = Fan(unique_id="ceiling_fan")

    with pytest.raises(RuntimeError, match="not bound"):
        await fan.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    await fan.on_event(lambda event: _noop())
    await fan.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/ceiling_fan/command": [fan._dispatch_command],
        "homeassistant/device/dev-1/ceiling_fan/command/percentage": [
            fan._dispatch_percentage
        ],
    }


async def test_dispatch_delivers_command_events() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "ON")
    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "OFF")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "command"
    assert first.topic_type == "command_topic"
    assert first.topic == "homeassistant/device/dev-1/ceiling_fan/command"
    assert first.message == "ON"
    assert first.state == "on"
    assert second.state == "off"


async def test_dispatch_command_uses_custom_payloads() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        payload_on="START",
        payload_off="STOP",
    )
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "START")
    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "STOP")
    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "ON")

    assert [event.state for event in received] == ["on", "off", None]


async def test_dispatch_delivers_percentage_event() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/percentage", "60"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/percentage", "fast"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/percentage", "nan"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/percentage", "101"
    )

    assert len(received) == 4
    first, second, _, _ = received
    assert first.event_type == "percentage"
    assert first.topic_type == "percentage_command_topic"
    assert first.message == "60"
    assert first.state == "60"
    assert second.state is None
    assert received[2].state is None
    assert received[3].state is None


async def test_dispatch_delivers_preset_mode_event() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", preset_mode_enabled=True)
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode", "auto"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode", "reset_percentage"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode", "turbo"
    )

    assert len(received) == 3
    first, second, third = received
    assert first.event_type == "preset_mode"
    assert first.topic_type == "preset_mode_command_topic"
    assert first.state == "auto"
    assert second.state == "reset_percentage"
    assert third.state is None


async def test_dispatch_preset_mode_uses_custom_modes() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(
        provider,
        unique_id="ceiling_fan",
        preset_mode_enabled=True,
        preset_modes=["low", "high"],
    )
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode", "high"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/preset_mode", "auto"
    )

    assert [event.state for event in received] == ["high", None]


async def test_dispatch_delivers_oscillation_event() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", oscillation_enabled=True)
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/oscillation", "oscillate_on"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/oscillation", "oscillate_off"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/oscillation", "maybe"
    )

    assert len(received) == 3
    first, second, third = received
    assert first.event_type == "oscillation"
    assert first.topic_type == "oscillation_command_topic"
    assert first.state == "on"
    assert second.state == "off"
    assert third.state is None


async def test_dispatch_delivers_direction_event() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan", direction_enabled=True)
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/direction", "forward"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/direction", "reverse"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/ceiling_fan/command/direction", "sideways"
    )

    assert len(received) == 3
    first, second, third = received
    assert first.event_type == "direction"
    assert first.topic_type == "direction_command_topic"
    assert first.state == "forward"
    assert second.state == "reverse"
    assert third.state is None


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")
    received: list[Event] = []
    await fan.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", b"ON")

    assert received[0].message == "ON"
    assert received[0].state == "on"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")
    first: list[Event] = []
    second: list[Event] = []
    await fan.on_event(collector(first))
    await fan.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "ON")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, fan = make_bound(provider, unique_id="ceiling_fan")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await fan.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.fan"):
        await provider.deliver("homeassistant/device/dev-1/ceiling_fan/command", "ON")

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan")

    # pl_on/pl_off and spd_rng_min/spd_rng_max are omitted because they match
    # the discovery defaults; percentage control is enabled by default.
    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
    }


async def test_discovery_config_includes_name_and_device_class() -> None:
    _, fan = make_bound(
        RecordingProvider(),
        unique_id="ceiling_fan",
        name="Ceiling fan",
        device_class="ceiling",
    )

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
        "name": "Ceiling fan",
        "dev_cla": "ceiling",
    }


async def test_discovery_config_includes_custom_payloads() -> None:
    _, fan = make_bound(
        RecordingProvider(),
        unique_id="ceiling_fan",
        payload_on="1",
        payload_off="0",
        oscillation_enabled=True,
        payload_oscillation_on="yes",
        payload_oscillation_off="no",
    )

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
        "pl_on": "1",
        "pl_off": "0",
        "osc_stat_t": "~/ceiling_fan/state/oscillation",
        "osc_cmd_t": "~/ceiling_fan/command/oscillation",
        "pl_osc_on": "yes",
        "pl_osc_off": "no",
    }


async def test_discovery_config_with_all_features_enabled() -> None:
    _, fan = make_bound(
        RecordingProvider(),
        unique_id="ceiling_fan",
        preset_mode_enabled=True,
        oscillation_enabled=True,
        direction_enabled=True,
    )

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
        "pr_mode_stat_t": "~/ceiling_fan/state/preset_mode",
        "pr_mode_cmd_t": "~/ceiling_fan/command/preset_mode",
        "osc_stat_t": "~/ceiling_fan/state/oscillation",
        "osc_cmd_t": "~/ceiling_fan/command/oscillation",
        "dir_stat_t": "~/ceiling_fan/state/direction",
        "dir_cmd_t": "~/ceiling_fan/command/direction",
    }


async def test_discovery_config_with_all_features_disabled() -> None:
    _, fan = make_bound(
        RecordingProvider(),
        unique_id="ceiling_fan",
        percentage_enabled=False,
        preset_mode_enabled=False,
        oscillation_enabled=False,
        direction_enabled=False,
    )

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
    }


async def test_discovery_config_includes_custom_modes_and_speed_range() -> None:
    _, fan = make_bound(
        RecordingProvider(),
        unique_id="ceiling_fan",
        preset_mode_enabled=True,
        preset_modes=["low", "medium", "high"],
        payload_reset_percentage="speed",
        speed_range_min=0,
        speed_range_max=10,
    )

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
        "pr_mode_stat_t": "~/ceiling_fan/state/preset_mode",
        "pr_mode_cmd_t": "~/ceiling_fan/command/preset_mode",
        "pr_modes": ["low", "medium", "high"],
        "pl_rst_pct": "speed",
        "spd_rng_min": 0,
        "spd_rng_max": 10,
    }


async def test_discovery_config_includes_optimistic() -> None:
    _, fan = make_bound(RecordingProvider(), unique_id="ceiling_fan", optimistic=True)

    assert fan.discovery_config() == {
        "uniq_id": "ceiling_fan",
        "p": "fan",
        "stat_t": "~/ceiling_fan/state",
        "cmd_t": "~/ceiling_fan/command",
        "pct_stat_t": "~/ceiling_fan/state/percentage",
        "pct_cmd_t": "~/ceiling_fan/command/percentage",
        "opt": True,
    }


async def test_preset_mode_enabled_requires_modes() -> None:
    with pytest.raises(ValueError, match="preset_modes"):
        Fan(unique_id="ceiling_fan", preset_mode_enabled=True, preset_modes=[])


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Fan(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, fan = make_bound(provider, unique_id="ceiling_fan", name="Ceiling fan")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"ceiling_fan": fan.discovery_config()}


async def _noop() -> None:
    return None
