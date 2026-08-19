"""String MQTT value."""

from __future__ import annotations

from ha_mqtt_device.values.value import Value

__all__ = ["StrValue"]


class StrValue(Value[str]):
    """A value that stores and publishes strings."""

    def _serialize_value(self, value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("StrValue requires a string")
        return value
