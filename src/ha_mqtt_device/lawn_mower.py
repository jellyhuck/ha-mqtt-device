"""Lawn mower entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["LawnMower"]

logger = logging.getLogger(__name__)

# Home Assistant MQTT discovery defaults for command payloads
DEFAULT_START_MOWING_PAYLOAD = '{"activity": "start_mowing"}'
DEFAULT_PAUSE_PAYLOAD = '{"activity": "pause"}'
DEFAULT_DOCK_PAYLOAD = '{"activity": "dock"}'

# Home Assistant MQTT discovery defaults for state values
DEFAULT_MOWING_STATE = "mowing"
DEFAULT_PAUSED_STATE = "paused"
DEFAULT_DOCKED_STATE = "docked"
DEFAULT_ERROR_STATE = "error"

# Event type for command events
_EVENT_TYPE_COMMAND = "command"

# Discovery config field names for command topics
_TOPIC_TYPE_START_MOWING_COMMAND = "start_mowing_command_topic"
_TOPIC_TYPE_PAUSE_COMMAND = "pause_command_topic"
_TOPIC_TYPE_DOCK_COMMAND = "dock_command_topic"

# Valid activities for the lawn mower
VALID_ACTIVITIES = ("mowing", "paused", "docked", "error")


@dataclass
class LawnMower(Entity):
    """A lawn mower belonging to a device.

    A lawn mower has one state topic (``~/<unique_id>/state``) and one command
    topic (``~/<unique_id>/set``) that receives all commands. Registering an
    async callback with :meth:`on_event` subscribes to the command topic and
    delivers every command as an :class:`~ha_mqtt_device.event.Event`::

        mower = LawnMower(unique_id="mower_1", name="Lawn Mower")
        device = Device(provider, info, entities=[mower])

        async def on_command(event: Event) -> None:
            # event.state is "start_mowing", "pause", or "dock"
            if event.state == "start_mowing":
                await mower.set_state("mowing")
            ...

        async with device:
            await mower.on_event(on_command)
            await mower.set_state("docked")

    Unlike :meth:`set_state`, commands received from Home Assistant do not
    change the lawn mower's state by themselves — the application decides what
    to do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        payload_start_mowing: Payload published when Home Assistant sends a
            start mowing command (``pl_strt``). Defaults to
            ``{"activity": "start_mowing"}``.
        payload_pause: Payload published when Home Assistant sends a pause
            command (``pl_pau``). Defaults to ``{"activity": "pause"}``.
        payload_dock: Payload published when Home Assistant sends a dock
            command (``pl_doc``). Defaults to ``{"activity": "dock"}``.
        state_mowing: State value Home Assistant treats as mowing
            (``sta_mow``). Defaults to ``"mowing"``.
        state_paused: State value Home Assistant treats as paused
            (``sta_pau``). Defaults to those strings. None means the default is used and omitted from discovery.
        state_docked: State value Home Assistant treats as docked
            (``sta_doc``). Defaults to ``"docked"``.
        state_error: State value Home Assistant treats as error
            (``sta_err``). Defaults to ``"error"``.
    """

    component = "lawn_mower"

    # Command payloads (what HA sends to the device)
    payload_start_mowing: str = DEFAULT_START_MOWING_PAYLOAD
    payload_pause: str = DEFAULT_PAUSE_PAYLOAD
    payload_dock: str = DEFAULT_DOCK_PAYLOAD

    # State values (what the device publishes, and what HA expects)
    state_mowing: str | None = None
    state_paused: str | None = None
    state_docked: str | None = None
    state_error: str | None = None

    # Internal: callbacks and subscription state
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def state_topic(self) -> str:
        """State topic as ``~`` shorthand, ``~/<unique_id>/state``."""
        return f"~/{self.unique_id}/state"

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/set``.

        All three command types (start_mowing, pause, dock) use this same topic.
        Home Assistant distinguishes them via different payload templates.
        """
        return f"~/{self.unique_id}/set"

    async def set_state(self, activity: str) -> None:
        """Publish the lawn mower's activity state.

        Publishes a JSON payload ``{"activity": activity}`` to the state topic
        (``~/<unique_id>/state``).

        Args:
            activity: The activity state to publish (e.g., "mowing", "paused",
                "docked", "error"). No validation is performed; any string is
                accepted.

        Raises:
            RuntimeError: If the lawn mower is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = json.dumps({"activity": activity})
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/set``). Every command message is awaited as an
        :class:`~ha_mqtt_device.event.Event` with ``event_type`` ``"command"``,
        ``topic_type`` indicating which command topic (``"start_mowing_command_topic"``,
        ``"pause_command_topic"``, or ``"dock_command_topic"``), and ``state``
        ``"start_mowing"``, ``"pause"``, or ``"dock"`` derived from the JSON
        payload's ``activity`` field. An unknown payload is still delivered
        with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the lawn mower is not bound to a device.
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
        activity = self._command_activity(payload)

        # Determine which command topic this maps to for topic_type
        if activity == "start_mowing":
            topic_type = _TOPIC_TYPE_START_MOWING_COMMAND
        elif activity == "pause":
            topic_type = _TOPIC_TYPE_PAUSE_COMMAND
        elif activity == "dock":
            topic_type = _TOPIC_TYPE_DOCK_COMMAND
        else:
            topic_type = _TOPIC_TYPE_START_MOWING_COMMAND  # fallback

        event = Event(
            timestamp=datetime.now(UTC),
            event_type=_EVENT_TYPE_COMMAND,
            topic=message.topic,
            topic_type=topic_type,
            message=payload,
            state=activity,
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

    def _command_activity(self, payload: str) -> str | None:
        """Extract the activity from a command payload.

        Expects JSON with an "activity" field: {"activity": "start_mowing"}
        Returns "start_mowing", "pause", "dock", or None if not recognized.
        """
        try:
            data = json.loads(payload)
            activity = data.get("activity")
            if activity in ("start_mowing", "pause", "dock"):
                return activity
        except json.JSONDecodeError:
            pass
        return None

    def discovery_config(self) -> dict[str, object]:
        """Return this lawn mower's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()

        # State topic
        config["act_stat_t"] = self.state_topic

        # All command topics point to the same MQTT topic
        command_topic = self.command_topic
        config["st_mow_cmd_t"] = command_topic
        config["pau_cmd_t"] = command_topic
        config["doc_cmd_t"] = command_topic

        # Command payloads (what HA sends)
        if self.payload_start_mowing != DEFAULT_START_MOWING_PAYLOAD:
            config["pl_strt"] = self.payload_start_mowing
        if self.payload_pause != DEFAULT_PAUSE_PAYLOAD:
            config["pl_pau"] = self.payload_pause
        if self.payload_dock != DEFAULT_DOCK_PAYLOAD:
            config["pl_doc"] = self.payload_dock

        # State values (what device publishes / HA expects)
        if self.state_mowing is not None and self.state_mowing != DEFAULT_MOWING_STATE:
            config["sta_mow"] = self.state_mowing
        if self.state_paused is not None and self.state_paused != DEFAULT_PAUSED_STATE:
            config["sta_pau"] = self.state_paused
        if self.state_docked is not None and self.state_docked != DEFAULT_DOCKED_STATE:
            config["sta_doc"] = self.state_docked
        if self.state_error is not None and self.state_error != DEFAULT_ERROR_STATE:
            config["sta_err"] = self.state_error

        return config
