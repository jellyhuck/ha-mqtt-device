"""Floating-point MQTT value."""

from __future__ import annotations

from ha_mqtt_device.values.value import Value

__all__ = ["FloatValue"]


class FloatValue(Value[float]):
    """A value that stores and publishes floating-point numbers."""

    def _serialize_value(self, value: float) -> str:
        if not isinstance(value, float):
            raise TypeError("FloatValue requires a float")
        return str(value)
