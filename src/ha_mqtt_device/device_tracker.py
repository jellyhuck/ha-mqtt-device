"""Device tracker entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ha_mqtt_device.entity import Entity

__all__ = ["DeviceTracker"]

#: Home Assistant MQTT discovery default for ``payload_home``.
DEFAULT_PAYLOAD_HOME = "home"

#: Home Assistant MQTT discovery default for ``payload_not_home``.
DEFAULT_PAYLOAD_NOT_HOME = "not_home"

#: Home Assistant MQTT discovery default for ``source_type``.
DEFAULT_SOURCE_TYPE = "gps"


@dataclass
class DeviceTracker(Entity):
    """A device tracker belonging to a device.

    The tracker reports its presence to Home Assistant over MQTT; it has no
    command topic (device trackers are read-only in Home Assistant). The
    device publishes whether it is home with :meth:`set_state` —
    :attr:`payload_home` (default ``"home"``) or :attr:`payload_not_home`
    (default ``"not_home"``) to the state topic — or a GPS position report
    with :meth:`set_location`. Create it with just a unique id and pass it to
    the device constructor, which binds it and publishes its discovery
    config::

        tracker = DeviceTracker(
            unique_id="phone",
            name="Phone",
            latitude=32.87336,
            longitude=-117.22743,
        )
        device = Device(provider, info, entities=[tracker])

        async with device:
            await tracker.set_state(True)
            await tracker.set_location(32.87336, -117.22743)

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        payload_home: Payload published when the tracker reports home.
        payload_not_home: Payload published when the tracker reports not home.
        source_type: Source type of the tracker (``source_type``), for example
            ``"gps"``, ``"bluetooth"``, or ``"router"``. Omitted from the
            discovery config when unset or equal to the Home Assistant
            default (``"gps"``).
        latitude: Latitude of the tracker's location (``lat``). Omitted from
            the discovery config when unset.
        longitude: Longitude of the tracker's location (``lon``). Omitted
            from the discovery config when unset.
        gps_accuracy: GPS accuracy in meters (``gps_acc``). Omitted when
            unset.
        battery_level: Battery level in percent (``bat_lvl``). Omitted when
            unset.
        icon: Icon of the entity (``ic``). Omitted when unset.
    """

    component = "device_tracker"

    payload_home: str = DEFAULT_PAYLOAD_HOME
    payload_not_home: str = DEFAULT_PAYLOAD_NOT_HOME
    source_type: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    gps_accuracy: int | None = None
    battery_level: int | None = None
    icon: str | None = None

    async def set_state(self, state: bool) -> None:
        """Publish the tracker's home/not-home state.

        ``True`` publishes :attr:`payload_home` and ``False`` publishes
        :attr:`payload_not_home` to the state topic
        (``~/<unique_id>/state``).

        Raises:
            RuntimeError: If the tracker is not bound to a device.
            Exception: If the message could not be published.
        """
        payload = self.payload_home if state else self.payload_not_home
        await self._publish(
            self._register_publish_topic(self.state_topic, retain=True), payload
        )

    async def set_location(
        self,
        latitude: float,
        longitude: float,
        gps_accuracy: int | None = None,
        battery_level: int | None = None,
        source_type: str | None = None,
    ) -> None:
        """Publish a GPS position report.

        Publishes a JSON payload with ``latitude`` and ``longitude`` to the
        state topic (``~/<unique_id>/state``), plus ``gps_accuracy``,
        ``battery_level``, and ``source_type`` when set. Optional arguments
        left as ``None`` fall back to the matching
        :attr:`gps_accuracy`, :attr:`battery_level`, and :attr:`source_type`
        attributes, so a tracker configured once can report its position with
        just ``await tracker.set_location(lat, lon)``.

        Raises:
            RuntimeError: If the tracker is not bound to a device.
            Exception: If the message could not be published.
        """
        payload: dict[str, object] = {
            "latitude": latitude,
            "longitude": longitude,
        }
        if gps_accuracy is not None:
            payload["gps_accuracy"] = gps_accuracy
        elif self.gps_accuracy is not None:
            payload["gps_accuracy"] = self.gps_accuracy
        if battery_level is not None:
            payload["battery_level"] = battery_level
        elif self.battery_level is not None:
            payload["battery_level"] = self.battery_level
        if source_type is not None:
            payload["source_type"] = source_type
        elif self.source_type is not None:
            payload["source_type"] = self.source_type
        await self._publish(
            self._register_publish_topic(self.state_topic, retain=True),
            json.dumps(payload),
        )

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this tracker's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        if self.payload_home != DEFAULT_PAYLOAD_HOME:
            config["pl_home"] = self.payload_home
        if self.payload_not_home != DEFAULT_PAYLOAD_NOT_HOME:
            config["pl_not_home"] = self.payload_not_home
        if self.source_type is not None and self.source_type != DEFAULT_SOURCE_TYPE:
            config["source_type"] = self.source_type
        if self.latitude is not None:
            config["lat"] = self.latitude
        if self.longitude is not None:
            config["lon"] = self.longitude
        if self.gps_accuracy is not None:
            config["gps_acc"] = self.gps_accuracy
        if self.battery_level is not None:
            config["bat_lvl"] = self.battery_level
        if self.icon is not None:
            config["ic"] = self.icon
        return config
