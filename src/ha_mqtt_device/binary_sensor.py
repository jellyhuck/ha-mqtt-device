"""Binary sensor entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ha_mqtt_device.entity import Entity

__all__ = ["BinarySensor"]

#: Home Assistant MQTT discovery default for ``payload_on``.
DEFAULT_PAYLOAD_ON = "ON"

#: Home Assistant MQTT discovery default for ``payload_off``.
DEFAULT_PAYLOAD_OFF = "OFF"


@dataclass
class BinarySensor(Entity):
    """A binary sensor belonging to a device.

    The sensor reports a boolean state to Home Assistant over MQTT; it has no
    command topic (binary sensors are read-only in Home Assistant). Create it
    with just a unique id and pass it to the device constructor, which binds it
    and publishes its discovery config::

        sensor = BinarySensor(unique_id="is_led_on", name="LED state")
        device = Device(provider, info, entities=[sensor])

        async with device:
            await sensor.set_state(True)
            await sensor.set_state(False)

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"motion"``, ``"light"``, or ``"door"``. Omitted from the
            discovery config when unset.
        payload_on: Payload published when the sensor reports ``True``.
        payload_off: Payload published when the sensor reports ``False``.
    """

    component = "binary_sensor"

    device_class: str | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF

    async def set_state(self, state: bool) -> None:
        """Publish the sensor's state.

        ``True`` publishes :attr:`payload_on` and ``False`` publishes
        :attr:`payload_off` to the state topic (``~/<unique_id>/state``).

        Raises:
            RuntimeError: If the sensor is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = self.payload_on if state else self.payload_off
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    def discovery_config(self) -> dict[str, object]:
        """Return this sensor's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return config
