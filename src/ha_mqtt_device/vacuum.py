"""Vacuum entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.str_value import StrValue

__all__ = ["Vacuum"]

logger = logging.getLogger(__name__)
VALID_STATES = frozenset({"cleaning", "docked", "paused", "idle", "returning", "error"})
VALID_FEATURES = frozenset(
    {
        "start",
        "stop",
        "pause",
        "return_home",
        "status",
        "locate",
        "clean_spot",
        "fan_speed",
        "send_command",
    }
)
DEFAULT_FEATURES = (
    "start",
    "stop",
    "return_home",
    "status",
    "clean_spot",
)
DEFAULT_PAYLOADS = {
    "start": "start",
    "pause": "pause",
    "stop": "stop",
    "return_home": "return_to_base",
    "locate": "locate",
    "clean_spot": "clean_spot",
}


@dataclass
class Vacuum(Entity):
    """An MQTT vacuum with JSON state and documented command topics."""

    component = "vacuum"

    supported_features: Sequence[str] | None = None
    fan_speed_list: Sequence[str] | None = None
    send_command_enabled: bool = False
    clean_segments_enabled: bool = False
    payload_start: str = DEFAULT_PAYLOADS["start"]
    payload_pause: str = DEFAULT_PAYLOADS["pause"]
    payload_stop: str = DEFAULT_PAYLOADS["stop"]
    payload_return_to_base: str = DEFAULT_PAYLOADS["return_home"]
    payload_locate: str = DEFAULT_PAYLOADS["locate"]
    payload_clean_spot: str = DEFAULT_PAYLOADS["clean_spot"]

    _state_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)
    _command_value: Entity.StateValue[str] | None = field(
        init=False, repr=False, compare=False
    )
    _fan_speed_value: Entity.StateValue[str] | None = field(
        init=False, repr=False, compare=False
    )
    _send_command_value: Entity.StateValue[str] | None = field(
        init=False, repr=False, compare=False
    )
    _clean_segments_value: Entity.StateValue[str] | None = field(
        init=False, repr=False, compare=False
    )

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed_topics: set[str] = field(default_factory=set, init=False, repr=False)
    _features: tuple[str, ...] = field(default=DEFAULT_FEATURES, init=False, repr=False)
    _fan_speeds: tuple[str, ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        features = tuple(
            DEFAULT_FEATURES
            if self.supported_features is None
            else self.supported_features
        )
        if not features:
            raise ValueError("supported_features must not be empty")
        if len(set(features)) != len(features):
            raise ValueError("supported_features must not contain duplicates")
        if any(feature not in VALID_FEATURES for feature in features):
            raise ValueError(f"unsupported vacuum feature in {features!r}")
        self._features = features

        if self.fan_speed_list is not None:
            speeds = tuple(self.fan_speed_list)
            if not speeds or any(
                not isinstance(speed, str) or not speed for speed in speeds
            ):
                raise ValueError("fan_speed_list must contain non-empty strings")
            if len(set(speeds)) != len(speeds):
                raise ValueError("fan_speed_list must not contain duplicates")
            self._fan_speeds = speeds
            if "fan_speed" not in self._features:
                raise ValueError("fan_speed_list requires the fan_speed feature")
        if "fan_speed" in self._features and not self._fan_speeds:
            raise ValueError("fan_speed feature requires fan_speed_list")
        if self.send_command_enabled and "send_command" not in self._features:
            raise ValueError("send_command_enabled requires the send_command feature")
        for name in DEFAULT_PAYLOADS:
            value = getattr(
                self, f"payload_{'return_to_base' if name == 'return_home' else name}"
            )
            if not isinstance(value, str) or not value:
                raise ValueError(f"payload for {name} must be a non-empty string")
        self._state_value = self._make_persistent_state(StrValue(), "state")
        self._command_value = (
            self._make_momentary_state(StrValue(), "command")
            if any(feature in self._features for feature in DEFAULT_PAYLOADS)
            else None
        )
        self._fan_speed_value = (
            self._make_momentary_state(StrValue(), "command/fan_speed")
            if "fan_speed" in self._features
            else None
        )
        self._send_command_value = (
            self._make_momentary_state(StrValue(), "command/send")
            if "send_command" in self._features
            else None
        )
        self._clean_segments_value = (
            self._make_momentary_state(StrValue(), "command/clean_segments")
            if self.clean_segments_enabled
            else None
        )

    @property
    def command_topic(self) -> str:
        """Basic command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    @property
    def fan_speed_topic(self) -> str:
        """Fan speed command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id, "fan_speed")

    @property
    def send_command_topic(self) -> str:
        """Custom command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id, "send")

    @property
    def clean_segments_topic(self) -> str:
        """Clean-segments command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id, "clean_segments")

    async def set_state(
        self,
        state: str,
        *,
        fan_speed: str | None = None,
        segments: Mapping[str, str] | None = None,
    ) -> None:
        """Publish a validated vacuum JSON state payload."""
        if state not in VALID_STATES:
            raise ValueError(f"unsupported vacuum state: {state!r}")
        payload: dict[str, object] = {"state": state}
        if fan_speed is not None:
            if not isinstance(fan_speed, str) or not fan_speed:
                raise ValueError("fan_speed must be a non-empty string")
            payload["fan_speed"] = fan_speed
        if segments is not None:
            payload["segments"] = self._validate_segments(segments)
        await self.publish_state(payload)

    async def reset_state(self) -> None:
        """Publish ``null`` to reset Home Assistant's vacuum state."""
        await self._state_value.set_value("null")

    async def publish_state(self, state: Mapping[str, object]) -> None:
        """Publish a validated JSON state mapping."""
        payload = self._validated_state(state)
        await self._state_value.set_value(json.dumps(payload))

    async def start(self) -> None:
        """Start cleaning."""
        await self._publish_basic("start")

    async def pause(self) -> None:
        """Pause cleaning."""
        await self._publish_basic("pause")

    async def stop(self) -> None:
        """Stop cleaning."""
        await self._publish_basic("stop")

    async def return_to_base(self) -> None:
        """Return to the charging base."""
        await self._publish_basic("return_home")

    async def locate(self) -> None:
        """Locate the vacuum."""
        await self._publish_basic("locate")

    async def clean_spot(self) -> None:
        """Start a spot-cleaning cycle."""
        await self._publish_basic("clean_spot")

    async def set_fan_speed(self, speed: str) -> None:
        """Publish a configured fan speed."""
        self._require_feature("fan_speed")
        self._validate_fan_speed(speed)
        assert self._fan_speed_value is not None
        await self._fan_speed_value.set_value(speed)

    async def send_command(
        self, command: str, params: Mapping[str, object] | None = None
    ) -> None:
        """Publish a custom command as plain text or a flattened JSON mapping."""
        self._require_feature("send_command")
        if not isinstance(command, str) or not command:
            raise ValueError("command must be a non-empty string")
        if params is None:
            payload: str = command
        else:
            payload_map: dict[str, object] = {"command": command}
            for key, value in params.items():
                if not isinstance(key, str) or key == "command":
                    raise ValueError(
                        "custom command parameter keys must be strings other than command"
                    )
                payload_map[key] = value
            payload = json.dumps(payload_map)
        assert self._send_command_value is not None
        await self._send_command_value.set_value(payload)

    async def clean_segments(self, segments: Sequence[str]) -> None:
        """Publish the JSON list of segment IDs to clean."""
        if not self.clean_segments_enabled:
            raise ValueError("clean segments command is disabled")
        if not segments or any(
            not isinstance(segment, str) or not segment for segment in segments
        ):
            raise ValueError("segments must contain non-empty strings")
        assert self._clean_segments_value is not None
        await self._clean_segments_value.set_value(json.dumps(list(segments)))

    async def on_event(self, callback: EventCallback) -> None:
        """Subscribe once to each enabled Home Assistant command topic."""
        device = self._require_device()
        topics = self._command_subscriptions()
        if not topics:
            raise ValueError("vacuum has no enabled command features")
        for topic in topics:
            resolved_topic = device.info.resolve_topic(topic)
            if resolved_topic not in self._subscribed_topics:
                await device.provider.subscribe(resolved_topic, self._dispatch)
                self._subscribed_topics.add(resolved_topic)
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        topic_type, state = self._event_mapping(message.topic, payload)
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="command",
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

    async def _publish_basic(self, feature: str) -> None:
        self._require_feature(feature)
        assert self._command_value is not None
        await self._command_value.set_value(self._payload_for(feature))

    def _require_feature(self, feature: str) -> None:
        if feature not in self._features:
            raise ValueError(f"vacuum feature is disabled: {feature}")

    def _payload_for(self, feature: str) -> str:
        field = "return_to_base" if feature == "return_home" else feature
        return getattr(self, f"payload_{field}")

    def _command_subscriptions(self) -> dict[str, str]:
        topics: dict[str, str] = {}
        if any(feature in self._features for feature in DEFAULT_PAYLOADS):
            topics[self.command_topic] = "command_topic"
        if "fan_speed" in self._features:
            topics[self.fan_speed_topic] = "set_fan_speed_topic"
        if self.send_command_enabled:
            topics[self.send_command_topic] = "send_command_topic"
        if self.clean_segments_enabled:
            topics[self.clean_segments_topic] = "clean_segments_command_topic"
        return topics

    def _event_mapping(
        self, topic: str, payload: str
    ) -> tuple[str, str | dict[str, Any] | None]:
        device = self._require_device()
        subscriptions = {
            device.info.resolve_topic(subscribed): field
            for subscribed, field in self._command_subscriptions().items()
        }
        topic_type = subscriptions.get(topic, "command_topic")
        if topic == device.info.resolve_topic(self.command_topic):
            for feature in DEFAULT_PAYLOADS:
                if feature in self._features and payload == self._payload_for(feature):
                    return topic_type, feature
            return topic_type, None
        if topic == device.info.resolve_topic(self.fan_speed_topic):
            return topic_type, payload if payload in self._fan_speeds else None
        if topic == device.info.resolve_topic(self.send_command_topic):
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                return topic_type, payload
            return topic_type, decoded if isinstance(decoded, dict) else None
        if topic == device.info.resolve_topic(self.clean_segments_topic):
            try:
                decoded = json.loads(payload)
            except json.JSONDecodeError:
                return topic_type, None
            if isinstance(decoded, list) and all(
                isinstance(item, str) for item in decoded
            ):
                return topic_type, {"segments": decoded}
        return topic_type, None

    @classmethod
    def _validated_state(cls, state: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(state, Mapping):
            raise TypeError("vacuum state must be a mapping")
        payload = dict(state)
        if set(payload) - {"state", "fan_speed", "segments"}:
            raise ValueError(
                "vacuum state supports only state, fan_speed, and segments"
            )
        if payload.get("state") not in VALID_STATES:
            raise ValueError("vacuum state must contain a supported state")
        if (
            "fan_speed" in payload
            and payload["fan_speed"] is not None
            and (not isinstance(payload["fan_speed"], str) or not payload["fan_speed"])
        ):
            raise ValueError("fan_speed must be a non-empty string")
        if "segments" in payload and payload["segments"] is not None:
            payload["segments"] = cls._validate_segments(payload["segments"])
        return payload

    @staticmethod
    def _validate_segments(segments: object) -> dict[str, str]:
        if not isinstance(segments, Mapping):
            raise TypeError("segments must be a mapping")
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in segments.items()
        ):
            raise TypeError("segment IDs and names must be strings")
        return dict(segments)

    def _validate_fan_speed(self, speed: str) -> None:
        if speed not in self._fan_speeds:
            raise ValueError(f"unsupported fan speed: {speed!r}")

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this vacuum's abbreviated discovery configuration."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        if any(feature in self._features for feature in DEFAULT_PAYLOADS):
            config["cmd_t"] = self.command_topic
        if self.send_command_enabled:
            config["send_cmd_t"] = self.send_command_topic
        if self._fan_speeds:
            config["set_fan_spd_t"] = self.fan_speed_topic
            config["fanspd_lst"] = list(self._fan_speeds)
        if self.clean_segments_enabled:
            config["clean_segments_command_topic"] = self.clean_segments_topic
        if (
            self.supported_features is not None
            and tuple(self.supported_features) != DEFAULT_FEATURES
        ):
            config["sup_feat"] = list(self._features)
        for feature, key, default in (
            ("start", "pl_strt", DEFAULT_PAYLOADS["start"]),
            ("pause", "pl_paus", DEFAULT_PAYLOADS["pause"]),
            ("stop", "pl_stop", DEFAULT_PAYLOADS["stop"]),
            ("return_home", "pl_ret", DEFAULT_PAYLOADS["return_home"]),
            ("locate", "pl_loc", DEFAULT_PAYLOADS["locate"]),
            ("clean_spot", "pl_cln_sp", DEFAULT_PAYLOADS["clean_spot"]),
        ):
            if (
                feature in self._features
                and getattr(
                    self,
                    f"payload_{'return_to_base' if feature == 'return_home' else feature}",
                )
                != default
            ):
                config[key] = getattr(
                    self,
                    f"payload_{'return_to_base' if feature == 'return_home' else feature}",
                )
        return self._resolve_discovery_config(config)
