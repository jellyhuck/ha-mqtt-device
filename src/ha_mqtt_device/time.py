"""Time entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import time as time_value

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Time"]

logger = logging.getLogger(__name__)
_TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_TIME_FORMAT = "%H:%M:%S"


@dataclass
class Time(Entity):
    """An MQTT time value serialized as a locale-independent ISO time."""

    component = "time"

    state_enabled: bool = True
    command_template: str | None = None
    value_template: str | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, value: time_value | str) -> None:
        """Normalize and publish a time value to the state topic."""
        device = self._require_device()
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        payload = self._time_payload(value)
        await device.provider.publish(
            device.info.resolve_topic(self.state_topic), payload
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for time commands received from Home Assistant."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        try:
            state = self._canonical_time(payload)
        except ValueError:
            state = None
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

    def _time_payload(self, value: time_value | str) -> str:
        if isinstance(value, str):
            return self._canonical_time(value)
        if isinstance(value, time_value):
            if value.microsecond:
                raise ValueError("time values must not contain fractional seconds")
            return value.strftime(_TIME_FORMAT)
        raise TypeError("time value must be datetime.time or an HH:MM[:SS] string")

    @staticmethod
    def _canonical_time(value: str) -> str:
        if not _TIME_PATTERN.fullmatch(value):
            raise ValueError("time value must be an HH:MM[:SS] string")
        parts = value.split(":")
        normalized = f"{int(parts[0]):02d}:{parts[1]}"
        if len(parts) == 3:
            normalized += f":{parts[2]}"
        try:
            parsed = time_value.fromisoformat(normalized)
        except ValueError:
            raise ValueError(f"time value {value!r} is invalid") from None
        return parsed.strftime(_TIME_FORMAT)

    def discovery_config(self) -> dict[str, object]:
        """Return this time entity's abbreviated discovery configuration."""
        config = super().discovery_config()
        if not self.state_enabled:
            config.pop("stat_t")
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        return config
