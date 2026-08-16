"""Alarm control panel entity for Home Assistant MQTT discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["AlarmControlPanel"]

logger = logging.getLogger(__name__)

DEFAULT_PAYLOAD_ARM_AWAY = "ARM_AWAY"
DEFAULT_PAYLOAD_ARM_CUSTOM_BYPASS = "ARM_CUSTOM_BYPASS"
DEFAULT_PAYLOAD_ARM_HOME = "ARM_HOME"
DEFAULT_PAYLOAD_ARM_NIGHT = "ARM_NIGHT"
DEFAULT_PAYLOAD_ARM_VACATION = "ARM_VACATION"
DEFAULT_PAYLOAD_DISARM = "DISARM"
DEFAULT_PAYLOAD_TRIGGER = "TRIGGER"

_ALARM_MODES = {
    "armed_away",
    "armed_custom_bypass",
    "armed_home",
    "armed_night",
    "armed_vacation",
    "disarmed",
    "pending",
    "triggered",
}


@dataclass
class AlarmControlPanel(Entity):
    """An MQTT alarm control panel.

    Home Assistant sends alarm commands to ``command_topic``.  The device can
    report one of the documented alarm states to ``state_topic``.  Command
    callbacks receive the raw payload, so applications can handle alarm codes
    and command templates without the library guessing at their format.
    """

    component = "alarm_control_panel"

    payload_arm_away: str = DEFAULT_PAYLOAD_ARM_AWAY
    payload_arm_custom_bypass: str = DEFAULT_PAYLOAD_ARM_CUSTOM_BYPASS
    payload_arm_home: str = DEFAULT_PAYLOAD_ARM_HOME
    payload_arm_night: str = DEFAULT_PAYLOAD_ARM_NIGHT
    payload_arm_vacation: str = DEFAULT_PAYLOAD_ARM_VACATION
    payload_disarm: str = DEFAULT_PAYLOAD_DISARM
    payload_trigger: str = DEFAULT_PAYLOAD_TRIGGER
    code_arm_required: bool = False
    code_disarm_required: bool = False
    code_trigger_required: bool = False
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
        payloads = (
            self.payload_arm_away,
            self.payload_arm_custom_bypass,
            self.payload_arm_home,
            self.payload_arm_night,
            self.payload_arm_vacation,
            self.payload_disarm,
            self.payload_trigger,
        )
        if any(not payload for payload in payloads):
            raise ValueError("alarm command payloads must be non-empty")

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand."""
        return f"~/{self.unique_id}/command"

    async def set_state(self, state: str) -> None:
        """Publish a documented alarm state."""
        device = self._require_device()
        if not self.state_enabled:
            raise ValueError("state reporting is disabled")
        if state not in _ALARM_MODES:
            raise ValueError(f"unknown alarm state {state!r}")
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, state)

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
        commands = {
            self.payload_arm_away: "armed_away",
            self.payload_arm_custom_bypass: "armed_custom_bypass",
            self.payload_arm_home: "armed_home",
            self.payload_arm_night: "armed_night",
            self.payload_arm_vacation: "armed_vacation",
            self.payload_disarm: "disarmed",
            self.payload_trigger: "triggered",
        }
        return commands.get(payload)

    def discovery_config(self) -> dict[str, object]:
        """Return this panel's device discovery component configuration."""
        config = super().discovery_config()
        config["cmd_t"] = self.command_topic
        if not self.state_enabled:
            config.pop("stat_t")
        if self.state_enabled:
            config["stat_t"] = self.state_topic
        if self.payload_arm_away != DEFAULT_PAYLOAD_ARM_AWAY:
            config["pl_arm_away"] = self.payload_arm_away
        if self.payload_arm_custom_bypass != DEFAULT_PAYLOAD_ARM_CUSTOM_BYPASS:
            config["pl_arm_custom_b"] = self.payload_arm_custom_bypass
        if self.payload_arm_home != DEFAULT_PAYLOAD_ARM_HOME:
            config["pl_arm_home"] = self.payload_arm_home
        if self.payload_arm_night != DEFAULT_PAYLOAD_ARM_NIGHT:
            config["pl_arm_nite"] = self.payload_arm_night
        if self.payload_arm_vacation != DEFAULT_PAYLOAD_ARM_VACATION:
            config["pl_arm_vacation"] = self.payload_arm_vacation
        if self.payload_disarm != DEFAULT_PAYLOAD_DISARM:
            config["pl_disarm"] = self.payload_disarm
        if self.payload_trigger != DEFAULT_PAYLOAD_TRIGGER:
            config["pl_trig"] = self.payload_trigger
        if self.code_arm_required:
            config["cod_arm_req"] = True
        if self.code_disarm_required:
            config["cod_dis_req"] = True
        if self.code_trigger_required:
            config["cod_trig_req"] = True
        if self.command_template is not None:
            config["cmd_tpl"] = self.command_template
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        if self.optimistic is not None:
            config["opt"] = self.optimistic
        return config
