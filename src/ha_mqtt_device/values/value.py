"""Generic base class for typed MQTT-published values."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ha_mqtt_device.provider import MqttProvider
from ha_mqtt_device.publish_topic import PublishTopic

__all__ = ["Value"]

T = TypeVar("T")


class Value(ABC, Generic[T]):
    """A typed value whose changes can be published to one MQTT topic.

    Values start unset. A setter publishes the first value, changed values,
    and values explicitly marked for publication. The in-memory value changes
    only after a publication succeeds.
    """

    __slots__ = ("_publish_topic", "_value")

    def __init__(self, publish_topic: PublishTopic) -> None:
        self._value: T | None = None
        self._publish_topic = publish_topic

    @property
    def value(self) -> T | None:
        """Return the current value, or ``None`` while it is unset."""
        return self._value

    @property
    def publish_topic(self) -> PublishTopic:
        """Return the MQTT topic descriptor used for publications."""
        return self._publish_topic

    async def set_value(
        self,
        new_value: T,
        provider: MqttProvider,
        force_publish: bool = False,
    ) -> None:
        """Set and, when needed, publish ``new_value``.

        Raises:
            TypeError: If ``new_value`` is ``None`` or has the wrong type for
                the concrete value class.
            Exception: If the provider cannot publish the value.
        """
        if new_value is None:
            raise TypeError("value cannot be None")

        payload = self._serialize_value(new_value)
        if self._value is None or self._value != new_value or force_publish:
            await provider.publish(
                self._publish_topic.topic,
                payload,
                retain=self._publish_topic.retain,
            )
            self._value = new_value

    @abstractmethod
    def _serialize_value(self, value: T) -> str:
        """Validate ``value`` and convert it to an MQTT payload."""
        raise NotImplementedError
