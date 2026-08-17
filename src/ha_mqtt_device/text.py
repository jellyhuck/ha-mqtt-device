"""Text entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Text"]

logger = logging.getLogger(__name__)
DEFAULT_MIN_LENGTH = 0
DEFAULT_MAX_LENGTH = 255
DEFAULT_MODE = "text"
VALID_MODES = frozenset({"text", "password"})


@dataclass
class Text(Entity):
    """An MQTT text value with optional length and regular-expression limits."""

    component = "text"

    min_length: int = DEFAULT_MIN_LENGTH
    max_length: int = DEFAULT_MAX_LENGTH
    mode: str = DEFAULT_MODE
    pattern: str | None = None
    state_enabled: bool = True
    command_template: str | None = None
    value_template: str | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)
    _compiled_pattern: re.Pattern[str] | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.min_length, int) or isinstance(self.min_length, bool):
            raise TypeError("min_length must be an integer")
        if not isinstance(self.max_length, int) or isinstance(self.max_length, bool):
            raise TypeError("max_length must be an integer")
        if not 0 <= self.min_length <= DEFAULT_MAX_LENGTH:
            raise ValueError("min_length must be between 0 and 255")
        if not 0 <= self.max_length <= DEFAULT_MAX_LENGTH:
            raise ValueError("max_length must be between 0 and 255")
        if self.min_length > self.max_length:
            raise ValueError("min_length must not exceed max_length")
        if self.mode not in VALID_MODES:
            raise ValueError("mode must be either 'text' or 'password'")
        if self.pattern is not None:
            try:
                self._compiled_pattern = re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid text pattern: {exc}") from exc

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, value: str) -> None:
        """Validate and publish a text state to the state topic."""
        device = self._require_device()
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        self._validate_value(value)
        await device.provider.publish(
            device.info.resolve_topic(self.state_topic), value
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for text commands received from Home Assistant."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        state: str | None
        try:
            self._validate_value(payload)
        except TypeError, ValueError:
            state = None
        else:
            state = payload
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="command",
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

    def _validate_value(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("text value must be a string")
        length = len(value)
        if not self.min_length <= length <= self.max_length:
            raise ValueError(
                f"text value length must be between {self.min_length} and "
                f"{self.max_length}"
            )
        if (
            self._compiled_pattern is not None
            and self._compiled_pattern.fullmatch(value) is None
        ):
            raise ValueError("text value does not match pattern")

    def discovery_config(self) -> dict[str, object]:
        """Return this text entity's abbreviated discovery configuration."""
        config = super().discovery_config()
        if not self.state_enabled:
            config.pop("stat_t")
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.max_length != DEFAULT_MAX_LENGTH:
            config["max"] = self.max_length
        if self.min_length != DEFAULT_MIN_LENGTH:
            config["min"] = self.min_length
        if self.mode != DEFAULT_MODE:
            config["mode"] = self.mode
        if self.pattern is not None:
            config["ptrn"] = self.pattern
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        return config
