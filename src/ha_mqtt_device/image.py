"""Image entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ha_mqtt_device.entity import Entity

__all__ = ["Image"]

#: An omitted ``image_encoding`` means that the image payload is raw binary.
DEFAULT_ENCODING: str | None = None

#: Home Assistant MQTT discovery default for ``content_type``.
DEFAULT_CONTENT_TYPE = "image/jpeg"


@dataclass
class Image(Entity):
    """An image belonging to a device.

    The device publishes image data to Home Assistant over MQTT; it has no
    command topic (images are read-only in Home Assistant). Create it with
    just a unique id and pass it to the device constructor, which binds it and
    publishes its discovery config::

        snapshot = Image(unique_id="camera", name="Camera", encoding="b64")
        device = Device(provider, info, entities=[snapshot])

        async with device:
            await snapshot.set_image(base64.b64encode(raw_image_bytes))

    Home Assistant decodes the payload on the image topic according to the
    optional ``image_encoding`` advertised in the discovery config. The
    default is omitted, so the payload is raw image data; set :attr:`encoding`
    to ``"b64"`` when publishing base64-encoded text.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        content_type: MIME type of image data (``cont_type``), for example
            ``"image/jpeg"`` or ``"image/png"``. The default is omitted.
        encoding: Optional image payload encoding (``img_e``). ``None`` is
            omitted and means raw image bytes; ``"b64"`` enables Base64
            decoding. :meth:`set_image` publishes the payload verbatim
            regardless of this setting.
    """

    component = "image"

    content_type: str = DEFAULT_CONTENT_TYPE
    encoding: str | None = DEFAULT_ENCODING

    @property
    def image_topic(self) -> str:
        """Image topic as ``~`` shorthand, ``~/<unique_id>/image``."""
        return f"~/{self.unique_id}/image"

    async def set_image(self, payload: bytes) -> None:
        """Publish an image payload to Home Assistant.

        ``payload`` is published verbatim to the image topic
        (``~/<unique_id>/image``); this entity does not transform it. With
        :attr:`encoding` omitted, Home Assistant expects raw image bytes. Set
        it to ``"b64"`` and pass base64-encoded bytes — for example
        ``base64.b64encode(raw_image_bytes)``.

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
        # Images have no state topic; the single topic is the image topic.
        config["img_t"] = self.image_topic
        if self.encoding is not None:
            config["img_e"] = self.encoding
        if self.content_type != DEFAULT_CONTENT_TYPE:
            config["cont_type"] = self.content_type
        return config
