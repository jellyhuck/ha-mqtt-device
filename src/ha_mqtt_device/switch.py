"""Switch entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Switch"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``payload_on``.
DEFAULT_PAYLOAD_ON = "ON"

#: Home Assistant MQTT discovery default for ``payload_off``.
DEFAULT_PAYLOAD_OFF = "OFF"

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"


@dataclass
class Switch(Entity):
    """A switch belonging to a device.

    A switch has two MQTT topics. The device publishes its state to the state
    topic (``~/<unique_id>/state``) with :meth:`set_state`, and it receives
    commands from Home Assistant on the command topic
    (``~/<unique_id>/command``). Registering an async callback with
    :meth:`on_event` subscribes to the command topic and delivers every
    command as an :class:`~ha_mqtt_device.event.Event`::

        switch = Switch(unique_id="relay_1", name="Relay")
        device = Device(provider, info, entities=[switch])

        async def on_command(event: Event) -> None:
            await switch.set_state(event.state == "on")

        async with device:
            await switch.on_event(on_command)
            await switch.set_state(True)
            await switch.set_state(False)

    Unlike :meth:`set_state`, commands received from Home Assistant do not
    change the switch's state by themselves — the application decides what to
    do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"outlet"`` or ``"switch"``. Omitted from the discovery config
            when unset.
        payload_on: Payload published when the switch reports ``True`` and
            the default for ``state_on``/``command_on``.
        payload_off: Payload published when the switch reports ``False`` and
            the default for ``state_off``/``command_off``.
        state_on: Payload Home Assistant treats as ``on`` in state updates
            (``sta_on``). Defaults to :attr:`payload_on`.
        state_off: Payload Home Assistant treats as ``off`` in state updates
            (``sta_off``). Defaults to :attr:`payload_off`.
        command_on: Payload Home Assistant sends to turn the switch on
            (``cmd_on``). Defaults to :attr:`payload_on`.
        command_off: Payload Home Assistant sends to turn the switch off
            (``cmd_off``). Defaults to :attr:`payload_off`.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
    """

    component = "switch"

    device_class: str | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    state_on: str | None = None
    state_off: str | None = None
    command_on: str | None = None
    command_off: str | None = None
    optimistic: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the command topic subscription has been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return f"~/{self.unique_id}/command"

    async def set_state(self, state: bool) -> None:
        """Publish the switch's state.

        ``True`` publishes :attr:`payload_on` and ``False`` publishes
        :attr:`payload_off` to the state topic (``~/<unique_id>/state``).
        Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topic do.

        Raises:
            RuntimeError: If the switch is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = self.payload_on if state else self.payload_off
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``). Every command message is awaited as
        an :class:`~ha_mqtt_device.event.Event` with ``event_type``
        ``"command"``, ``topic_type`` ``"command_topic"``, and ``state``
        ``"on"`` or ``"off"`` derived from the payload via
        :attr:`command_on`/:attr:`command_off` (falling back to
        :attr:`payload_on`/:attr:`payload_off`). An unknown payload is still
        delivered with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the switch is not bound to a device.
            Exception: If the subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            topic = device.info.resolve_topic(self.command_topic)
            await device.provider.subscribe(topic, self._dispatch)
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        """Turn an MQTT message into an :class:`Event` and await the callbacks."""
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=_EVENT_TYPE_COMMAND,
            topic=message.topic,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=payload,
            state=self._command_state(payload),
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

    def _command_state(self, payload: str) -> str | None:
        """Map a command payload to ``"on"``, ``"off"``, or ``None``."""
        command_on = self.command_on if self.command_on is not None else self.payload_on
        command_off = (
            self.command_off if self.command_off is not None else self.payload_off
        )
        if payload == command_on:
            return "on"
        if payload == command_off:
            return "off"
        return None

    def discovery_config(self) -> dict[str, object]:
        """Return this switch's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["cmd_t"] = self.command_topic
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        if self.state_on is not None and self.state_on != self.payload_on:
            config["sta_on"] = self.state_on
        if self.state_off is not None and self.state_off != self.payload_off:
            config["sta_off"] = self.state_off
        if self.command_on is not None and self.command_on != self.payload_on:
            config["cmd_on"] = self.command_on
        if self.command_off is not None and self.command_off != self.payload_off:
            config["cmd_off"] = self.command_off
        if self.optimistic:
            config["opt"] = True
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return config
