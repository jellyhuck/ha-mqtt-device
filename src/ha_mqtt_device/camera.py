"""Camera entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ha_mqtt_device.entity import Entity

__all__ = ["Camera"]

#: Home Assistant MQTT discovery default for ``image_encoding`` (``enc``).
DEFAULT_ENCODING = "b64"

#: Home Assistant MQTT discovery default for ``content_type`` (``cont_t``).
DEFAULT_CONTENT_TYPE = "image/jpeg"


@dataclass
class Camera(Entity):
    """A camera belonging to a device.

    The device publishes image frames to Home Assistant over MQTT; cameras are
    read-only in Home Assistant — Home Assistant subscribes to the image topic
    and displays every frame, so there is no command topic. Create it with
    just a unique id and pass it to the device constructor, which binds it and
    publishes its discovery config::

        camera = Camera(unique_id="camera", name="Camera")
        device = Device(provider, info, entities=[camera])

        async with device:
            await camera.set_image(base64.b64encode(raw_image_bytes))

    Home Assistant decodes the payload on the image topic according to the
    ``image_encoding`` advertised in the discovery config. The default is
    ``"b64"`` (base64), so the payload must be base64-encoded text by default;
    set :attr:`encoding` to any other value to publish raw image bytes
    instead.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        content_type: MIME type of the image payload (``cont_t``), for
            example ``"image/jpeg"`` or ``"image/png"``. Omitted from the
            discovery config when it equals the default ``"image/jpeg"``.
        encoding: How Home Assistant should decode the payload (``enc``).
            Defaults to ``"b64"``, meaning the payload is base64-encoded
            text. Any other value tells Home Assistant to treat the payload
            as raw image bytes. Omitted from the discovery config when it
            equals the default. :meth:`set_image` publishes the payload
            verbatim regardless of this setting.
    """

    component = "camera"

    content_type: str = DEFAULT_CONTENT_TYPE
    encoding: str = DEFAULT_ENCODING

    @property
    def image_topic(self) -> str:
        """Image topic as ``~`` shorthand, ``~/<unique_id>/image``."""
        return f"~/{self.unique_id}/image"

    async def set_image(self, payload: bytes) -> None:
        """Publish an image frame to Home Assistant.

        ``payload`` is published verbatim to the image topic
        (``~/<unique_id>/image``); this entity does not transform it. With the
        default :attr:`encoding` (``"b64"``) Home Assistant base64-decodes the
        payload, so pass base64-encoded bytes — for example
        ``base64.b64encode(raw_image_bytes)``. Set :attr:`encoding` to a
        non-``"b64"`` value and pass the raw image bytes to publish binary
        image data.

        Raises:
            RuntimeError: If the entity is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        topic = device.info.resolve_topic(self.image_topic)
        await device.provider.publish(topic, payload)

    def discovery_config(self) -> dict[str, object]:
        """Return this entity's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        # Cameras have no state topic; the single topic is the image topic
        # (the Home Assistant camera discovery key is ``topic``, abbreviated
        # as ``t`` in the new-format payload).
        config.pop("p")
        config["t"] = self.image_topic
        if self.encoding != DEFAULT_ENCODING:
            config["enc"] = self.encoding
        if self.content_type != DEFAULT_CONTENT_TYPE:
            config["cont_t"] = self.content_type
        return config
