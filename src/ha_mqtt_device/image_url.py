"""URL-based image entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass, field

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.values.str_value import StrValue

__all__ = ["ImageUrl"]


@dataclass
class ImageUrl(Entity):
    """An image entity whose content is supplied by a published URL.

    The device publishes an image URL to Home Assistant over MQTT; Home
    Assistant downloads the image from that URL. Create it with a unique id,
    pass it to the device constructor, and publish URLs with
    :meth:`set_url`::

        snapshot = ImageUrl(unique_id="camera", name="Camera")
        device = Device(provider, info, entities=[snapshot])

        async with device:
            await snapshot.set_url("https://example.com/image.jpg")

    URL publications are retained so Home Assistant can recover the current
    image after a restart. The URL is published verbatim; URL validation and
    image downloading are handled by Home Assistant.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
    """

    component = "image"

    _url_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._url_value = self._make_persistent_state(StrValue(), "url")

    @property
    def url_topic(self) -> str:
        """Return the resolved MQTT topic used for image URL publications."""
        return self._url_value.topic().topic

    async def set_url(self, url: str) -> None:
        """Publish an image URL to Home Assistant.

        ``url`` is published verbatim to the resolved URL topic. An unchanged
        retained URL is not published again.

        Raises:
            RuntimeError: If the entity is not bound to a device.
            TypeError: If ``url`` is not a string.
            Exception: If the message could not be published.
        """
        await self._url_value.set_value(url)

    def discovery_config(self) -> dict[str, object]:
        """Return this entity's ``cmps`` config entry for discovery."""
        config = super().discovery_config()
        config["url_t"] = self.url_topic
        return self._resolve_discovery_config(config)
