"""Siren entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Siren"]

logger = logging.getLogger(__name__)
DEFAULT_PAYLOAD_ON = "ON"
DEFAULT_PAYLOAD_OFF = "OFF"


@dataclass
class Siren(Entity):
    """An MQTT siren using JSON-compatible command and state payloads.

    Home Assistant uses one command topic for power and optional tone,
    duration, and volume parameters. The library publishes state reports as
    JSON to the state topic and delivers received command payloads through
    :meth:`on_event` without evaluating Home Assistant templates.
    """

    component = "siren"

    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    state_on: str | None = None
    state_off: str | None = None
    state_enabled: bool = True
    optimistic: bool | None = None
    available_tones: list[str] = field(default_factory=list)
    support_duration: bool = True
    support_volume_set: bool = True
    command_template: str | None = None
    command_off_template: str | None = None
    value_template: str | None = None
    state_value_template: str | None = None
    availability_topic: str | None = None
    availability_template: str | None = None
    payload_available: str = "online"
    payload_not_available: str = "offline"

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if any(not isinstance(tone, str) for tone in self.available_tones):
            raise ValueError("available_tones must contain only strings")

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(
        self,
        state: bool,
        *,
        tone: str | None = None,
        duration: int | None = None,
        volume_level: float | None = None,
    ) -> None:
        """Publish a siren state and optional turn-on parameters."""
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        payload: dict[str, Any] = {
            "state": self.payload_on if state else self.payload_off
        }
        self._add_parameters(payload, tone, duration, volume_level)
        await self._publish(
            self._register_publish_topic(self.state_topic, retain=True),
            json.dumps(payload),
        )

    async def set_tone(self, tone: str) -> None:
        """Publish a tone command, validating it against available tones."""
        self._validate_tone(tone)
        await self._publish_command({"tone": tone})

    async def set_duration(self, duration: int) -> None:
        """Publish a duration command in seconds."""
        self._validate_duration(duration)
        if not self.support_duration:
            raise ValueError("duration support is disabled")
        await self._publish_command({"duration": duration})

    async def set_volume(self, volume_level: float) -> None:
        """Publish a volume command; Home Assistant volume is from 0 to 1."""
        self._validate_volume(volume_level)
        if not self.support_volume_set:
            raise ValueError("volume support is disabled")
        await self._publish_command({"volume_level": volume_level})

    async def _publish_command(self, payload: dict[str, Any]) -> None:
        self._require_device()
        await self._publish(
            self._register_publish_topic(self.command_topic, retain=False),
            json.dumps(payload),
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for command payloads received from Home Assistant."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="command",
            topic=message.topic,
            topic_type="command_topic",
            message=payload,
            state=self._parse_payload(payload),
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

    def _parse_payload(self, payload: str) -> str | dict[str, Any] | None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return self._power_state(payload)
        if isinstance(parsed, dict):
            return parsed
        if parsed is None:
            return None
        if isinstance(parsed, str):
            return self._power_state(parsed)
        return None

    def _power_state(self, payload: str) -> str | None:
        state_on = self.state_on or self.payload_on
        state_off = self.state_off or self.payload_off
        if payload == state_on:
            return "on"
        if payload == state_off:
            return "off"
        return None

    def _add_parameters(
        self,
        payload: dict[str, Any],
        tone: str | None,
        duration: int | None,
        volume_level: float | None,
    ) -> None:
        if tone is not None:
            self._validate_tone(tone)
            payload["tone"] = tone
        if duration is not None:
            self._validate_duration(duration)
            if not self.support_duration:
                raise ValueError("duration support is disabled")
            payload["duration"] = duration
        if volume_level is not None:
            self._validate_volume(volume_level)
            if not self.support_volume_set:
                raise ValueError("volume support is disabled")
            payload["volume_level"] = volume_level

    def _validate_tone(self, tone: str) -> None:
        if not self.available_tones:
            raise ValueError("tone support is disabled")
        if tone not in self.available_tones:
            raise ValueError(f"tone {tone!r} is not in available_tones")

    @staticmethod
    def _validate_duration(duration: int) -> None:
        if isinstance(duration, bool) or duration < 0:
            raise ValueError("duration must be a non-negative integer")

    @staticmethod
    def _validate_volume(volume_level: float) -> None:
        if not isinstance(volume_level, (int, float)) or isinstance(volume_level, bool):
            raise TypeError("volume_level must be a number between 0 and 1")
        if not 0 <= volume_level <= 1:
            raise ValueError("volume_level must be between 0 and 1")

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this siren's abbreviated MQTT discovery configuration."""
        config = super().discovery_config()
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.available_tones:
            config["av_tones"] = list(self.available_tones)
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.command_off_template is not None:
            config["cmd_off_tpl"] = self.command_off_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        if self.state_value_template is not None:
            config["stat_val_tpl"] = self.state_value_template
        if self.support_duration is not True:
            config["sup_dur"] = self.support_duration
        if self.support_volume_set is not True:
            config["sup_vol"] = self.support_volume_set
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        effective_state_on = self.state_on or self.payload_on
        effective_state_off = self.state_off or self.payload_off
        if effective_state_on != DEFAULT_PAYLOAD_ON:
            config["stat_on"] = effective_state_on
        if effective_state_off != DEFAULT_PAYLOAD_OFF:
            config["stat_off"] = effective_state_off
        if self.optimistic is not None:
            default_optimistic = not self.state_enabled
            if self.optimistic != default_optimistic:
                config["opt"] = self.optimistic
        if self.availability_topic is not None:
            config["avty_t"] = self.availability_topic
        if self.availability_template is not None:
            config["avty_tpl"] = self.availability_template
        if self.payload_available != "online":
            config["pl_avail"] = self.payload_available
        if self.payload_not_available != "offline":
            config["pl_not_avail"] = self.payload_not_available
        return self._resolve_discovery_config(config)
