"""Camera entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass, field

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.values.bytes_value import BytesValue

__all__ = ["Camera"]

#: An omitted ``image_encoding`` means that the image payload is raw binary.
DEFAULT_ENCODING: str | None = None

#: Retained for compatibility; Camera discovery has no content-type field.
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
    optional ``image_encoding`` advertised in the discovery config. The
    default is omitted, so the payload is raw image data; set :attr:`encoding`
    to ``"b64"`` when publishing base64-encoded text.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        content_type: Retained for backwards compatibility, but not emitted;
            Camera MQTT discovery has no documented content-type field.
        encoding: Optional image payload encoding (``img_e``). ``None`` is
            omitted and means raw image bytes; ``"b64"`` enables Base64
            decoding. :meth:`set_image` publishes the payload verbatim
            regardless of this setting.
    """

    component = "camera"

    # Kept as a source-compatible argument, but Camera discovery does not
    # define a content-type field.
    content_type: str = DEFAULT_CONTENT_TYPE
    encoding: str | None = DEFAULT_ENCODING
    _image_value: Entity.StateValue[bytes] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._image_value = self._make_momentary_state(BytesValue(), "image")

    @property
    def image_topic(self) -> str:
        """Image topic as ``~`` shorthand, ``~/<unique_id>/image``."""
        return f"~/{self.unique_id}/image"

    async def set_image(self, payload: bytes) -> None:
        """Publish an image frame to Home Assistant.

        ``payload`` is published verbatim to the image topic
        (``~/<unique_id>/image``); this entity does not transform it. With
        :attr:`encoding` omitted, Home Assistant expects raw image bytes. Set
        it to ``"b64"`` and pass base64-encoded bytes — for example
        ``base64.b64encode(raw_image_bytes)``. Frames are transient, so every
        call publishes even when the bytes are unchanged.

        Raises:
            RuntimeError: If the entity is not bound to a device.
            Exception: If the message could not be published.
        """
        await self._image_value.set_value(payload)

    def discovery_config(self) -> dict[str, object]:
        """Return this entity's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        # Cameras have no state topic; the single topic is the image topic
        # (the Home Assistant camera discovery key is ``topic``, abbreviated
        # as ``t`` in the new-format payload).
        config["t"] = self.image_topic
        if self.encoding is not None:
            config["img_e"] = self.encoding
        # Camera's MQTT schema does not define content_type; do not emit it.
        return self._resolve_discovery_config(config)
