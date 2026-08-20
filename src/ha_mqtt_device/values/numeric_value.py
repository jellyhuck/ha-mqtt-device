"""Numeric MQTT value preserving the caller's integer/float spelling."""

from __future__ import annotations

from math import isfinite

from ha_mqtt_device.values.float_value import FloatValue

__all__ = ["NumericValue"]


class NumericValue(FloatValue):
    """Float-like value that also accepts integers without reformatting them."""

    def _serialize_value(self, value: float) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("NumericValue requires a number")
        if not isfinite(value):
            raise ValueError("NumericValue requires a finite number")
        return str(value)
