"""Integer MQTT value."""

from __future__ import annotations

from ha_mqtt_device.values.value import Value

__all__ = ["IntValue"]


class IntValue(Value[int]):
    """A value that stores and publishes integers."""

    def _serialize_value(self, value: int) -> str:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("IntValue requires an integer")
        return str(value)
