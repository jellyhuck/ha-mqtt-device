"""String-enum MQTT value."""

from __future__ import annotations

from enum import StrEnum
from typing import TypeVar

from ha_mqtt_device.values.value import Value

__all__ = ["StrEnumValue"]

E = TypeVar("E", bound=StrEnum)


class StrEnumValue(Value[E]):
    """A value that stores a :class:`enum.StrEnum` member.

    The enum member's string value is published as the MQTT payload. Plain
    strings are not accepted, so the stored value remains the enum member.
    """

    def _serialize_value(self, value: E) -> str:
        if not isinstance(value, StrEnum):
            raise TypeError("StrEnumValue requires a StrEnum")
        return value.value
