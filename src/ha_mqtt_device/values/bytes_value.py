"""Binary MQTT value used by image-like entities."""

from __future__ import annotations

from ha_mqtt_device.values.value import Value

__all__ = ["BytesValue"]


class BytesValue(Value[bytes]):
    """A value that stores and publishes raw bytes."""

    def _serialize_value(self, value: bytes) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError("BytesValue requires bytes")
        return value
