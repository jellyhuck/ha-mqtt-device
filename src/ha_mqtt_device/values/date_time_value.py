"""Datetime MQTT value."""

from __future__ import annotations

from datetime import datetime

from ha_mqtt_device.values.value import Value

__all__ = ["DateTimeValue"]


class DateTimeValue(Value[datetime]):
    """A value that stores datetimes and publishes Home Assistant payloads."""

    def _serialize_value(self, value: datetime) -> str:
        if not isinstance(value, datetime):
            raise TypeError("DateTimeValue requires a datetime.datetime")
        return value.strftime("%Y-%m-%d %H:%M:%S")
