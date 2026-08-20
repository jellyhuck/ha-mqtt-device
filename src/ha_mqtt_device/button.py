"""Button entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Button"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``payload_press``.
DEFAULT_PAYLOAD_PRESS = "PRESS"

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_PRESS = "press"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"


@dataclass
class Button(Entity):
    """A button belonging to a device.

    A button is triggered by Home Assistant rather than reported by the
    device: Home Assistant shows the button and, when it is pressed, publishes
    :attr:`payload_press` to the button's resolved command topic. The button
    has no state topic — the device never publishes anything for it.
    Registering an async callback with :meth:`on_event` subscribes to the
    resolved command topic and delivers every press
    as an :class:`~ha_mqtt_device.event.Event`::

        button = Button(unique_id="restart", name="Restart")
        device = Device(provider, info, entities=[button])

        async def on_press(event: Event) -> None:
            await reboot_device()

        async with device:
            await button.on_event(on_press)

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"restart"``, ``"update"``, ``"identify"``, or ``"locate"``.
            Omitted from the discovery config when unset.
        payload_press: Payload Home Assistant publishes to the command topic
            when the button is pressed (``pl_prs``).
    """

    component = "button"

    device_class: str | None = None
    payload_press: str = DEFAULT_PAYLOAD_PRESS

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def command_topic(self) -> str:
        """Return the resolved command topic for this bound entity."""
        return self.command_topic_for()

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every press received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the resolved
        command topic. Every press is awaited as an
        :class:`~ha_mqtt_device.event.Event` with ``event_type`` ``"press"``,
        ``topic_type`` ``"command_topic"``, and ``state`` ``"press"`` when the
        payload equals :attr:`payload_press`. An unknown payload is still
        delivered with ``state`` ``None``.

        The broker connection must be running for presses to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the button is not bound to a device.
            Exception: If the subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(self.command_topic, self._dispatch)
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        """Turn an MQTT message into an :class:`Event` and await the callbacks."""
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=_EVENT_TYPE_PRESS,
            topic=message.topic,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=payload,
            state=self._press_state(payload),
        )
        for callback in tuple(self._event_callbacks):
            try:
                await callback(event)
            except Exception:
                logger.exception(
                    "event callback failed for %s %r on topic %r",
                    type(self).__name__,
                    self.unique_id,
                    message.topic,
                )

    def _press_state(self, payload: str) -> str | None:
        """Map a press payload to ``"press"`` or ``None``."""
        if payload == self.payload_press:
            return "press"
        return None

    def discovery_config(self) -> dict[str, object]:
        """Return this button's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        # Buttons have no state topic; the single topic is the command topic.
        config["cmd_t"] = self.command_topic
        if self.payload_press != DEFAULT_PAYLOAD_PRESS:
            config["pl_prs"] = self.payload_press
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return self._resolve_discovery_config(config)
