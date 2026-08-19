"""Date MQTT value."""

from __future__ import annotations

from datetime import date, datetime

from ha_mqtt_device.values.value import Value

__all__ = ["DateValue"]


class DateValue(Value[date]):
    """A value that stores dates and publishes ISO date strings."""

    def _serialize_value(self, value: date) -> str:
        if isinstance(value, datetime) or not isinstance(value, date):
            raise TypeError("DateValue requires a datetime.date")
        return value.isoformat()
