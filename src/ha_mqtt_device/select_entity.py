"""Select entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["SelectEntity"]

logger = logging.getLogger(__name__)


@dataclass
class SelectEntity(Entity):
    """An MQTT select with a fixed list of selectable string options."""

    component = "select"

    options: list[str] = field(default_factory=list)
    state_enabled: bool = True
    optimistic: bool | None = None
    command_template: str | None = None
    value_template: str | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if any(not isinstance(option, str) for option in self.options):
            raise ValueError("options must contain only strings")

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, option: str) -> None:
        """Publish a selected option to the state topic."""
        device = self._require_device()
        self._validate_option(option)
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        await device.provider.publish(
            device.info.resolve_topic(self.state_topic), option
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for options selected by Home Assistant."""
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
            state=payload if payload in self.options else None,
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

    def _validate_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"option {option!r} must be one of {self.options!r}")

    def discovery_config(self) -> dict[str, object]:
        """Return this select's abbreviated MQTT discovery configuration."""
        config = super().discovery_config()
        if not self.state_enabled:
            config.pop("stat_t")
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        config["ops"] = list(self.options)
        if self.optimistic is not None:
            default_optimistic = not self.state_enabled
            if self.optimistic != default_optimistic:
                config["opt"] = self.optimistic
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        return config
