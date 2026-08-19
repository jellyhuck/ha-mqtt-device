"""Device metadata for Home Assistant MQTT device discovery.

``DeviceInfo`` models the fields allowed in the device discovery payload
described at https://www.home-assistant.io/integrations/mqtt/#device-discovery-payload.

The ``cmps`` (components) key is deliberately excluded: individual entities of
the device are represented by separate classes in this project.

The discovery topic for the new format is
``<discovery_prefix>/device/<device_id>/config`` and the payload carries the
``dev`` and ``o`` mappings and the root-level availability options (``avty``).
All topics in the payload are fully resolved.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from typing import Any

__all__ = ["DeviceInfo"]

#: Allowed characters for the device id used as the discovery topic object id
#: (see the "Discovery topic" section of the MQTT integration docs).
_OBJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

#: Placeholder inside the default topic prefix, replaced by the device id.
_DEVICE_ID_PLACEHOLDER = "<device_id>"

#: Home Assistant MQTT discovery default for ``payload_available``.
DEFAULT_PAYLOAD_AVAILABLE = "online"

#: Home Assistant MQTT discovery default for ``payload_not_available``.
DEFAULT_PAYLOAD_NOT_AVAILABLE = "offline"


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Metadata published in the device discovery payload.

    Only ``device_id`` and ``name`` are required; every other field has a sane
    default.

    Attributes:
        device_id: Unique id of the device. Used as the ``object_id`` of the
            discovery topic and as the default identifier. Must consist of
            ``[a-zA-Z0-9_-]`` characters.
        name: Name of the device as shown in Home Assistant.
        manufacturer: Manufacturer of the device (``dev.mf``).
        model: Model of the device (``dev.mdl``).
        model_id: Model id of the device (``dev.mdl_id``).
        sw_version: Software version of the device (``dev.sw``).
        hw_version: Hardware version of the device (``dev.hw``).
        serial_number: Serial number of the device (``dev.sn``).
        suggested_area: Suggested area for the device (``dev.sa``).
        configuration_url: Configuration url of the device (``dev.cu``).
        via_device: Identifier of the parent device (``dev.via_device``).
        connections: List of ``(type, id)`` connections of the device
            (``dev.cns``), for example ``[("mac", "00:11:22:33:44:55")]``.
        identifiers: Additional identifiers of the device (``dev.ids``).
            Defaults to ``[device_id]``.
        topic_prefix: MQTT topic prefix used to resolve shorthand topics. Defaults to
            ``"<discovery_prefix>/device/<device_id>"`` —
            ``"homeassistant/device/<device_id>"`` with the default discovery
            prefix — matching the prefix of the discovery topic. May contain
            ``<device_id>``, which is replaced by the actual device id.
        availability_topic: Topic used for availability updates. A ``~/...``
            value is resolved against ``topic_prefix``. Defaults to ``~/status``.
        availability_payload_available: Payload marking the device available.
        availability_payload_unavailable: Payload marking the device unavailable.
        origin_name: Name of the integration that created the config (``o.name``).
        origin_sw: Version of the integration (``o.sw``).
        origin_url: Support url of the integration (``o.url``).
        discovery_prefix: MQTT discovery prefix, defaults to ``homeassistant``.
    """

    device_id: str
    name: str
    manufacturer: str | None = None
    model: str | None = None
    model_id: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    serial_number: str | None = None
    suggested_area: str | None = None
    configuration_url: str | None = None
    via_device: str | None = None
    connections: list[tuple[str, str]] | None = None
    identifiers: list[str] | None = None
    topic_prefix: str | None = None
    availability_topic: str | None = None
    availability_payload_available: str = DEFAULT_PAYLOAD_AVAILABLE
    availability_payload_unavailable: str = DEFAULT_PAYLOAD_NOT_AVAILABLE
    origin_name: str = "ha-mqtt-device"
    origin_sw: str | None = None
    origin_url: str | None = None
    discovery_prefix: str = "homeassistant"

    def __post_init__(self) -> None:
        if not _OBJECT_ID_RE.fullmatch(self.device_id):
            raise ValueError(
                "device_id must be a non-empty string of [a-zA-Z0-9_-] "
                f"characters, got {self.device_id!r}"
            )
        if not self.name.strip():
            raise ValueError("name must be a non-empty string")
        topic_prefix = self.topic_prefix
        if topic_prefix is None:
            # Default to the same prefix as the discovery topic, e.g.
            # homeassistant/device/<device_id>.
            topic_prefix = f"{self.discovery_prefix}/device/{self.device_id}"
        elif _DEVICE_ID_PLACEHOLDER in topic_prefix:
            topic_prefix = topic_prefix.replace(_DEVICE_ID_PLACEHOLDER, self.device_id)
        object.__setattr__(self, "topic_prefix", topic_prefix)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this device info to a plain dictionary."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "model_id": self.model_id,
            "sw_version": self.sw_version,
            "hw_version": self.hw_version,
            "serial_number": self.serial_number,
            "suggested_area": self.suggested_area,
            "configuration_url": self.configuration_url,
            "via_device": self.via_device,
            "connections": (
                None
                if self.connections is None
                else [list(c) for c in self.connections]
            ),
            "identifiers": self.identifiers,
            "topic_prefix": self.topic_prefix,
            "availability_topic": self.availability_topic,
            "availability_payload_available": self.availability_payload_available,
            "availability_payload_unavailable": self.availability_payload_unavailable,
            "origin_name": self.origin_name,
            "origin_sw": self.origin_sw,
            "origin_url": self.origin_url,
            "discovery_prefix": self.discovery_prefix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceInfo:
        """Deserialize a dictionary produced by :meth:`to_dict`.

        Raises:
            ValueError: If ``device_id`` or ``name`` is missing.
        """
        missing = [key for key in ("device_id", "name") if key not in data]
        if missing:
            raise ValueError(
                f"DeviceInfo is missing required field(s): {', '.join(missing)}"
            )
        valid = {f.name for f in fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in valid}
        if kwargs.get("connections") is not None:
            converted: list[tuple[str, str]] = []
            for pair in kwargs["connections"]:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError("connections entries must be [type, id] pairs")
                converted.append((str(pair[0]), str(pair[1])))
            kwargs["connections"] = converted
        return cls(**kwargs)

    def to_json(self) -> str:
        """Serialize this device info to a JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> DeviceInfo:
        """Deserialize a device info from a JSON string.

        Raises:
            ValueError: If the text is not valid JSON or is missing a
                required field.
            TypeError: If the JSON value is not an object.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid DeviceInfo JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise TypeError("DeviceInfo JSON must be a JSON object")
        return cls.from_dict(data)

    def discovery_payload(self) -> dict[str, Any]:
        """Return the new-format device discovery payload (without ``cmps``)."""
        dev: dict[str, Any] = {
            "ids": list(self.identifiers or [self.device_id]),
            "name": self.name,
        }
        optional: dict[str, Any] = {
            "cns": (
                None
                if self.connections is None
                else [list(pair) for pair in self.connections]
            ),
            "mf": self.manufacturer,
            "mdl": self.model,
            "mdl_id": self.model_id,
            "sw": self.sw_version,
            "hw": self.hw_version,
            "sn": self.serial_number,
            "sa": self.suggested_area,
            "cu": self.configuration_url,
            "via_device": self.via_device,
        }
        for key, value in optional.items():
            if value is not None:
                dev[key] = value

        origin: dict[str, Any] = {"name": self.origin_name}
        if self.origin_sw is not None:
            origin["sw"] = self.origin_sw
        if self.origin_url is not None:
            origin["url"] = self.origin_url

        availability: dict[str, Any] = {
            "topic": self.resolve_topic(self.availability_topic),
        }
        if self.availability_payload_available != DEFAULT_PAYLOAD_AVAILABLE:
            availability["payload_available"] = self.availability_payload_available
        if self.availability_payload_unavailable != DEFAULT_PAYLOAD_NOT_AVAILABLE:
            availability["payload_not_available"] = (
                self.availability_payload_unavailable
            )

        return {
            "dev": dev,
            "o": origin,
            "avty": [availability],
        }

    def discovery_topic(self) -> str:
        """Return the MQTT discovery topic for this device."""
        return f"{self.discovery_prefix}/device/{self.device_id}/config"

    def shorthand_topic(self, topic: str | None = None) -> str:
        """Return ``topic`` as a ``~``-prefixed shorthand.

        ``None`` defaults to ``~/status``. This helper is retained for callers
        that use the internal shorthand topic convention.
        """
        if topic is None:
            return "~/status"
        return topic

    def resolve_topic(self, topic: str | None = None) -> str:
        """Resolve ``topic`` against the device's topic prefix.

        ``None`` and ``~/...`` topics are expanded using ``topic_prefix``, so
        ``~/status`` becomes ``homeassistant/device/<device_id>/status``. Plain
        topics are returned unchanged.
        """
        if topic is None:
            topic = "~/status"
        if topic == "~":
            assert self.topic_prefix is not None  # resolved in __post_init__
            return self.topic_prefix
        if topic.startswith("~/"):
            assert self.topic_prefix is not None  # resolved in __post_init__
            return f"{self.topic_prefix}{topic[1:]}"
        return topic
