"""Water heater entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message
from ha_mqtt_device.values.mapped_value import MappedValue
from ha_mqtt_device.values.numeric_value import NumericValue
from ha_mqtt_device.values.str_value import StrValue

__all__ = ["WaterHeater"]

logger = logging.getLogger(__name__)

DEFAULT_MODES = (
    "off",
    "eco",
    "electric",
    "gas",
    "heat_pump",
    "high_demand",
    "performance",
)
DEFAULT_PAYLOAD_ON = "ON"
DEFAULT_PAYLOAD_OFF = "OFF"
DEFAULT_TEMPERATURE_UNIT = "C"
DEFAULT_MIN_TEMP_C = 43.3
DEFAULT_MAX_TEMP_C = 60.0
DEFAULT_MIN_TEMP_F = 110.0
DEFAULT_MAX_TEMP_F = 140.0
VALID_PRECISIONS = (0.1, 0.5, 1.0)


@dataclass
class WaterHeater(Entity):
    """An MQTT water heater with temperature, mode, and power controls.

    State is published on separate current-temperature, target-temperature,
    and mode topics. Home Assistant commands arrive on the corresponding
    command topics and are delivered to :meth:`on_event` callbacks; this class
    does not change hardware state automatically.
    """

    component = "water_heater"

    modes: list[str] | None = None
    temperature_unit: str | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    precision: float | None = None
    initial: float | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    optimistic: bool = False
    power_enabled: bool = False

    _current_temperature_value: Entity.StateValue[float] = field(
        init=False, repr=False, compare=False
    )
    _target_temperature_value: Entity.StateValue[float] = field(
        init=False, repr=False, compare=False
    )
    _mode_value: Entity.StateValue[str] = field(init=False, repr=False, compare=False)
    _power_value: Entity.StateValue[bool] | None = field(
        init=False, repr=False, compare=False
    )

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.modes is not None:
            if not self.modes:
                raise ValueError("modes must not be empty")
            if len(set(self.modes)) != len(self.modes):
                raise ValueError("modes must not contain duplicates")
            unsupported = set(self.modes) - set(DEFAULT_MODES)
            if unsupported:
                raise ValueError(f"unsupported water heater modes: {unsupported}")
        if self.temperature_unit not in (None, "C", "F"):
            raise ValueError("temperature_unit must be 'C' or 'F'")
        if self.precision is not None and self.precision not in VALID_PRECISIONS:
            raise ValueError(f"precision must be one of {VALID_PRECISIONS}")
        if self.min_temp is not None:
            self._validate_number(self.min_temp, "min_temp")
        if self.max_temp is not None:
            self._validate_number(self.max_temp, "max_temp")
        if (
            self.min_temp is not None
            and self.max_temp is not None
            and self.min_temp >= self.max_temp
        ):
            raise ValueError("min_temp must be less than max_temp")
        if self.initial is not None:
            self._validate_number(self.initial, "initial")
            if not self._in_temperature_range(self.initial):
                raise ValueError("initial is outside the configured temperature range")
        if not isinstance(self.payload_on, str) or not isinstance(
            self.payload_off, str
        ):
            raise TypeError("power payloads must be strings")
        self._current_temperature_value = self._make_persistent_state(
            NumericValue(), "state/current_temperature"
        )
        self._target_temperature_value = self._make_persistent_state(
            NumericValue(), "state/temperature"
        )
        self._mode_value = self._make_persistent_state(StrValue(), "state/mode")
        self._power_value = (
            self._make_momentary_state(
                MappedValue({True: self.payload_on, False: self.payload_off}),
                "command/power",
            )
            if self.power_enabled
            else None
        )

    @property
    def current_temperature_topic(self) -> str:
        """Return the resolved current-temperature state topic."""
        return self._current_temperature_value.topic().topic

    @property
    def temperature_state_topic(self) -> str:
        """Return the resolved target-temperature state topic."""
        return self._target_temperature_value.topic().topic

    @property
    def temperature_command_topic(self) -> str:
        """Return the resolved target-temperature command topic."""
        return self.command_topic_for("temperature")

    @property
    def mode_state_topic(self) -> str:
        """Return the resolved operation-mode state topic."""
        return self._mode_value.topic().topic

    @property
    def mode_command_topic(self) -> str:
        """Return the resolved operation-mode command topic."""
        return self.command_topic_for("mode")

    @property
    def power_command_topic(self) -> str:
        """Return the resolved optional power command topic."""
        return self.command_topic_for("power")

    async def set_current_temperature(self, temperature: float) -> None:
        """Publish the current water temperature."""
        self._validate_number(temperature, "temperature")
        await self._current_temperature_value.set_value(temperature)

    async def set_target_temperature(self, temperature: float) -> None:
        """Publish the current target temperature."""
        self._validate_temperature(temperature)
        await self._target_temperature_value.set_value(temperature)

    async def set_mode(self, mode: str) -> None:
        """Publish the current operation mode."""
        if mode not in self._effective_modes:
            raise ValueError(f"unsupported water heater mode: {mode!r}")
        await self._mode_value.set_value(mode)

    async def set_power(self, enabled: bool) -> None:
        """Publish a power payload to the optional power command topic."""
        if not self.power_enabled:
            raise ValueError("power commands are not enabled")
        assert self._power_value is not None
        await self._power_value.set_value(enabled)

    async def on_event(self, callback: EventCallback) -> None:
        """Subscribe once to enabled command topics and register ``callback``."""
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                self.temperature_command_topic,
                self._dispatch_temperature,
            )
            await device.provider.subscribe(
                self.mode_command_topic, self._dispatch_mode
            )
            if self.power_enabled:
                await device.provider.subscribe(
                    self.power_command_topic,
                    self._dispatch_power,
                )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch_temperature(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        state = self._temperature_state(payload)
        await self._notify(
            "temperature", "temperature_command_topic", message, payload, state
        )

    async def _dispatch_mode(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        state = payload if payload in self._effective_modes else None
        await self._notify("mode", "mode_command_topic", message, payload, state)

    async def _dispatch_power(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        if payload == self.payload_on:
            state: str | None = "on"
        elif payload == self.payload_off:
            state = "off"
        else:
            state = None
        await self._notify("power", "power_command_topic", message, payload, state)

    async def _notify(
        self,
        event_type: str,
        topic_type: str,
        message: Message,
        payload: str,
        state: str | None,
    ) -> None:
        event = Event(
            timestamp=datetime.now(UTC),
            event_type=event_type,
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

    def _temperature_state(self, payload: str) -> str | None:
        try:
            value = float(payload)
        except ValueError:
            return None
        if not isfinite(value) or not self._in_temperature_range(value):
            return None
        return payload

    @property
    def _effective_modes(self) -> list[str] | tuple[str, ...]:
        return self.modes if self.modes is not None else DEFAULT_MODES

    def _default_temperature_limits(self) -> tuple[float, float]:
        if self.temperature_unit == "F":
            return DEFAULT_MIN_TEMP_F, DEFAULT_MAX_TEMP_F
        return DEFAULT_MIN_TEMP_C, DEFAULT_MAX_TEMP_C

    def _temperature_limits(self) -> tuple[float, float]:
        default_min, default_max = self._default_temperature_limits()
        return (
            self.min_temp if self.min_temp is not None else default_min,
            self.max_temp if self.max_temp is not None else default_max,
        )

    def _in_temperature_range(self, temperature: float) -> bool:
        minimum, maximum = self._temperature_limits()
        return minimum <= temperature <= maximum

    @staticmethod
    def _validate_number(value: float, field_name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name} must be a number")
        if not isfinite(value):
            raise ValueError(f"{field_name} must be finite")

    def _validate_temperature(self, temperature: float) -> None:
        self._validate_number(temperature, "temperature")
        if not self._in_temperature_range(temperature):
            minimum, maximum = self._temperature_limits()
            raise ValueError(
                f"temperature {temperature!r} is outside {minimum}..{maximum}"
            )

    @staticmethod
    def _number_payload(value: float) -> str:
        return str(value)

    def discovery_config(self) -> dict[str, object]:
        """Return this water heater's compact MQTT discovery configuration."""
        config = super().discovery_config()
        config["curr_temp_t"] = self.current_temperature_topic
        config["temp_stat_t"] = self.temperature_state_topic
        config["temp_cmd_t"] = self.temperature_command_topic
        config["mode_stat_t"] = self.mode_state_topic
        config["mode_cmd_t"] = self.mode_command_topic
        if self.power_enabled:
            config["power_command_topic"] = self.power_command_topic
        if self.modes is not None:
            config["modes"] = self.modes
        default_min, default_max = self._default_temperature_limits()
        if self.min_temp is not None and self.min_temp != default_min:
            config["min_temp"] = self.min_temp
        if self.max_temp is not None and self.max_temp != default_max:
            config["max_temp"] = self.max_temp
        if self.initial is not None:
            config["init"] = self.initial
        if self.precision is not None:
            config["prec"] = self.precision
        if self.temperature_unit is not None:
            config["temp_unit"] = self.temperature_unit
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        if self.optimistic:
            config["opt"] = True
        return self._resolve_discovery_config(config)
