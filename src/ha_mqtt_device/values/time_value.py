"""Time MQTT value."""

from __future__ import annotations

from datetime import time

from ha_mqtt_device.values.value import Value

__all__ = ["TimeValue"]


class TimeValue(Value[time]):
    """A value that stores times and publishes ``HH:MM:SS`` payloads."""

    def _serialize_value(self, value: time) -> str:
        if not isinstance(value, time):
            raise TypeError("TimeValue requires a datetime.time")
        if value.microsecond:
            raise ValueError("time values must not contain fractional seconds")
        return value.strftime("%H:%M:%S")
