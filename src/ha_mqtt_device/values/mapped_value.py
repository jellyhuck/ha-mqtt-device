"""Mapped value used by entities with configurable update payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Generic, TypeVar

from ha_mqtt_device.values.value import Value

__all__ = ["MappedValue"]

T = TypeVar("T")


class MappedValue(Value[T], Generic[T]):
    """Store a canonical value while publishing a configured payload."""

    __slots__ = ("_payloads",)

    def __init__(self, payloads: Mapping[T, str]) -> None:
        super().__init__()
        self._payloads = dict(payloads)

    def _serialize_value(self, value: T) -> str:
        try:
            return self._payloads[value]
        except KeyError:
            raise ValueError(f"value {value!r} is not mapped") from None
