"""Tests for Climate using a recording fake MqttProvider — no broker needed."""

from __future__ import annotations

import json
from typing import Any

import pytest
from recording_provider import RecordingProvider

from ha_mqtt_device.climate import Climate
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.event import Event, EventCallback


def make_bound(
    provider: RecordingProvider, **entity_kwargs: Any
) -> tuple[Device, Climate]:
    """Build a device and a bound climate with the given kwargs."""
    climate = Climate(**entity_kwargs)
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[climate],
    )
    return device, climate


def collector(received: list[Event]) -> EventCallback:
    """Return an async callback that appends events to ``received``."""

    async def collect(event: Event) -> None:
        received.append(event)

    return collect


async def test_set_current_temperature_publishes_to_topic() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_current_temperature(21.5)

    assert provider.published == [
        (
            "homeassistant/device/dev-1/thermostat/state/current_temperature",
            "21.5",
            True,
        )
    ]


async def test_set_target_temperature_publishes_to_state_topic() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_target_temperature(21.5)

    assert provider.published == [
        ("homeassistant/device/dev-1/thermostat/state/temperature", "21.5", True)
    ]


async def test_set_mode_publishes_verbatim() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_mode("heat")

    assert provider.published == [
        ("homeassistant/device/dev-1/thermostat/state/mode", "heat", True)
    ]


async def test_set_mode_validates_against_modes() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(
        provider, unique_id="thermostat", modes=["off", "heat", "cool"]
    )

    with pytest.raises(ValueError, match="not in modes"):
        await climate.set_mode("auto")


async def test_set_mode_without_modes_accepts_any_mode() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_mode("fan_only")

    assert provider.published == [
        ("homeassistant/device/dev-1/thermostat/state/mode", "fan_only", True)
    ]


async def test_set_action_publishes_verbatim() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_action("heating")

    assert provider.published == [
        ("homeassistant/device/dev-1/thermostat/state/action", "heating", False)
    ]


async def test_set_target_temperature_requires_binding() -> None:
    climate = Climate(unique_id="thermostat")

    with pytest.raises(RuntimeError, match="not bound"):
        await climate.set_target_temperature(21.5)


async def test_set_mode_requires_binding() -> None:
    climate = Climate(unique_id="thermostat")

    with pytest.raises(RuntimeError, match="not bound"):
        await climate.set_mode("heat")


async def test_topics_shorthand() -> None:
    _, climate = make_bound(RecordingProvider(), unique_id="thermostat")

    assert climate.current_temperature_topic == "~/thermostat/state/current_temperature"
    assert climate.temperature_state_topic == "~/thermostat/state/temperature"
    assert climate.temperature_command_topic == "~/thermostat/command/temperature"
    assert climate.mode_state_topic == "~/thermostat/state/mode"
    assert climate.mode_command_topic == "~/thermostat/command/mode"
    assert climate.action_topic == "~/thermostat/state/action"


async def test_publish_methods_do_not_subscribe() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.set_target_temperature(21.5)
    await climate.set_mode("heat")

    assert provider.subscriptions == {}


async def test_on_event_subscribes_to_both_resolved_command_topics() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.on_event(lambda event: _noop())

    assert list(provider.subscriptions) == [
        "homeassistant/device/dev-1/thermostat/command/temperature",
        "homeassistant/device/dev-1/thermostat/command/mode",
    ]


async def test_on_event_requires_binding() -> None:
    climate = Climate(unique_id="thermostat")

    with pytest.raises(RuntimeError, match="not bound"):
        await climate.on_event(lambda event: _noop())


async def test_on_event_subscribes_once_for_multiple_callbacks() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    await climate.on_event(lambda event: _noop())
    await climate.on_event(lambda event: _noop())

    assert provider.subscriptions == {
        "homeassistant/device/dev-1/thermostat/command/temperature": [
            climate._dispatch_temperature
        ],
        "homeassistant/device/dev-1/thermostat/command/mode": [climate._dispatch_mode],
    }


async def test_dispatch_delivers_temperature_event() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", "21.5"
    )

    assert len(received) == 1
    event = received[0]
    assert event.event_type == "temperature"
    assert event.topic_type == "temperature_command_topic"
    assert event.topic == "homeassistant/device/dev-1/thermostat/command/temperature"
    assert event.message == "21.5"
    assert event.state == "21.5"


async def test_dispatch_temperature_unknown_payload_has_null_state() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", "hot"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", ""
    )

    assert [event.state for event in received] == [None, None]


async def test_dispatch_delivers_mode_event() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/thermostat/command/mode", "heat")
    await provider.deliver("homeassistant/device/dev-1/thermostat/command/mode", "auto")

    assert len(received) == 2
    first, second = received
    assert first.event_type == "mode"
    assert first.topic_type == "mode_command_topic"
    assert first.topic == "homeassistant/device/dev-1/thermostat/command/mode"
    assert first.message == "heat"
    assert first.state == "heat"
    assert second.state == "auto"


