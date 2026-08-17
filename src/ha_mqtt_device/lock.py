"""Lock entity for Home Assistant MQTT discovery."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Lock"]

logger = logging.getLogger(__name__)

DEFAULT_PAYLOAD_LOCK = "LOCK"
DEFAULT_PAYLOAD_UNLOCK = "UNLOCK"
DEFAULT_STATE_JAMMED = "JAMMED"
DEFAULT_STATE_LOCKED = "LOCKED"
DEFAULT_STATE_LOCKING = "LOCKING"
DEFAULT_STATE_UNLOCKED = "UNLOCKED"
DEFAULT_STATE_UNLOCKING = "UNLOCKING"
DEFAULT_PAYLOAD_RESET = "None"

_DEFAULT_STATES = {
    "jammed": DEFAULT_STATE_JAMMED,
    "locked": DEFAULT_STATE_LOCKED,
    "locking": DEFAULT_STATE_LOCKING,
    "unlocked": DEFAULT_STATE_UNLOCKED,
    "unlocking": DEFAULT_STATE_UNLOCKING,
}


@dataclass
class Lock(Entity):
    """An MQTT lock with lock, unlock, and optional open commands."""

    component = "lock"

    payload_lock: str = DEFAULT_PAYLOAD_LOCK
    payload_unlock: str = DEFAULT_PAYLOAD_UNLOCK
    payload_open: str | None = None
    payload_reset: str | None = None
    state_jammed: str = DEFAULT_STATE_JAMMED
    state_locked: str = DEFAULT_STATE_LOCKED
    state_locking: str = DEFAULT_STATE_LOCKING
    state_unlocked: str = DEFAULT_STATE_UNLOCKED
    state_unlocking: str = DEFAULT_STATE_UNLOCKING
    code_format: str | None = None
    command_template: str | None = None
    value_template: str | None = None
    state_enabled: bool = True
    optimistic: bool | None = None

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.payload_lock or not self.payload_unlock:
            raise ValueError("payload_lock and payload_unlock must be non-empty")
        if self.payload_open == "":
            raise ValueError("payload_open must be non-empty when configured")
        states = (
            self.state_jammed,
            self.state_locked,
            self.state_locking,
            self.state_unlocked,
            self.state_unlocking,
        )
        if any(not state for state in states):
            raise ValueError("lock state payloads must be non-empty")
        if self.code_format is not None:
            try:
                re.compile(self.code_format)
            except re.error as error:
                raise ValueError(f"invalid code_format: {error}") from error

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    async def set_state(self, state: str) -> None:
        """Publish a lock state using its configured state payload."""
        device = self._require_device()
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        if state == "unknown":
            payload = self.payload_reset or DEFAULT_PAYLOAD_RESET
        else:
            states = {
                "jammed": self.state_jammed,
                "locked": self.state_locked,
                "locking": self.state_locking,
                "unlocked": self.state_unlocked,
                "unlocking": self.state_unlocking,
            }
            try:
                payload = states[state]
            except KeyError:
                raise ValueError(f"unknown lock state {state!r}") from None
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for commands received from Home Assistant."""
        device = self._require_device()
        if not self._subscribed:
            topic = device.info.resolve_topic(self.command_topic)
            await device.provider.subscribe(topic, self._dispatch)
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
        if payload == self.payload_lock:
            return "lock"
        if payload == self.payload_unlock:
            return "unlock"
        if self.payload_open is not None and payload == self.payload_open:
            return "open"
        return None

    def _state_payload(self, state: str) -> str | None:
        return {
            "jammed": self.state_jammed,
            "locked": self.state_locked,
            "locking": self.state_locking,
            "unlocked": self.state_unlocked,
            "unlocking": self.state_unlocking,
        }.get(state)

    def discovery_config(self) -> dict[str, object]:
        """Return this lock's device discovery component configuration."""
        config = super().discovery_config()
        config["cmd_t"] = self.command_topic
        if not self.state_enabled:
            config.pop("stat_t")
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        if self.payload_lock != DEFAULT_PAYLOAD_LOCK:
            config["pl_lock"] = self.payload_lock
        if self.payload_unlock != DEFAULT_PAYLOAD_UNLOCK:
            config["pl_unlk"] = self.payload_unlock
        if self.payload_open is not None:
            config["pl_open"] = self.payload_open
        if (
            self.payload_reset is not None
            and self.payload_reset != DEFAULT_PAYLOAD_RESET
        ):
            config["pl_rst"] = self.payload_reset
        state_keys = {
            "jammed": "stat_jam",
            "locked": "stat_locked",
            "locking": "stat_locking",
            "unlocked": "stat_unlocked",
            "unlocking": "stat_unlocking",
        }
        for key, default in _DEFAULT_STATES.items():
            configured = getattr(self, f"state_{key}")
            if configured != default:
                config[state_keys[key]] = configured
        if self.code_format is not None:
            config["cod_fmt"] = self.code_format
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        if self.optimistic is not None:
            config["opt"] = self.optimistic
        return config
