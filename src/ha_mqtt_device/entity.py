"""Base class for entities associated with a Home Assistant MQTT device.

An entity is a pure configuration object until it is bound to a
:class:`~ha_mqtt_device.device.Device`; binding happens automatically when the
entity is passed to the device constructor. Once bound, the entity can publish
state changes through the device's MQTT provider.

Topics follow the convention ``~/<unique_id>/<topic>``: the device's topic
prefix (published as ``~`` in the discovery payload) is followed by the
entity's ``unique_id`` and then the per-entity topic, for example the state
topic ``~/is_led_on/state``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from ha_mqtt_device.publish_topic import PublishTopic

if TYPE_CHECKING:
    from ha_mqtt_device.device import Device

__all__ = ["Entity"]

#: Allowed characters for the entity unique id, which becomes a topic segment
#: (``~/<unique_id>/...``) and the ``cmps`` object id in the discovery payload.
_UNIQUE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class Entity:
    """A single entity belonging to a Home Assistant device.

    Attributes:
        unique_id: Globally unique id of the entity. Used as the ``uniq_id``
            in the discovery config and as the topic segment of every entity
            topic (for example ``~/<unique_id>/state``). Must consist of
        ``[a-zA-Z0-9_-]`` characters. Entity subclasses that publish state
        expose a ``state_topic`` property; command-only entities do not.
        name: Name of the entity as shown in Home Assistant. Omitted from the
            discovery config when unset.
    """

    unique_id: str
    name: str | None = None
    #: The device this entity is bound to; set by :meth:`bind` when the entity
    #: is passed to the ``Device`` constructor.
    device: Device | None = field(default=None, init=False, repr=False)
    _publish_topics: dict[str, PublishTopic] = field(
        default_factory=dict, init=False, repr=False
    )

    #: Home Assistant MQTT component name, e.g. ``"binary_sensor"``.
    component: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if not _UNIQUE_ID_RE.fullmatch(self.unique_id):
            raise ValueError(
                "unique_id must be a non-empty string of [a-zA-Z0-9_-] "
                f"characters, got {self.unique_id!r}"
            )

    @staticmethod
    def command_topic_for(unique_id: str, suffix: str | None = None) -> str:
        """Build a command topic for ``unique_id`` and an optional suffix."""
        topic = f"~/{unique_id}/command"
        return f"{topic}/{suffix}" if suffix else topic

    @staticmethod
    def state_topic_for(unique_id: str, suffix: str | None = None) -> str:
        """Build a state topic for ``unique_id`` and an optional suffix."""
        topic = f"~/{unique_id}/state"
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

    def _register_publish_topic(self, topic: str, *, retain: bool) -> PublishTopic:
        """Register and return a resolved topic descriptor.

        Raises:
            ValueError: If the topic was already registered with another
                retention policy.
        """
        device = self._require_device()
        resolved_topic = device.info.resolve_topic(topic)
        descriptor = PublishTopic(resolved_topic, retain)
        existing = self._publish_topics.get(resolved_topic)
        if existing is not None and existing.retain != retain:
            raise ValueError(
                f"topic {resolved_topic!r} was registered with conflicting "
                "retention policies"
            )
        self._publish_topics[resolved_topic] = descriptor
        return existing or descriptor

    async def _publish(self, topic: PublishTopic, message: str | bytes) -> None:
        """Publish a payload using a registered topic descriptor."""
        device = self._require_device()
        await device.provider.publish(topic.topic, message, retain=topic.retain)

    async def _on_remove(self) -> None:
        """Clear every retained topic registered by this entity."""
        device = self._require_device()
        for descriptor in self._publish_topics.values():
            if descriptor.retain:
                await device.provider.publish(descriptor.topic, "", retain=True)

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
