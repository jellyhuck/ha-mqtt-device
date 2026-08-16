"""Sensor entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

from dataclasses import dataclass

from ha_mqtt_device.entity import Entity

__all__ = ["Sensor"]


@dataclass
class Sensor(Entity):
    """A sensor belonging to a device.

    The sensor reports a numeric or text value to Home Assistant over MQTT; it
    has no command topic (sensors are read-only in Home Assistant). Create it
    with just a unique id and pass it to the device constructor, which binds it
    and publishes its discovery config::

        temperature = Sensor(
            unique_id="temperature",
            name="Temperature",
            device_class="temperature",
            unit_of_measurement="°C",
            state_class="measurement",
        )
        device = Device(provider, info, entities=[temperature])

        async with device:
            await temperature.set_state(21.5)

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"temperature"``, ``"humidity"``, or ``"power"``. Omitted from
            the discovery config when unset.
        unit_of_measurement: Unit of measurement (``unit_of_meas``), for
            example ``"°C"`` or ``"W"``. Omitted when unset.
        state_class: State class (``stat_cla``), for example ``"measurement"``
            or ``"total_increasing"``. Omitted when unset.
        expire_after: Seconds after which Home Assistant marks the sensor as
            unavailable without a state update (``exp_aft``). Omitted when
            unset.
        force_update: Whether Home Assistant should publish an update even if
            the value is unchanged (``frc_upd``). Defaults to ``False``.
        suggested_display_precision: Suggested number of decimals Home
            Assistant shows (``sug_dsp_prc``). Omitted when unset.
    """

    component = "sensor"

    device_class: str | None = None
    unit_of_measurement: str | None = None
    state_class: str | None = None
    expire_after: int | None = None
    force_update: bool = False
    suggested_display_precision: int | None = None

    async def set_state(self, value: str | float) -> None:
        """Publish the sensor's value.

        ``value`` is converted to a string and published to the state topic
        (``~/<unique_id>/state``), for example ``21.5`` is published as
        ``"21.5"``.

        Raises:
            RuntimeError: If the sensor is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = str(value)
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    def discovery_config(self) -> dict[str, object]:
        """Return this sensor's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        if self.unit_of_measurement is not None:
            config["unit_of_meas"] = self.unit_of_measurement
        if self.state_class is not None:
            config["stat_cla"] = self.state_class
        if self.expire_after is not None:
            config["exp_aft"] = self.expire_after
        if self.force_update:
            config["frc_upd"] = True
        if self.suggested_display_precision is not None:
            config["sug_dsp_prc"] = self.suggested_display_precision
        return config
