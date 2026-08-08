"""Tests for DeviceInfo: defaults, payload mapping, JSON round-trip, validation."""

from __future__ import annotations

import pytest

from ha_mqtt_device.device_info import DeviceInfo


def test_defaults_require_only_device_id_and_name() -> None:
    info = DeviceInfo(device_id="my_device_id", name="My device")

    assert info.device_id == "my_device_id"
    assert info.name == "My device"
    assert info.manufacturer is None
    assert info.identifiers is None
    assert info.topic_prefix == "homeassistant/device/my_device_id"
    assert info.availability_topic is None


def test_default_discovery_payload() -> None:
    info = DeviceInfo(device_id="my_device_id", name="My device")

    payload = info.discovery_payload()

    assert payload["dev"] == {"ids": ["my_device_id"], "name": "My device"}
    assert payload["o"] == {"name": "ha-mqtt-device"}
    assert payload["~"] == "homeassistant/device/my_device_id"
    assert payload["avty"] == [
        {
            "topic": "~/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
    ]
    assert "cmps" not in payload


def test_full_field_mapping_to_abbreviated_keys() -> None:
    info = DeviceInfo(
        device_id="dev_1",
        name="Device",
        manufacturer="Acme",
        model="Widget",
        model_id="W-42",
        sw_version="1.2.3",
        hw_version="rev2",
        serial_number="SN-123",
        suggested_area="Living room",
        configuration_url="https://example.com/config",
        via_device="hub-1",
        connections=[("mac", "00:11:22:33:44:55")],
        identifiers=["extra-id"],
        origin_name="my-integration",
        origin_sw="0.9",
        origin_url="https://example.com/support",
    )

    payload = info.discovery_payload()

    assert payload["dev"] == {
        "ids": ["extra-id"],
        "name": "Device",
        "mf": "Acme",
        "mdl": "Widget",
        "mdl_id": "W-42",
        "sw": "1.2.3",
        "hw": "rev2",
        "sn": "SN-123",
        "sa": "Living room",
        "cu": "https://example.com/config",
        "via_device": "hub-1",
        "cns": [["mac", "00:11:22:33:44:55"]],
    }
    assert payload["o"] == {
        "name": "my-integration",
        "sw": "0.9",
        "url": "https://example.com/support",
    }


def test_identifiers_default_to_device_id() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert info.discovery_payload()["dev"]["ids"] == ["dev-1"]

    overridden = DeviceInfo(device_id="dev-1", name="Device", identifiers=["other"])
    assert overridden.discovery_payload()["dev"]["ids"] == ["other"]


def test_connections_round_trip_via_json() -> None:
    info = DeviceInfo(
        device_id="dev-1",
        name="Device",
        connections=[("mac", "00:11:22:33:44:55"), ("zip", "12345")],
    )

    restored = DeviceInfo.from_json(info.to_json())

    assert restored == info
    assert restored.connections == [("mac", "00:11:22:33:44:55"), ("zip", "12345")]


def test_json_round_trip_preserves_all_fields() -> None:
    info = DeviceInfo(
        device_id="dev-1",
        name="Device",
        manufacturer="Acme",
        model="Widget",
        model_id="W-42",
        sw_version="1.2.3",
        hw_version="rev2",
        serial_number="SN-123",
        suggested_area="Living room",
        configuration_url="https://example.com/config",
        via_device="hub-1",
        connections=[("mac", "00:11:22:33:44:55")],
        identifiers=["extra-id"],
        topic_prefix="custom/prefix",
        availability_topic="custom/status",
        availability_payload_available="up",
        availability_payload_unavailable="down",
        origin_name="my-integration",
        origin_sw="0.9",
        origin_url="https://example.com/support",
        discovery_prefix="myhome",
    )

    restored = DeviceInfo.from_json(info.to_json())

    assert restored == info


def test_to_dict_and_from_dict_round_trip() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert DeviceInfo.from_dict(info.to_dict()) == info


def test_from_dict_missing_required_fields_raises() -> None:
    with pytest.raises(ValueError, match="device_id"):
        DeviceInfo.from_dict({"name": "Device"})
    with pytest.raises(ValueError, match="name"):
        DeviceInfo.from_dict({"device_id": "dev-1"})


def test_from_dict_ignores_unknown_keys() -> None:
    data = DeviceInfo(device_id="dev-1", name="Device").to_dict()
    data["unknown_key"] = "ignored"

    assert DeviceInfo.from_dict(data) == DeviceInfo(device_id="dev-1", name="Device")


def test_from_json_invalid_input_raises() -> None:
    with pytest.raises(ValueError, match="invalid DeviceInfo JSON"):
        DeviceInfo.from_json("not json")
    with pytest.raises(TypeError, match="JSON object"):
        DeviceInfo.from_json("[1, 2, 3]")


def test_validation_rejects_invalid_device_id() -> None:
    for bad in ("", "has/slash", "has#hash", "has+plus", "has space", "has\0null"):
        with pytest.raises(ValueError, match="device_id"):
            DeviceInfo(device_id=bad, name="Device")


def test_validation_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        DeviceInfo(device_id="dev-1", name="")
    with pytest.raises(ValueError, match="name"):
        DeviceInfo(device_id="dev-1", name="   ")


def test_discovery_topic_default_and_custom_prefix() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert info.discovery_topic() == "homeassistant/device/dev-1/config"

    custom = DeviceInfo(device_id="dev-1", name="Device", discovery_prefix="myhome")
    assert custom.discovery_topic() == "myhome/device/dev-1/config"


def test_shorthand_topic_defaults_to_status() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert info.shorthand_topic(None) == "~/status"
    assert info.shorthand_topic("~/state") == "~/state"
    assert info.shorthand_topic("~") == "~"
    assert info.shorthand_topic("plain/topic") == "plain/topic"


def test_resolve_topic_expands_prefix() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert info.resolve_topic(None) == "homeassistant/device/dev-1/status"
    assert info.resolve_topic("~/status") == "homeassistant/device/dev-1/status"
    assert info.resolve_topic("~") == "homeassistant/device/dev-1"
    assert info.resolve_topic("plain/topic") == "plain/topic"


def test_topic_prefix_defaults_to_discovery_prefix() -> None:
    info = DeviceInfo(device_id="dev-1", name="Device")

    assert info.topic_prefix == "homeassistant/device/dev-1"
    assert info.discovery_payload()["~"] == "homeassistant/device/dev-1"

    custom = DeviceInfo(device_id="dev-1", name="Device", discovery_prefix="myhome")
    assert custom.topic_prefix == "myhome/device/dev-1"
    assert custom.discovery_payload()["~"] == "myhome/device/dev-1"


def test_custom_topic_prefix_placeholder_is_resolved() -> None:
    info = DeviceInfo(
        device_id="dev-1",
        name="Device",
        topic_prefix="custom/<device_id>/prefix",
    )

    assert info.topic_prefix == "custom/dev-1/prefix"
    assert info.discovery_payload()["~"] == "custom/dev-1/prefix"


def test_custom_availability_config_appears_in_payload() -> None:
    info = DeviceInfo(
        device_id="dev-1",
        name="Device",
        topic_prefix="home/dev",
        availability_topic="~/state",
        availability_payload_available="up",
        availability_payload_unavailable="down",
    )

    # The payload keeps the "~" shorthand; Home Assistant resolves it.
    assert info.discovery_payload()["avty"] == [
        {
            "topic": "~/state",
            "payload_available": "up",
            "payload_not_available": "down",
        }
    ]
    assert info.discovery_payload()["~"] == "home/dev"
