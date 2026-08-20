"""Structural coverage for entity-owned StateValue fields."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields

import pytest

from ha_mqtt_device import (
    AlarmControlPanel,
    BinarySensor,
    Button,
    Camera,
    Climate,
    Cover,
    Date,
    DateTime,
    DeviceTracker,
    Entity,
    EventEntity,
    Fan,
    Humidifier,
    Image,
    InfraredEmitter,
    InfraredReceiver,
    LawnMower,
    Light,
    Lock,
    Notify,
    Number,
    Scene,
    SelectEntity,
    Sensor,
    Siren,
    Switch,
    TagScanner,
    Text,
    Time,
    Update,
    Vacuum,
    Valve,
    WaterHeater,
)

PUBLISHING_ENTITIES: tuple[tuple[Callable[[], Entity], int], ...] = (
    (lambda: AlarmControlPanel("alarm"), 1),
    (lambda: BinarySensor("binary"), 1),
    (lambda: Camera("camera"), 1),
    (lambda: Climate("climate"), 4),
    (lambda: Cover("cover"), 2),
    (lambda: Date("date"), 1),
    (lambda: DateTime("datetime"), 1),
    (lambda: DeviceTracker("tracker"), 1),
    (lambda: EventEntity("event", event_types=["pressed"]), 1),
    (
        lambda: Fan(
            "fan",
            preset_mode_enabled=True,
            oscillation_enabled=True,
            direction_enabled=True,
        ),
        5,
    ),
    (lambda: Humidifier("humidifier"), 2),
    (lambda: Image("image"), 1),
    (lambda: InfraredReceiver("receiver"), 1),
    (lambda: LawnMower("mower"), 1),
    (
        lambda: Light(
            "light",
            brightness_enabled=True,
            color_temp_enabled=True,
            rgb_enabled=True,
            hs_enabled=True,
            xy_enabled=True,
            effect_enabled=True,
            white_enabled=True,
        ),
        8,
    ),
    (lambda: Lock("lock"), 1),
    (lambda: Number("number"), 1),
    (lambda: Scene("scene"), 1),
    (lambda: SelectEntity("select"), 1),
    (lambda: Sensor("sensor"), 1),
    (lambda: Siren("siren"), 2),
    (lambda: Switch("switch"), 1),
    (lambda: TagScanner("scanner", topic="~/tags"), 1),
    (lambda: Text("text"), 1),
    (lambda: Time("time"), 1),
    (lambda: Update("update", latest_version_enabled=True), 3),
    (
        lambda: Vacuum(
            "vacuum",
            supported_features=[
                "start",
                "stop",
                "pause",
                "return_home",
                "status",
                "locate",
                "clean_spot",
                "fan_speed",
                "send_command",
            ],
            fan_speed_list=["low"],
            send_command_enabled=True,
            clean_segments_enabled=True,
        ),
        5,
    ),
    (lambda: Valve("valve"), 2),
    (lambda: WaterHeater("heater", power_enabled=True), 4),
)


@pytest.mark.parametrize(("factory", "expected_count"), PUBLISHING_ENTITIES)
def test_publishers_store_state_values_as_private_dataclass_fields(
    factory: Callable[[], Entity], expected_count: int
) -> None:
    entity = factory()
    dataclass_fields = {item.name: item for item in fields(entity)}
    stored = [
        (dataclass_fields[name], value)
        for name, value in vars(entity).items()
        if isinstance(value, Entity.StateValue)
    ]

    assert len(stored) == expected_count
    for item, _value in stored:
        assert item.name.startswith("_")
        assert item.init is False
        assert item.repr is False
        assert item.compare is False


@pytest.mark.parametrize(
    "entity",
    [Button("button"), InfraredEmitter("emitter"), Notify("notify")],
)
def test_receive_only_entities_do_not_store_state_values(entity: Entity) -> None:
    assert not any(
        isinstance(value, Entity.StateValue) for value in vars(entity).values()
    )