async def test_dispatch_mode_unknown_payload_is_delivered_verbatim() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/thermostat/command/mode", "eco")

    assert len(received) == 1
    assert received[0].message == "eco"
    assert received[0].state == "eco"


async def test_dispatch_mode_rejects_unconfigured_mode() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat", modes=["off", "heat"])
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver("homeassistant/device/dev-1/thermostat/command/mode", "eco")

    assert received[0].message == "eco"
    assert received[0].state is None


async def test_dispatch_temperature_rejects_non_finite_and_out_of_range_values() -> (
    None
):
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat", min_temp=10, max_temp=30)
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", "nan"
    )
    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", "31"
    )

    assert [event.state for event in received] == [None, None]


async def test_dispatch_decodes_utf8_payload() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    received: list[Event] = []
    await climate.on_event(collector(received))

    await provider.deliver(
        "homeassistant/device/dev-1/thermostat/command/temperature", b"21.5"
    )

    assert received[0].message == "21.5"
    assert received[0].state == "21.5"


async def test_dispatch_invokes_all_callbacks() -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")
    first: list[Event] = []
    second: list[Event] = []
    await climate.on_event(collector(first))
    await climate.on_event(collector(second))

    await provider.deliver("homeassistant/device/dev-1/thermostat/command/mode", "heat")

    assert len(first) == 1
    assert len(second) == 1
    assert first[0] == second[0]


async def test_dispatch_logs_callback_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = RecordingProvider()
    _, climate = make_bound(provider, unique_id="thermostat")

    async def boom(event: Event) -> None:
        raise RuntimeError("callback exploded")

    await climate.on_event(boom)

    with caplog.at_level("ERROR", logger="ha_mqtt_device.climate"):
        await provider.deliver(
            "homeassistant/device/dev-1/thermostat/command/mode", "heat"
        )

    assert "callback exploded" in caplog.text


async def test_discovery_config_defaults() -> None:
    _, climate = make_bound(RecordingProvider(), unique_id="thermostat")

    assert climate.discovery_config() == {
        "uniq_id": "thermostat",
        "p": "climate",
        "curr_temp_t": "homeassistant/device/dev-1/thermostat/state/current_temperature",
        "temp_stat_t": "homeassistant/device/dev-1/thermostat/state/temperature",
        "temp_cmd_t": "homeassistant/device/dev-1/thermostat/command/temperature",
        "mode_stat_t": "homeassistant/device/dev-1/thermostat/state/mode",
        "mode_cmd_t": "homeassistant/device/dev-1/thermostat/command/mode",
        "act_t": "homeassistant/device/dev-1/thermostat/state/action",
    }


async def test_discovery_config_includes_name() -> None:
    _, climate = make_bound(
        RecordingProvider(), unique_id="thermostat", name="Thermostat"
    )

    assert climate.discovery_config()["name"] == "Thermostat"


async def test_discovery_config_includes_modes_unit_and_bounds() -> None:
    _, climate = make_bound(
        RecordingProvider(),
        unique_id="thermostat",
        modes=["off", "heat", "cool", "auto"],
        temperature_unit="F",
        min_temp=60,
        max_temp=90,
        temp_step=1,
    )

    assert climate.discovery_config() == {
        "uniq_id": "thermostat",
        "p": "climate",
        "curr_temp_t": "homeassistant/device/dev-1/thermostat/state/current_temperature",
        "temp_stat_t": "homeassistant/device/dev-1/thermostat/state/temperature",
        "temp_cmd_t": "homeassistant/device/dev-1/thermostat/command/temperature",
        "mode_stat_t": "homeassistant/device/dev-1/thermostat/state/mode",
        "mode_cmd_t": "homeassistant/device/dev-1/thermostat/command/mode",
        "act_t": "homeassistant/device/dev-1/thermostat/state/action",
        "modes": ["off", "heat", "cool", "auto"],
        "temp_unit": "F",
        "min_temp": 60,
        "max_temp": 90,
        "temp_step": 1,
    }


async def test_discovery_config_includes_precision_and_initial() -> None:
    _, climate = make_bound(
        RecordingProvider(),
        unique_id="thermostat",
        precision=0.5,
        initial=21.0,
    )

    assert climate.discovery_config()["prec"] == 0.5
    assert climate.discovery_config()["init"] == 21.0


async def test_discovery_config_includes_optimistic_flags() -> None:
    _, climate = make_bound(
        RecordingProvider(), unique_id="thermostat", mode_opt=True, temp_opt=True
    )

    assert climate.discovery_config()["mode_opt"] is True
    assert climate.discovery_config()["temp_opt"] is True


async def test_unique_id_validation() -> None:
    with pytest.raises(ValueError, match="unique_id"):
        Climate(unique_id="bad id!")


async def test_configure_includes_cmps() -> None:
    provider = RecordingProvider()
    device, climate = make_bound(provider, unique_id="thermostat", name="Thermostat")

    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert payload["cmps"] == {"thermostat": climate.discovery_config()}


async def _noop() -> None:
    return None
