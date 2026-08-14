"""Cross-entity Device discovery and identity regression tests."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from ha_mqtt_device import (
    AlarmControlPanel,
    Device,
    DeviceInfo,
    Entity,
    Lock,
    Notify,
    Scene,
    SelectEntity,
    Siren,
    TagScanner,
    Text,
    Time,
    Update,
    Vacuum,
    Valve,
    WaterHeater,
)
from ha_mqtt_device.provider import MqttMessageCallback


class RecordingProvider:
    """Minimal provider for discovery-only Device tests."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str | bytes]] = []

    async def publish(self, topic: str, message: str | bytes) -> None:
        self.published.append((topic, message))

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        return None

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def regular_entities() -> list[Entity]:
    """Return one instance of every new entity that uses ``cmps``."""
    return [
        AlarmControlPanel(unique_id="alarm"),
        Lock(unique_id="lock"),
        Notify(unique_id="notify"),
        Scene(unique_id="scene"),
        SelectEntity(unique_id="select"),
        Siren(unique_id="siren"),
        Text(unique_id="text"),
        Time(unique_id="time"),
        Update(unique_id="update"),
        Vacuum(unique_id="vacuum"),
        Valve(unique_id="valve"),
        WaterHeater(unique_id="water_heater"),
    ]


ENTITY_FACTORIES: tuple[Callable[[str], Entity], ...] = (
    lambda unique_id: AlarmControlPanel(unique_id=unique_id),
    lambda unique_id: Lock(unique_id=unique_id),
    lambda unique_id: Notify(unique_id=unique_id),
    lambda unique_id: Scene(unique_id=unique_id),
    lambda unique_id: SelectEntity(unique_id=unique_id),
    lambda unique_id: Siren(unique_id=unique_id),
    lambda unique_id: TagScanner(unique_id=unique_id, topic="~/tag/scanned"),
    lambda unique_id: Text(unique_id=unique_id),
    lambda unique_id: Time(unique_id=unique_id),
    lambda unique_id: Update(unique_id=unique_id),
    lambda unique_id: Vacuum(unique_id=unique_id),
    lambda unique_id: Valve(unique_id=unique_id),
    lambda unique_id: WaterHeater(unique_id=unique_id),
)


async def test_all_regular_sprint_entities_bind_and_join_cmps() -> None:
    provider = RecordingProvider()
    entities = regular_entities()
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=entities,
    )

    assert all(entity.device is device for entity in entities)
    await device.configure()

    payload = json.loads(provider.published[0][1])
    assert set(payload["cmps"]) == {entity.component for entity in entities}
    assert all(
        payload["cmps"][entity.component][entity.unique_id] == entity.discovery_config()
        for entity in entities
    )


async def test_tag_scanner_binds_through_standalone_discovery() -> None:
    provider = RecordingProvider()
    scanner = TagScanner(unique_id="tag_scanner", topic="~/tag/scanned")
    device = Device(
        provider,
        DeviceInfo(device_id="dev-1", name="Device"),
        entities=[scanner],
    )

    assert scanner.device is device
    await device.configure()

    device_payload = json.loads(provider.published[0][1])
    tag_payload = json.loads(provider.published[1][1])
    assert "cmps" not in device_payload
    assert provider.published[1][0] == "homeassistant/tag/tag_scanner/config"
    assert tag_payload == {
        "t": "~/tag/scanned",
        "dev": device.info.discovery_payload()["dev"],
    }


@pytest.mark.parametrize("factory", ENTITY_FACTORIES)
async def test_each_sprint_entity_rejects_duplicate_component_and_unique_id(
    factory: Callable[[str], Entity],
) -> None:
    provider = RecordingProvider()
    first = factory("duplicate")
    second = factory("duplicate")

    with pytest.raises(ValueError, match="duplicate entity component/unique_id"):
        Device(
            provider,
            DeviceInfo(device_id="dev-1", name="Device"),
            entities=[first, second],
        )

    assert first.device is None
    assert second.device is None
