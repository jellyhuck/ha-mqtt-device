"""Event entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass, field

from ha_mqtt_device.entity import Entity

__all__ = ["EventEntity"]


@dataclass
class EventEntity(Entity):
    """An event entity belonging to a device.

    An event entity fires transient events to Home Assistant; events have no
    state. The device publishes an event type to the state topic
    (``~/<unique_id>/state``) with :meth:`set_event`, and Home Assistant fires
    an HA event whose ``event_type`` is the published payload. The entity has
    no command topic — events flow from the device to Home Assistant only.
    Create it with a unique id and at least one event type::

        doorbell = EventEntity(
            unique_id="doorbell",
            name="Doorbell",
            device_class="doorbell",
            event_types=["doorbell_pressed", "doorbell_long_press"],
        )
        device = Device(provider, info, entities=[doorbell])

        async with device:
            await doorbell.set_event("doorbell_pressed")

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"doorbell"`` or ``"button"``. Omitted from the discovery config
            when unset.
        event_types: Event types that can be fired (``evt_typ``). Must contain
            at least one type.
        event_type_template: Template that extracts the event type from the
            payload (``eve_tt``). Mutually exclusive with
            :attr:`value_template`.
        value_template: Template that extracts the event value from the
            payload (``val_tpl``). Mutually exclusive with
            :attr:`event_type_template`.
    """

    component = "event"

    device_class: str | None = None
    event_types: list[str] = field(default_factory=list)
    event_type_template: str | None = None
    value_template: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.event_types:
            raise ValueError("event_types must contain at least one event type")
        if self.event_type_template is not None and self.value_template is not None:
            raise ValueError(
                "event_type_template and value_template are mutually exclusive"
            )

    async def set_event(self, event_type: str) -> None:
        """Publish ``event_type`` as an event to Home Assistant.

        ``event_type`` must be one of :attr:`event_types`; it is published to
        the state topic (``~/<unique_id>/state``).

        Raises:
            RuntimeError: If the entity is not bound to a device.
            ValueError: If ``event_type`` is not in :attr:`event_types`.
            Exception: If the message could not be published.
        """
        if event_type not in self.event_types:
            raise ValueError(
                f"event_type {event_type!r} is not in event_types {self.event_types!r}"
            )
        await self._publish(
            self._register_publish_topic(self.state_topic, retain=False), event_type
        )

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this entity's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["evt_typ"] = self.event_types
        if self.event_type_template is not None:
            config["eve_tt"] = self.event_type_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return config
