"""Base class for entities associated with a Home Assistant MQTT device.

An entity is a pure configuration object until it is bound to a
:class:`~ha_mqtt_device.device.Device`; binding happens automatically when the
entity is passed to the device constructor. Once bound, the entity can publish
state changes through the device's MQTT provider.

Topics follow the convention ``<device topic prefix>/<unique_id>/<topic>``.
For example, an entity named ``is_led_on`` uses the state topic
``homeassistant/device/<device_id>/is_led_on/state`` with the default device
prefix. Topic properties and discovery configs contain fully resolved topics.
"""

from __future__ import annotations

import re
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from ha_mqtt_device.publish_topic import PublishTopic
from ha_mqtt_device.values.value import Value

if TYPE_CHECKING:
    from ha_mqtt_device.device import Device

__all__ = ["Entity"]

T = TypeVar("T")

#: Allowed characters for the entity unique id, which becomes a topic segment
#: and the ``cmps`` object id in the discovery payload.
_UNIQUE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class Entity:
    """A single entity belonging to a Home Assistant device.

    Attributes:
        unique_id: Globally unique id of the entity. Used as the ``uniq_id``
            in the discovery config and as the topic segment of every entity
            topic. Must consist of ``[a-zA-Z0-9_-]`` characters. Entity
            subclasses that publish state expose a ``state_topic`` property;
            command-only entities do not.
        name: Name of the entity as shown in Home Assistant. Omitted from the
            discovery config when unset.
    """

    unique_id: str
    name: str | None = None
    #: The device this entity is bound to; set by :meth:`bind` when the entity
    #: is passed to the ``Device`` constructor.
    device: Device | None = field(default=None, init=False, repr=False)
    _retained_values: list[StateValue[Any]] = field(
        default_factory=list, init=False, repr=False, compare=False
    )

    #: Home Assistant MQTT component name, e.g. ``"binary_sensor"``.
    component: ClassVar[str] = ""

    class StateValue(Generic[T]):
        """A typed value published through an owning entity's MQTT topic.

        The owning entity is held weakly so a state value does not extend the
        entity's lifetime. Use :meth:`Entity._make_momentary_state` or
        :meth:`Entity._make_persistent_state` to construct instances.
        """

        __slots__ = (
            "_entity",
            "_force_update",
            "_retain",
            "_topic_suffix",
            "_value",
        )

        def __init__(
            self,
            value: Value[T],
            topic_suffix: str,
            retain: bool,
            force_update: bool,
            entity: Entity,
        ) -> None:
            self._value = value
            self._topic_suffix = topic_suffix
            self._retain = retain
            self._force_update = force_update
            self._entity: weakref.ReferenceType[Entity] = weakref.ref(entity)
            if retain:
                entity._register_retained_value(self)

        def topic(self) -> PublishTopic:
            """Return this value's resolved topic and retention policy."""
            entity = self._entity()
            if entity is None:
                raise RuntimeError("the owning Entity no longer exists")
            return PublishTopic(
                f"{entity.topic_prefix()}/{self._topic_suffix}",
                self._retain,
            )

        async def set_value(self, new_value: T) -> None:
            """Publish ``new_value`` using this value's topic and retention."""
            entity = self._entity()
            if entity is None:
                raise RuntimeError("the owning Entity no longer exists")

            async def update(payload: str | bytes) -> None:
                await entity._publish(self.topic(), payload)

            await self._value.set_value(new_value, update, self._force_update)

    def __post_init__(self) -> None:
        if not _UNIQUE_ID_RE.fullmatch(self.unique_id):
            raise ValueError(
                "unique_id must be a non-empty string of [a-zA-Z0-9_-] "
                f"characters, got {self.unique_id!r}"
            )

    def topic_prefix(self) -> str:
        """Return this entity's resolved MQTT topic prefix."""
        return f"{self._require_device().topic_prefix()}/{self.unique_id}"

    def command_topic_for(self, suffix: str | None = None) -> str:
        """Return this entity's command topic with an optional suffix."""
        topic = f"{self.topic_prefix()}/command"
        return f"{topic}/{suffix}" if suffix else topic

    def bind(self, device: Device) -> None:
        """Bind this entity to ``device``, giving it access to provider and info.

        Called automatically by the :class:`~ha_mqtt_device.device.Device`
        constructor; do not call it manually.

        Raises:
            RuntimeError: If the entity is already bound.
        """
        if self.device is not None:
            raise RuntimeError(
                f"{type(self).__name__} {self.unique_id!r} is already bound to a Device"
            )
        self.device = device

    def _make_momentary_state(
        self, value: Value[T], topic_suffix: str
    ) -> Entity.StateValue[T]:
        """Create a state value whose publications are not retained."""
        return self._make_state(value, topic_suffix, retain=False, force_update=True)

    def _make_persistent_state(
        self, value: Value[T], topic_suffix: str
    ) -> Entity.StateValue[T]:
        """Create a state value whose publications are retained."""
        return self._make_state(value, topic_suffix, retain=True, force_update=False)

    def _make_state(
        self,
        value: Value[T],
        topic_suffix: str,
        retain: bool = True,
        force_update: bool = False,
    ) -> Entity.StateValue[T]:
        """Create a state value with independent publication policies."""
        return Entity.StateValue(value, topic_suffix, retain, force_update, self)

    def _register_retained_value(self, value: StateValue[Any]) -> None:
        self._retained_values.append(value)

    async def _publish(self, topic: PublishTopic, message: str | bytes) -> None:
        """Publish a payload using a topic descriptor."""
        device = self._require_device()
        await device.provider.publish(topic.topic, message, retain=topic.retain)

    async def _on_remove(self) -> None:
        """Clear every retained topic registered by this entity."""
        device = self._require_device()
        cleared_topics: set[str] = set()
        for value in self._retained_values:
            descriptor = value.topic()
            if descriptor.topic in cleared_topics:
                continue
            await device.provider.publish(descriptor.topic, "", retain=True)
            cleared_topics.add(descriptor.topic)

    def _require_device(self) -> Device:
        """Return the bound device or raise a helpful error."""
        if self.device is None:
            raise RuntimeError(
                f"{type(self).__name__} {self.unique_id!r} is not bound to a "
                "Device; pass it via Device(..., entities=[...])"
            )
        return self.device

    def discovery_config(self) -> dict[str, Any]:
        """Return this entity's ``cmps`` config entry for the discovery payload."""
        config: dict[str, Any] = {
            "uniq_id": self.unique_id,
            "p": self.component,
        }
        if self.name is not None:
            config["name"] = self.name
        return config

    def _resolve_discovery_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Resolve shorthand topics contained in an entity discovery config."""
        device = self._require_device()

        def resolve(value: Any) -> Any:
            if isinstance(value, str):
                return device.info.resolve_topic(value)
            if isinstance(value, dict):
                return {key: resolve(item) for key, item in value.items()}
            if isinstance(value, list):
                return [resolve(item) for item in value]
            return value

        return resolve(config)
