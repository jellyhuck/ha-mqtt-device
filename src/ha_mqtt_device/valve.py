"""Valve entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Valve"]

logger = logging.getLogger(__name__)

DEFAULT_PAYLOAD_OPEN = "OPEN"
DEFAULT_PAYLOAD_CLOSE = "CLOSE"
DEFAULT_POSITION_CLOSED = 0
DEFAULT_POSITION_OPEN = 100
DEFAULT_STATE_OPEN = "open"
DEFAULT_STATE_OPENING = "opening"
DEFAULT_STATE_CLOSED = "closed"
DEFAULT_STATE_CLOSING = "closing"
_VALID_STATES = ("open", "opening", "closed", "closing")


@dataclass
class Valve(Entity):
    """An MQTT valve belonging to a device.

    In the normal mode, :meth:`open`, :meth:`close`, and :meth:`stop` publish
    configured command payloads and :meth:`set_state` publishes a state value.
    With ``reports_position=True``, open and close publish the configured
    position endpoints and :meth:`set_position` publishes a numeric position.
    Home Assistant commands are delivered to callbacks as :class:`Event`
    objects; callbacks decide how the physical valve changes.
    """

    component = "valve"

    payload_open: str | None = DEFAULT_PAYLOAD_OPEN
    payload_close: str | None = DEFAULT_PAYLOAD_CLOSE
    payload_stop: str | None = None
    state_open: str = DEFAULT_STATE_OPEN
    state_opening: str = DEFAULT_STATE_OPENING
    state_closed: str = DEFAULT_STATE_CLOSED
    state_closing: str = DEFAULT_STATE_CLOSING
    reports_position: bool = False
    position_closed: int = DEFAULT_POSITION_CLOSED
    position_open: int = DEFAULT_POSITION_OPEN
    optimistic: bool = False
    value_template: str | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.position_closed == self.position_open:
            raise ValueError("position_closed and position_open must differ")
        if self.reports_position:
            if self.payload_open not in (None, DEFAULT_PAYLOAD_OPEN):
                raise ValueError(
                    "payload_open cannot be customized when reports_position is true"
                )
            if self.payload_close not in (None, DEFAULT_PAYLOAD_CLOSE):
                raise ValueError(
                    "payload_close cannot be customized when reports_position is true"
                )
            if self.state_open != DEFAULT_STATE_OPEN:
                raise ValueError(
                    "state_open cannot be customized when reports_position is true"
                )
            if self.state_closed != DEFAULT_STATE_CLOSED:
                raise ValueError(
                    "state_closed cannot be customized when reports_position is true"
                )
        for value, field_name in (
            (self.position_closed, "position_closed"),
            (self.position_open, "position_open"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} must be an integer")
        if not isinstance(self.payload_open, str) and self.payload_open is not None:
            raise ValueError("payload_open must be a string or None")
        if not isinstance(self.payload_close, str) and self.payload_close is not None:
            raise ValueError("payload_close must be a string or None")
        if not isinstance(self.payload_stop, str) and self.payload_stop is not None:
            raise ValueError("payload_stop must be a string or None")
        if self.value_template is not None and not isinstance(self.value_template, str):
            raise ValueError("value_template must be a string or None")

    @property
    def command_topic(self) -> str:
        """Command topic as ``~/<unique_id>/command``."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, state: str) -> None:
        """Publish a valve state to the state topic."""
        device = self._require_device()
        if state not in self._state_values:
            raise ValueError(f"unsupported valve state: {state!r}")
        await device.provider.publish(
            device.info.resolve_topic(self.state_topic), state
        )

    async def set_position(self, position: float) -> None:
        """Publish a numeric position to the command topic.

        Position publishing is available only when ``reports_position`` is
        enabled and accepts values within the configured closed/open range.
        """
        device = self._require_device()
        self._validate_position(position)
        await device.provider.publish(
            device.info.resolve_topic(self.command_topic),
            self._number_payload(position),
        )

    async def open(self) -> None:
        """Publish the open command or open position."""
        if self.reports_position:
            await self.set_position(self.position_open)
        elif self.payload_open is not None:
            await self._publish_command(self.payload_open)
        else:
            raise ValueError("the valve open command is disabled")

    async def close(self) -> None:
        """Publish the close command or closed position."""
        if self.reports_position:
            await self.set_position(self.position_closed)
        elif self.payload_close is not None:
            await self._publish_command(self.payload_close)
        else:
            raise ValueError("the valve close command is disabled")

    async def stop(self) -> None:
        """Publish the optional stop command."""
        if self.payload_stop is None:
            raise ValueError("the valve stop command is not configured")
        await self._publish_command(self.payload_stop)

    async def _publish_command(self, payload: str) -> None:
        device = self._require_device()
        await device.provider.publish(
            device.info.resolve_topic(self.command_topic), payload
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Subscribe once to commands and deliver them to ``callback``."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        event_type, state = self._event_state(payload)
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            topic=message.topic,
            topic_type="command_topic",
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

    def _event_state(self, payload: str) -> tuple[str, str | dict[str, Any] | None]:
        if self.reports_position:
            try:
                data = json.loads(payload)
                if isinstance(data, dict) and ("state" in data or "position" in data):
                    return "position", data
            except json.JSONDecodeError:
                pass
            try:
                value = float(payload)
            except ValueError:
                return "command", None
            if isfinite(value) and self._in_position_range(value):
                return "position", payload
            return "position", None
        if self.payload_open is not None and payload == self.payload_open:
            return "command", "open"
        if self.payload_close is not None and payload == self.payload_close:
            return "command", "closed"
        if self.payload_stop is not None and payload == self.payload_stop:
            return "command", "stop"
        return "command", None

    @property
    def _state_values(self) -> tuple[str, ...]:
        return (
            self.state_open,
            self.state_opening,
            self.state_closed,
            self.state_closing,
        )

    def _in_position_range(self, position: float) -> bool:
        low = min(self.position_closed, self.position_open)
        high = max(self.position_closed, self.position_open)
        return low <= position <= high

    def _validate_position(self, position: float) -> None:
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            raise TypeError("position must be a number")
        if not isfinite(position) or not self._in_position_range(position):
            raise ValueError(
                f"position {position!r} is outside the range "
                f"{self.position_closed}..{self.position_open}"
            )
        if not self.reports_position:
            raise ValueError("position commands require reports_position=True")

    @staticmethod
    def _number_payload(value: float) -> str:
        return str(value)

    def discovery_config(self) -> dict[str, object]:
        """Return this valve's compact MQTT discovery configuration."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.reports_position:
            config["pos"] = True
            if self.position_closed != DEFAULT_POSITION_CLOSED:
                config["pos_clsd"] = self.position_closed
            if self.position_open != DEFAULT_POSITION_OPEN:
                config["pos_open"] = self.position_open
        else:
            if self.payload_open != DEFAULT_PAYLOAD_OPEN:
                config["pl_open"] = self.payload_open
            if self.payload_close != DEFAULT_PAYLOAD_CLOSE:
                config["pl_cls"] = self.payload_close
            if self.state_open != DEFAULT_STATE_OPEN:
                config["stat_open"] = self.state_open
            if self.state_opening != DEFAULT_STATE_OPENING:
                config["stat_opening"] = self.state_opening
            if self.state_closed != DEFAULT_STATE_CLOSED:
                config["stat_clsd"] = self.state_closed
        if self.state_closing != DEFAULT_STATE_CLOSING:
            config["stat_closing"] = self.state_closing
        if self.payload_stop is not None:
            config["pl_stop"] = self.payload_stop
        if self.optimistic:
            config["opt"] = True
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        return config
