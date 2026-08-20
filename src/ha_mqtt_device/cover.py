"""Cover entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.int_value import IntValue
from ha_mqtt_device.values.mapped_value import MappedValue

__all__ = ["Cover"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``payload_open``.
DEFAULT_PAYLOAD_OPEN = "OPEN"

#: Home Assistant MQTT discovery default for ``payload_close``.
DEFAULT_PAYLOAD_CLOSE = "CLOSE"

#: Home Assistant MQTT discovery default for ``payload_stop``.
DEFAULT_PAYLOAD_STOP = "STOP"

#: Home Assistant MQTT discovery default for ``state_open``.
DEFAULT_STATE_OPEN = "open"

#: Home Assistant MQTT discovery default for ``state_opening``.
DEFAULT_STATE_OPENING = "opening"

#: Home Assistant MQTT discovery default for ``state_closed``.
DEFAULT_STATE_CLOSED = "closed"

#: Home Assistant MQTT discovery default for ``state_closing``.
DEFAULT_STATE_CLOSING = "closing"

#: Home Assistant MQTT discovery default for ``state_stopped``.
DEFAULT_STATE_STOPPED = "stopped"

#: Home Assistant MQTT discovery default for ``position_open``.
DEFAULT_POSITION_OPEN = 100

#: Home Assistant MQTT discovery default for ``position_closed``.
DEFAULT_POSITION_CLOSED = 0

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: ``event_type`` of events built from messages on the set-position topic.
_EVENT_TYPE_SET_POSITION = "set_position"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Discovery config field that names the set-position topic.
_TOPIC_TYPE_SET_POSITION = "set_position_topic"


@dataclass
class Cover(Entity):
    """A cover belonging to a device.

    A cover has four MQTT topics. The device publishes the cover's state to
    the state topic (``~/<unique_id>/state``) with :meth:`set_state` and its
    position to the position topic (``~/<unique_id>/position``) with
    :meth:`set_position`. It receives commands from Home Assistant on the
    command topic (``~/<unique_id>/command``) and position commands on the
    set-position topic (``~/<unique_id>/set_position``). Registering an async
    callback with :meth:`on_event` subscribes to both and delivers every
    message as an :class:`~ha_mqtt_device.event.Event`::

        blinds = Cover(unique_id="blinds", name="Blinds")
        device = Device(provider, info, entities=[blinds])

        async def on_command(event: Event) -> None:
            if event.event_type == "command":
                await apply_command(event.state)
            elif event.state is not None:
                await blinds.set_position(int(event.state))

        async with device:
            await blinds.on_event(on_command)
            await blinds.set_state("open")
            await blinds.set_position(100)

    Unlike :meth:`set_state` and :meth:`set_position`, commands received from
    Home Assistant do not change the cover by themselves — the application
    decides what to do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"window"``, ``"garage"``, ``"blind"``, or ``"curtain"``.
            Omitted from the discovery config when unset.
        payload_open: Payload Home Assistant sends to open the cover
            (``pl_open``).
        payload_close: Payload Home Assistant sends to close the cover
            (``pl_cls``).
        payload_stop: Payload Home Assistant sends to stop the cover
            (``pl_stop``).
        state_open: Payload Home Assistant treats as ``open`` in state
            updates (``stat_open``). Defaults to ``"open"``.
        state_opening: Payload Home Assistant treats as ``opening`` in state
            updates (``stat_opening``). Defaults to ``"opening"``.
        state_closed: Payload Home Assistant treats as ``closed`` in state
            updates (``stat_clsd``). Defaults to ``"closed"``.
        state_closing: Payload Home Assistant treats as ``closing`` in state
            updates (``stat_closing``). Defaults to ``"closing"``.
        state_stopped: Payload Home Assistant treats as ``stopped`` in state
            updates (``stat_stopped``). Defaults to ``"stopped"``.
        position_open: Value that represents fully open (``pos_open``).
            Defaults to ``100``.
        position_closed: Value that represents fully closed (``pos_clsd``).
            Defaults to ``0``.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
    """

    component = "cover"

    device_class: str | None = None
    payload_open: str = DEFAULT_PAYLOAD_OPEN
    payload_close: str = DEFAULT_PAYLOAD_CLOSE
    payload_stop: str = DEFAULT_PAYLOAD_STOP
    state_open: str | None = None
    state_opening: str | None = None
    state_closed: str | None = None
    state_closing: str | None = None
    state_stopped: str | None = None
    position_open: int = DEFAULT_POSITION_OPEN
    position_closed: int = DEFAULT_POSITION_CLOSED
    optimistic: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the incoming-topic subscriptions have been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)
    _state_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)
    _position_value: Entity.StateValue[int] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self._state_value = self._make_persistent_state(
            MappedValue(
                {
                    "open": self.state_open or DEFAULT_STATE_OPEN,
                    "opening": self.state_opening or DEFAULT_STATE_OPENING,
                    "closed": self.state_closed or DEFAULT_STATE_CLOSED,
                    "closing": self.state_closing or DEFAULT_STATE_CLOSING,
                    "stopped": self.state_stopped or DEFAULT_STATE_STOPPED,
                }
            ),
            "state",
        )
        self._position_value = self._make_persistent_state(IntValue(), "state/position")

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return Entity.command_topic_for(self.unique_id)

    @property
    def position_topic(self) -> str:
        """Position topic as ``~`` shorthand, ``~/<unique_id>/position``."""
        return Entity.state_topic_for(self.unique_id, "position")

    @property
    def set_position_topic(self) -> str:
        """Set-position topic as ``~`` shorthand, ``~/<unique_id>/set_position``."""
        return Entity.command_topic_for(self.unique_id, "position")

    async def set_state(self, state: str) -> None:
        """Publish the cover's state.

        ``state`` must be one of ``"open"``, ``"opening"``, ``"closed"``,
        ``"closing"``, or ``"stopped"``; the payload published to the state
        topic (``~/<unique_id>/state``) is the matching :attr:`state_open`/
        :attr:`state_opening`/:attr:`state_closed`/:attr:`state_closing`/
        :attr:`state_stopped` value (or the Home Assistant default when the
        corresponding field is unset). Publishing does not trigger callbacks
        registered with :meth:`on_event`; only messages received on the
        command and set-position topics do. Consecutive unchanged states are
        not republished.

        Raises:
            RuntimeError: If the cover is not bound to a device.
            ValueError: If ``state`` is not one of the known state names.
            Exception: If the message could not be published.
        """
        self._state_payload(state)
        await self._state_value.set_value(state)

    async def set_position(self, position: int) -> None:
        """Publish the cover's position.

        ``position`` is converted to a string and published to the position
        topic (``~/<unique_id>/position``), for example ``75`` is published
        as ``"75"``. Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command and
        set-position topics do. Consecutive unchanged positions are not
        republished.

        Raises:
            RuntimeError: If the cover is not bound to a device.
            Exception: If the message could not be published.
        """
        self._validate_position(position)
        await self._position_value.set_value(position)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``) and the set-position topic
        (``~/<unique_id>/set_position``). Every message on the command topic
        is awaited as an :class:`~ha_mqtt_device.event.Event` with
        ``event_type`` ``"command"``, ``topic_type`` ``"command_topic"``, and
        ``state`` ``"open"``, ``"close"``, or ``"stop"`` derived from the
        payload via :attr:`payload_open`/:attr:`payload_close`/
        :attr:`payload_stop`. Every message on the set-position topic is
        awaited with ``event_type`` ``"set_position"``, ``topic_type``
        ``"set_position_topic"``, and ``state`` equal to the payload when it
        parses as a number. An unknown payload is still delivered with
        ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the cover is not bound to a device.
            Exception: If a subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            command_topic = device.info.resolve_topic(self.command_topic)
            await device.provider.subscribe(command_topic, self._dispatch_command)
            set_position_topic = device.info.resolve_topic(self.set_position_topic)
            await device.provider.subscribe(
                set_position_topic, self._dispatch_set_position
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch_command(self, message: Message) -> None:
        """Turn a command topic message into an :class:`Event` and await it."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_COMMAND,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=message,
            payload=payload,
            state=self._command_state(payload),
        )

    async def _dispatch_set_position(self, message: Message) -> None:
        """Turn a set-position topic message into an :class:`Event` and await it."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_SET_POSITION,
            topic_type=_TOPIC_TYPE_SET_POSITION,
            message=message,
            payload=payload,
            state=self._position_state(payload),
        )

    async def _notify(
        self,
        event_type: str,
        topic_type: str,
        message: Message,
        payload: str,
        state: str | None,
    ) -> None:
        """Build the event and await every registered callback."""
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            topic=message.topic,
            topic_type=topic_type,
            message=payload,
            state=state,
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

    def _state_payload(self, state: str) -> str:
        """Resolve a state name to its configured payload.

        Raises:
            ValueError: If ``state`` is not a known cover state name.
        """
        values = {
            "open": self.state_open or DEFAULT_STATE_OPEN,
            "opening": self.state_opening or DEFAULT_STATE_OPENING,
            "closed": self.state_closed or DEFAULT_STATE_CLOSED,
            "closing": self.state_closing or DEFAULT_STATE_CLOSING,
            "stopped": self.state_stopped or DEFAULT_STATE_STOPPED,
        }
        if state not in values:
            raise ValueError(f"state {state!r} must be one of {sorted(values)}")
        return values[state]

    def _command_state(self, payload: str) -> str | None:
        """Map a command payload to ``"open"``, ``"close"``, ``"stop"``, or ``None``."""
        if payload == self.payload_open:
            return "open"
        if payload == self.payload_close:
            return "close"
        if payload == self.payload_stop:
            return "stop"
        return None

    def _position_state(self, payload: str) -> str | None:
        """Map a set-position payload to the payload string or ``None``.

        The payload is returned verbatim when it parses as a number;
        anything else maps to ``None``.
        """
        try:
            position = float(payload)
        except ValueError:
            return None
        if not isfinite(position) or not position.is_integer():
            return None
        if not self._position_in_range(int(position)):
            return None
        return payload

    def _validate_position(self, position: int) -> None:
        if isinstance(position, bool) or not isinstance(position, int):
            raise TypeError("position must be an integer")
        if not self._position_in_range(position):
            raise ValueError("position is outside the configured range")

    def _position_in_range(self, position: int) -> bool:
        return self.position_closed <= position <= self.position_open

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this cover's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        config["pos_t"] = self.position_topic
        config["set_pos_t"] = self.set_position_topic
        if self.payload_open != DEFAULT_PAYLOAD_OPEN:
            config["pl_open"] = self.payload_open
        if self.payload_close != DEFAULT_PAYLOAD_CLOSE:
            config["pl_cls"] = self.payload_close
        if self.payload_stop != DEFAULT_PAYLOAD_STOP:
            config["pl_stop"] = self.payload_stop
        if self.state_open is not None and self.state_open != DEFAULT_STATE_OPEN:
            config["stat_open"] = self.state_open
        if (
            self.state_opening is not None
            and self.state_opening != DEFAULT_STATE_OPENING
        ):
            config["stat_opening"] = self.state_opening
        if self.state_closed is not None and self.state_closed != DEFAULT_STATE_CLOSED:
            config["stat_clsd"] = self.state_closed
        if (
            self.state_closing is not None
            and self.state_closing != DEFAULT_STATE_CLOSING
        ):
            config["stat_closing"] = self.state_closing
        if (
            self.state_stopped is not None
            and self.state_stopped != DEFAULT_STATE_STOPPED
        ):
            config["stat_stopped"] = self.state_stopped
        if self.position_open != DEFAULT_POSITION_OPEN:
            config["pos_open"] = self.position_open
        if self.position_closed != DEFAULT_POSITION_CLOSED:
            config["pos_clsd"] = self.position_closed
        if self.optimistic:
            config["opt"] = True
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return self._resolve_discovery_config(config)
