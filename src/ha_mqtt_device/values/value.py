"""Generic base class for typed values with update callbacks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

__all__ = ["Value"]

T = TypeVar("T")


class Value(ABC, Generic[T]):
    """A typed value whose changes can be sent to an update callback.

    Values start unset. A setter updates the first value, changed values,
    and values explicitly marked for update. The in-memory value changes
    only after an update succeeds.
    """

    __slots__ = ("_value",)

    def __init__(self) -> None:
        self._value: T | None = None

    @property
    def value(self) -> T | None:
        """Return the current value, or ``None`` while it is unset."""
        return self._value

    async def set_value(
        self,
        new_value: T,
        updater: Callable[[str | bytes], Awaitable[None]],
        force_update: bool = False,
    ) -> None:
        """Set and, when needed, update the consumer with ``new_value``.

        Raises:
            TypeError: If ``new_value`` is ``None`` or has the wrong type for
                the concrete value class.
            Exception: If ``updater`` cannot update the value.
        """
        if new_value is None:
            raise TypeError("value cannot be None")

        payload = self._serialize_value(new_value)
        if force_update or new_value != self._value:
            await updater(payload)
            self._value = new_value

    @abstractmethod
    def _serialize_value(self, value: T) -> str | bytes:
        """Validate ``value`` and convert it to an update payload."""
        raise NotImplementedError
