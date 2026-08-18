"""Light entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Light"]

logger = logging.getLogger(__name__)
DEFAULT_PAYLOAD_ON = "ON"
DEFAULT_PAYLOAD_OFF = "OFF"


@dataclass
class Light(Entity):
    """An MQTT light with optional brightness and color controls.

    State topics are grouped below ``~/state`` and command topics below
    ``~/command``. Feature command messages are delivered to ``on_event``;
    applications acknowledge them by publishing the corresponding state.
    """

    component = "light"

    device_class: str | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    brightness_enabled: bool = False
    color_temp_enabled: bool = False
    rgb_enabled: bool = False
    hs_enabled: bool = False
    xy_enabled: bool = False
    effect_enabled: bool = False
    white_enabled: bool = False
    effect_list: list[str] = field(default_factory=list)
    color_temp_kelvin: bool = False
    brightness_scale: int = 255
    white_scale: int = 255
    optimistic: bool = False

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    @property
    def power_state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id, "power")

    @property
    def command_topic(self) -> str:
        return Entity.command_topic_for(self.unique_id, "power")

    def _topic(self, name: str, command: bool = False) -> str:
        return (Entity.command_topic_for if command else Entity.state_topic_for)(
            self.unique_id, name
        )

    @property
    def brightness_state_topic(self) -> str:
        return self._topic("brightness")

    @property
    def brightness_command_topic(self) -> str:
        return self._topic("brightness", True)

    @property
    def color_temp_state_topic(self) -> str:
        return self._topic("color_temp")

    @property
    def color_temp_command_topic(self) -> str:
        return self._topic("color_temp", True)

    @property
    def rgb_state_topic(self) -> str:
        return self._topic("rgb")

    @property
    def rgb_command_topic(self) -> str:
        return self._topic("rgb", True)

    @property
    def hs_state_topic(self) -> str:
        return self._topic("hs")

    @property
    def hs_command_topic(self) -> str:
        return self._topic("hs", True)

    @property
    def xy_state_topic(self) -> str:
        return self._topic("xy")

    @property
    def xy_command_topic(self) -> str:
        return self._topic("xy", True)

    @property
    def effect_state_topic(self) -> str:
        return self._topic("effect")

    @property
    def effect_command_topic(self) -> str:
        return self._topic("effect", True)

    @property
    def white_state_topic(self) -> str:
        return self._topic("white")

    @property
    def white_command_topic(self) -> str:
        return self._topic("white", True)

    async def set_state(self, state: bool) -> None:
        await self._publish(
            self._register_publish_topic(self.power_state_topic, retain=True),
            self.payload_on if state else self.payload_off,
        )

    async def set_brightness(self, brightness: int) -> None:
        self._require_enabled(self.brightness_enabled, "brightness")
        if not 0 <= brightness <= self.brightness_scale:
            raise ValueError(
                f"brightness must be between 0 and {self.brightness_scale}"
            )
        await self._publish(
            self._register_publish_topic(self.brightness_state_topic, retain=True),
            str(brightness),
        )

    async def set_color_temp(self, value: int) -> None:
        self._require_enabled(self.color_temp_enabled, "color_temp")
        self._validate_integer(value, "color_temp")
        await self._publish(
            self._register_publish_topic(self.color_temp_state_topic, retain=True),
            str(value),
        )

    async def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        self._require_enabled(self.rgb_enabled, "rgb")
        if len(rgb) != 3 or any(not 0 <= value <= 255 for value in rgb):
            raise ValueError("rgb must contain three values between 0 and 255")
        await self._publish(
            self._register_publish_topic(self.rgb_state_topic, retain=True),
            ",".join(map(str, rgb)),
        )

    async def set_hs(self, hs: tuple[float, float]) -> None:
        self._require_enabled(self.hs_enabled, "hs")
        self._validate_hs(hs)
        await self._publish(
            self._register_publish_topic(self.hs_state_topic, retain=True),
            f"{hs[0]},{hs[1]}",
        )

    async def set_xy(self, xy: tuple[float, float]) -> None:
        self._require_enabled(self.xy_enabled, "xy")
        self._validate_xy(xy)
        await self._publish(
            self._register_publish_topic(self.xy_state_topic, retain=True),
            f"{xy[0]},{xy[1]}",
        )

    async def set_effect(self, effect: str) -> None:
        self._require_enabled(self.effect_enabled, "effect")
        if self.effect_list and effect not in self.effect_list:
            raise ValueError(f"effect {effect!r} is not in effect_list")
        await self._publish(
            self._register_publish_topic(self.effect_state_topic, retain=True), effect
        )

    async def set_white(self, value: int) -> None:
        self._require_enabled(self.white_enabled, "white")
        if not 0 <= value <= self.white_scale:
            raise ValueError(f"white must be between 0 and {self.white_scale}")
        await self._publish(
            self._register_publish_topic(self.white_state_topic, retain=True),
            str(value),
        )

    async def on_event(self, callback: EventCallback) -> None:
        device = self._require_device()
        if not self._subscribed:
            topics = [(self.command_topic, "command", "command_topic")]
            features = [
                ("brightness", self.brightness_enabled),
                ("color_temp", self.color_temp_enabled),
                ("rgb", self.rgb_enabled),
                ("hs", self.hs_enabled),
                ("xy", self.xy_enabled),
                ("effect", self.effect_enabled),
                ("white", self.white_enabled),
            ]
            for name, enabled in features:
                if enabled:
                    topics.append(
                        (self._topic(name, True), name, f"{name}_command_topic")
                    )
            for topic, event_type, topic_type in topics:

                async def dispatch(
                    message: Message, et: str = event_type, tt: str = topic_type
                ) -> None:
                    await self._dispatch(message, et, tt)

                await device.provider.subscribe(
                    device.info.resolve_topic(topic), dispatch
                )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(
        self, message: Message, event_type: str, topic_type: str
    ) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        event = Event(
            datetime.now(UTC),
            event_type,
            message.topic,
            topic_type,
            payload,
            self._parse_state(event_type, payload),
        )
        for callback in tuple(self._event_callbacks):
            try:
                await callback(event)
            except Exception:
                logger.exception(
                    "event callback failed for %s %r",
                    type(self).__name__,
                    self.unique_id,
                )

    def _parse_state(
        self, event_type: str, payload: str
    ) -> str | dict[str, object] | None:
        if event_type == "command":
            return (
                "on"
                if payload == self.payload_on
                else "off"
                if payload == self.payload_off
                else None
            )
        if event_type in {"brightness", "color_temp", "white"}:
            try:
                value = float(payload)
            except ValueError:
                return None
            if not isfinite(value) or not value.is_integer():
                return None
            integer = int(value)
            if event_type == "brightness" and not 0 <= integer <= self.brightness_scale:
                return None
            if event_type == "white" and not 0 <= integer <= self.white_scale:
                return None
            if event_type == "color_temp" and integer < 0:
                return None
            return payload
        if event_type in {"rgb", "hs", "xy"}:
            try:
                values = [float(value) for value in payload.split(",")]
                names = {
                    "rgb": ("red", "green", "blue"),
                    "hs": ("hue", "sat"),
                    "xy": ("x", "y"),
                }[event_type]
                if len(values) != len(names) or not all(
                    isfinite(value) for value in values
                ):
                    return None
                if event_type == "rgb" and any(
                    not value.is_integer() or not 0 <= value <= 255 for value in values
                ):
                    return None
                if event_type == "hs" and not (
                    0 <= values[0] <= 360 and 0 <= values[1] <= 100
                ):
                    return None
                if event_type == "xy" and any(not 0 <= value <= 1 for value in values):
                    return None
                return {
                    name: (int(value) if event_type == "rgb" else value)
                    for name, value in zip(names, values)
                }
            except (ValueError, KeyError):
                return None
        if event_type == "effect":
            return (
                payload if not self.effect_list or payload in self.effect_list else None
            )
        return None

    @staticmethod
    def _validate_integer(value: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")

    @staticmethod
    def _validate_hs(hs: tuple[float, float]) -> None:
        if len(hs) != 2 or not all(isfinite(value) for value in hs):
            raise ValueError("hs must contain two finite values")
        if not 0 <= hs[0] <= 360 or not 0 <= hs[1] <= 100:
            raise ValueError("hs must be within hue 0..360 and saturation 0..100")

    @staticmethod
    def _validate_xy(xy: tuple[float, float]) -> None:
        if len(xy) != 2 or not all(isfinite(value) for value in xy):
            raise ValueError("xy must contain two finite values")
        if any(not 0 <= value <= 1 for value in xy):
            raise ValueError("xy values must be between 0 and 1")

    def _require_enabled(self, enabled: bool, feature: str) -> None:
        if not enabled:
            raise ValueError(
                f"{type(self).__name__} {self.unique_id!r} has {feature} control disabled"
            )

    def discovery_config(self) -> dict[str, object]:
        config = super().discovery_config()
        config.update({"stat_t": self.power_state_topic, "cmd_t": self.command_topic})
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        feature_keys = {
            "brightness": (
                "bri_stat_t",
                "bri_cmd_t",
                self.brightness_enabled,
                self.brightness_state_topic,
                self.brightness_command_topic,
            ),
            "color_temp": (
                "clr_temp_stat_t",
                "clr_temp_cmd_t",
                self.color_temp_enabled,
                self.color_temp_state_topic,
                self.color_temp_command_topic,
            ),
            "rgb": (
                "rgb_stat_t",
                "rgb_cmd_t",
                self.rgb_enabled,
                self.rgb_state_topic,
                self.rgb_command_topic,
            ),
            "hs": (
                "hs_stat_t",
                "hs_cmd_t",
                self.hs_enabled,
                self.hs_state_topic,
                self.hs_command_topic,
            ),
            "xy": (
                "xy_stat_t",
                "xy_cmd_t",
                self.xy_enabled,
                self.xy_state_topic,
                self.xy_command_topic,
            ),
            "effect": (
                "fx_stat_t",
                "fx_cmd_t",
                self.effect_enabled,
                self.effect_state_topic,
                self.effect_command_topic,
            ),
        }
        for (
            state_key,
            command_key,
            enabled,
            state_topic,
            command_topic,
        ) in feature_keys.values():
            if enabled:
                config[state_key] = state_topic
                config[command_key] = command_topic
        if self.effect_enabled and self.effect_list:
            config["fx_list"] = self.effect_list
        if self.color_temp_kelvin:
            config["clr_temp_k"] = True
        if self.white_enabled:
            config["whit_cmd_t"] = self.white_command_topic
        if self.brightness_scale != 255:
            config["bri_scl"] = self.brightness_scale
        if self.white_scale != 255:
            config["whit_scl"] = self.white_scale
        if self.optimistic:
            config["opt"] = True
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return config
