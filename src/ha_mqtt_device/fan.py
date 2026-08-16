"""Fan entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Fan"]

logger = logging.getLogger(__name__)

#: Home Assistant MQTT discovery default for ``payload_on``.
DEFAULT_PAYLOAD_ON = "ON"

#: Home Assistant MQTT discovery default for ``payload_off``.
DEFAULT_PAYLOAD_OFF = "OFF"

#: Home Assistant MQTT discovery default for ``payload_oscillation_on``.
DEFAULT_PAYLOAD_OSCILLATION_ON = "oscillate_on"

#: Home Assistant MQTT discovery default for ``payload_oscillation_off``.
DEFAULT_PAYLOAD_OSCILLATION_OFF = "oscillate_off"

#: Home Assistant MQTT discovery default for ``payload_reset_percentage``.
DEFAULT_PAYLOAD_RESET_PERCENTAGE = "reset_percentage"

#: Home Assistant MQTT discovery defaults for ``preset_modes``.
DEFAULT_PRESET_MODES: tuple[str, ...] = ("auto", "smart")

#: Home Assistant MQTT discovery default for ``speed_range_min``.
DEFAULT_SPEED_RANGE_MIN = 1

#: Home Assistant MQTT discovery default for ``speed_range_max``.
DEFAULT_SPEED_RANGE_MAX = 100

#: ``event_type`` of events built from messages on the command topic.
_EVENT_TYPE_COMMAND = "command"

#: ``event_type`` of events built from messages on the percentage command topic.
_EVENT_TYPE_PERCENTAGE = "percentage"

#: ``event_type`` of events built from messages on the preset-mode command topic.
_EVENT_TYPE_PRESET_MODE = "preset_mode"

#: ``event_type`` of events built from messages on the oscillation command topic.
_EVENT_TYPE_OSCILLATION = "oscillation"

#: ``event_type`` of events built from messages on the direction command topic.
_EVENT_TYPE_DIRECTION = "direction"

#: Discovery config field that names the command topic.
_TOPIC_TYPE_COMMAND = "command_topic"

#: Discovery config field that names the percentage command topic.
_TOPIC_TYPE_PERCENTAGE = "percentage_command_topic"

#: Discovery config field that names the preset-mode command topic.
_TOPIC_TYPE_PRESET_MODE = "preset_mode_command_topic"

#: Discovery config field that names the oscillation command topic.
_TOPIC_TYPE_OSCILLATION = "oscillation_command_topic"

#: Discovery config field that names the direction command topic.
_TOPIC_TYPE_DIRECTION = "direction_command_topic"


@dataclass
class Fan(Entity):
    """A fan belonging to a device.

    A fan has paired state and command topics. The device publishes its on/off
    state to the state topic (``~/<unique_id>/state``) with :meth:`set_state`,
    and optional percentage, preset-mode, oscillation, and direction features
    publish to their own state topics when enabled. It receives commands from
    Home Assistant on the command topic (``~/<unique_id>/command``) and on
    each enabled feature's command topic. Registering an async callback with
    :meth:`on_event` subscribes to every enabled command topic and delivers
    each message as an :class:`~ha_mqtt_device.event.Event`::

        fan = Fan(
            unique_id="ceiling_fan",
            name="Ceiling fan",
            percentage_enabled=True,
            oscillation_enabled=True,
        )
        device = Device(provider, info, entities=[fan])

        async def on_command(event: Event) -> None:
            if event.event_type == "command":
                await fan.set_state(event.state == "on")
            elif event.event_type == "percentage" and event.state is not None:
                await fan.set_percentage(int(event.state))
            elif event.event_type == "oscillation":
                await fan.set_oscillation(event.state == "on")

        async with device:
            await fan.on_event(on_command)
            await fan.set_state(True)
            await fan.set_percentage(60)

    Unlike :meth:`set_state`, :meth:`set_percentage`, :meth:`set_preset_mode`,
    :meth:`set_oscillation`, and :meth:`set_direction`, commands received from
    Home Assistant do not change the fan by themselves — the application
    decides what to do in the callback.

    Attributes:
        unique_id: See :class:`~ha_mqtt_device.entity.Entity`.
        name: See :class:`~ha_mqtt_device.entity.Entity`.
        device_class: Home Assistant device class (``dev_cla``), for example
            ``"fan"`` or ``"ceiling"``. Omitted from the discovery config when
            unset.
        payload_on: Payload published when the fan reports ``True`` and the
            default for the on state/command mapping.
        payload_off: Payload published when the fan reports ``False`` and the
            default for the off state/command mapping.
        payload_oscillation_on: Payload published when oscillation reports
            ``True`` (``pl_osc_on``).
        payload_oscillation_off: Payload published when oscillation reports
            ``False`` (``pl_osc_off``).
        payload_reset_percentage: Payload that switches from a preset mode
            back to percentage control (``pl_rst_pct``). Also the payload
            published by :meth:`set_preset_mode` for ``None``.
        preset_modes: Preset modes the fan supports (``pr_modes``). Defaults
            to ``["auto", "smart"]``.
        speed_range_min: Minimum value Home Assistant treats as 0% speed
            (``spd_rng_min``). Defaults to ``1``.
        speed_range_max: Maximum value Home Assistant treats as 100% speed
            (``spd_rng_max``). Defaults to ``100``.
        optimistic: Whether Home Assistant should assume commands take effect
            immediately (``opt``). Defaults to ``False``.
        percentage_enabled: Whether the fan has a percentage (speed) control.
            When ``True`` the percentage state and command topics are
            advertised and subscribed. Defaults to ``True``.
        preset_mode_enabled: Whether the fan has preset modes. When ``True``
            the preset-mode state and command topics are advertised and
            subscribed. Defaults to ``False``.
        oscillation_enabled: Whether the fan can oscillate. When ``True`` the
            oscillation state and command topics are advertised and
            subscribed. Defaults to ``False``.
        direction_enabled: Whether the fan direction can be changed. When
            ``True`` the direction state and command topics are advertised and
            subscribed. Defaults to ``False``.
    """

    component = "fan"

    device_class: str | None = None
    payload_on: str = DEFAULT_PAYLOAD_ON
    payload_off: str = DEFAULT_PAYLOAD_OFF
    payload_oscillation_on: str = DEFAULT_PAYLOAD_OSCILLATION_ON
    payload_oscillation_off: str = DEFAULT_PAYLOAD_OSCILLATION_OFF
    payload_reset_percentage: str = DEFAULT_PAYLOAD_RESET_PERCENTAGE
    preset_modes: list[str] = field(default_factory=lambda: list(DEFAULT_PRESET_MODES))
    speed_range_min: int = DEFAULT_SPEED_RANGE_MIN
    speed_range_max: int = DEFAULT_SPEED_RANGE_MAX
    optimistic: bool = False
    percentage_enabled: bool = True
    preset_mode_enabled: bool = False
    oscillation_enabled: bool = False
    direction_enabled: bool = False

    #: Callbacks registered via :meth:`on_event`.
    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    #: Whether the incoming-topic subscriptions have been registered.
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.preset_mode_enabled and not self.preset_modes:
            raise ValueError(
                "preset_modes must contain at least one mode when "
                "preset_mode_enabled is True"
            )

    @property
    def command_topic(self) -> str:
        """Command topic as ``~`` shorthand, ``~/<unique_id>/command``."""
        return f"~/{self.unique_id}/command"

    @property
    def percentage_state_topic(self) -> str:
        """Percentage state topic as ``~`` shorthand, ``~/<unique_id>/percentage_state``."""
        return f"~/{self.unique_id}/percentage_state"

    @property
    def percentage_command_topic(self) -> str:
        """Percentage command topic, ``~/<unique_id>/percentage_command``."""
        return f"~/{self.unique_id}/percentage_command"

    @property
    def preset_mode_state_topic(self) -> str:
        """Preset-mode state topic, ``~/<unique_id>/preset_mode_state``."""
        return f"~/{self.unique_id}/preset_mode_state"

    @property
    def preset_mode_command_topic(self) -> str:
        """Preset-mode command topic, ``~/<unique_id>/preset_mode_command``."""
        return f"~/{self.unique_id}/preset_mode_command"

    @property
    def oscillation_state_topic(self) -> str:
        """Oscillation state topic, ``~/<unique_id>/oscillation_state``."""
        return f"~/{self.unique_id}/oscillation_state"

    @property
    def oscillation_command_topic(self) -> str:
        """Oscillation command topic, ``~/<unique_id>/oscillation_command``."""
        return f"~/{self.unique_id}/oscillation_command"

    @property
    def direction_state_topic(self) -> str:
        """Direction state topic, ``~/<unique_id>/direction_state``."""
        return f"~/{self.unique_id}/direction_state"

    @property
    def direction_command_topic(self) -> str:
        """Direction command topic, ``~/<unique_id>/direction_command``."""
        return f"~/{self.unique_id}/direction_command"

    async def set_state(self, state: bool) -> None:
        """Publish the fan's on/off state.

        ``True`` publishes :attr:`payload_on` and ``False`` publishes
        :attr:`payload_off` to the state topic (``~/<unique_id>/state``).
        Publishing does not trigger callbacks registered with
        :meth:`on_event`; only messages received on the command topics do.

        Raises:
            RuntimeError: If the fan is not bound to a device.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        payload = self.payload_on if state else self.payload_off
        topic = device.info.resolve_topic(self.state_topic)
        await device.provider.publish(topic, payload)

    async def set_percentage(self, percentage: int) -> None:
        """Publish the fan's speed as a percentage.

        ``percentage`` is converted to a string and published to the
        percentage state topic (``~/<unique_id>/percentage_state``), for
        example ``60`` is published as ``"60"``.

        Raises:
            RuntimeError: If the fan is not bound to a device.
            ValueError: If percentage control is disabled.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        self._require_enabled(self.percentage_enabled, "percentage")
        self._validate_percentage(percentage)
        topic = device.info.resolve_topic(self.percentage_state_topic)
        await device.provider.publish(topic, str(percentage))

    async def set_preset_mode(self, preset_mode: str | None) -> None:
        """Publish the fan's preset mode.

        ``preset_mode`` must be in :attr:`preset_modes`; ``None`` publishes
        :attr:`payload_reset_percentage` (``pl_rst_pct``) to signal percentage
        control. The payload is published to the preset-mode state topic
        (``~/<unique_id>/preset_mode_state``).

        Raises:
            RuntimeError: If the fan is not bound to a device.
            ValueError: If preset-mode control is disabled or ``preset_mode``
                is not in :attr:`preset_modes`.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        self._require_enabled(self.preset_mode_enabled, "preset_mode")
        if preset_mode is None:
            payload = self.payload_reset_percentage
        elif preset_mode in self.preset_modes:
            payload = preset_mode
        else:
            raise ValueError(
                f"preset_mode {preset_mode!r} is not in preset_modes "
                f"{self.preset_modes!r}"
            )
        topic = device.info.resolve_topic(self.preset_mode_state_topic)
        await device.provider.publish(topic, payload)

    async def set_oscillation(self, oscillation: bool) -> None:
        """Publish the fan's oscillation state.

        ``True`` publishes :attr:`payload_oscillation_on` and ``False``
        publishes :attr:`payload_oscillation_off` to the oscillation state
        topic (``~/<unique_id>/oscillation_state``).

        Raises:
            RuntimeError: If the fan is not bound to a device.
            ValueError: If oscillation control is disabled.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        self._require_enabled(self.oscillation_enabled, "oscillation")
        payload = (
            self.payload_oscillation_on if oscillation else self.payload_oscillation_off
        )
        topic = device.info.resolve_topic(self.oscillation_state_topic)
        await device.provider.publish(topic, payload)

    async def set_direction(self, direction: str) -> None:
        """Publish the fan's direction.

        ``direction`` must be ``"forward"`` or ``"reverse"``; it is published
        verbatim to the direction state topic
        (``~/<unique_id>/direction_state``).

        Raises:
            RuntimeError: If the fan is not bound to a device.
            ValueError: If direction control is disabled or ``direction`` is
                not ``"forward"`` or ``"reverse"``.
            Exception: If the message could not be published.
        """
        device = self._require_device()
        self._require_enabled(self.direction_enabled, "direction")
        if direction not in ("forward", "reverse"):
            raise ValueError("direction must be 'forward' or 'reverse'")
        topic = device.info.resolve_topic(self.direction_state_topic)
        await device.provider.publish(topic, direction)

    async def on_event(self, callback: EventCallback) -> None:
        """Register ``callback`` for every command received from Home Assistant.

        Appends ``callback`` and, on first use, subscribes to the command
        topic (``~/<unique_id>/command``) plus every enabled feature's command
        topic. Every message is awaited as an
        :class:`~ha_mqtt_device.event.Event`:

        - On the command topic, ``event_type`` is ``"command"``,
          ``topic_type`` is ``"command_topic"``, and ``state`` is ``"on"`` or
          ``"off"`` derived from the payload via
          :attr:`payload_on`/:attr:`payload_off`.
        - On the percentage command topic, ``event_type`` is
          ``"percentage"``, ``topic_type`` is ``"percentage_command_topic"``,
          and ``state`` is the payload when it parses as a number.
        - On the preset-mode command topic, ``event_type`` is
          ``"preset_mode"``, ``topic_type`` is ``"preset_mode_command_topic"``,
          and ``state`` is the payload when it is in :attr:`preset_modes` or
          equals :attr:`payload_reset_percentage`.
        - On the oscillation command topic, ``event_type`` is
          ``"oscillation"``, ``topic_type`` is ``"oscillation_command_topic"``,
          and ``state`` is ``"on"`` or ``"off"`` derived from the payload via
          :attr:`payload_oscillation_on`/:attr:`payload_oscillation_off`.
        - On the direction command topic, ``event_type`` is ``"direction"``,
          ``topic_type`` is ``"direction_command_topic"``, and ``state`` is
          ``"forward"`` or ``"reverse"``.

        An unknown payload is still delivered with ``state`` ``None``.

        The broker connection must be running for commands to be delivered;
        subscriptions registered before :meth:`provider.run()
        <ha_mqtt_device.provider.MqttProvider.run>` are applied once the
        message loop starts.

        Raises:
            RuntimeError: If the fan is not bound to a device.
            Exception: If a subscription could not be registered.
        """
        device = self._require_device()
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch_command
            )
            if self.percentage_enabled:
                await device.provider.subscribe(
                    device.info.resolve_topic(self.percentage_command_topic),
                    self._dispatch_percentage,
                )
            if self.preset_mode_enabled:
                await device.provider.subscribe(
                    device.info.resolve_topic(self.preset_mode_command_topic),
                    self._dispatch_preset_mode,
                )
            if self.oscillation_enabled:
                await device.provider.subscribe(
                    device.info.resolve_topic(self.oscillation_command_topic),
                    self._dispatch_oscillation,
                )
            if self.direction_enabled:
                await device.provider.subscribe(
                    device.info.resolve_topic(self.direction_command_topic),
                    self._dispatch_direction,
                )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch_command(self, message: Message) -> None:
        """Turn a command topic message into an :class:`Event` and await it."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_COMMAND,
            topic_type=_TOPIC_TYPE_COMMAND,
            message=message,
            payload=payload,
            state=self._command_state(payload),
        )

    async def _dispatch_percentage(self, message: Message) -> None:
        """Turn a percentage command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_PERCENTAGE,
            topic_type=_TOPIC_TYPE_PERCENTAGE,
            message=message,
            payload=payload,
            state=self._percentage_state(payload),
        )

    async def _dispatch_preset_mode(self, message: Message) -> None:
        """Turn a preset-mode command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_PRESET_MODE,
            topic_type=_TOPIC_TYPE_PRESET_MODE,
            message=message,
            payload=payload,
            state=self._preset_mode_state(payload),
        )

    async def _dispatch_oscillation(self, message: Message) -> None:
        """Turn an oscillation command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_OSCILLATION,
            topic_type=_TOPIC_TYPE_OSCILLATION,
            message=message,
            payload=payload,
            state=self._oscillation_state(payload),
        )

    async def _dispatch_direction(self, message: Message) -> None:
        """Turn a direction command topic message into an :class:`Event`."""
        payload = message.payload.decode("utf-8", errors="replace")
        await self._notify(
            event_type=_EVENT_TYPE_DIRECTION,
            topic_type=_TOPIC_TYPE_DIRECTION,
            message=message,
            payload=payload,
            state=self._direction_state(payload),
        )

    async def _notify(
        self,
        event_type: str,
        topic_type: str,
        message: Message,
        payload: str,
        state: str | None,
    ) -> None:
        """Build the event and await every registered callback."""
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

    def _command_state(self, payload: str) -> str | None:
        """Map a command payload to ``"on"``, ``"off"``, or ``None``."""
        if payload == self.payload_on:
            return "on"
        if payload == self.payload_off:
            return "off"
        return None

    def _percentage_state(self, payload: str) -> str | None:
        """Map a percentage command payload to the payload or ``None``.

        The payload is returned verbatim when it parses as a number;
        anything else maps to ``None``.
        """
        try:
            percentage = float(payload)
        except ValueError:
            return None
        if (
            not isfinite(percentage)
            or not percentage.is_integer()
            or not self._percentage_in_range(int(percentage))
        ):
            return None
        return payload

    def _validate_percentage(self, percentage: int) -> None:
        if isinstance(percentage, bool) or not isinstance(percentage, int):
            raise TypeError("percentage must be an integer")
        if not self._percentage_in_range(percentage):
            raise ValueError("percentage is outside the configured speed range")

    def _percentage_in_range(self, percentage: int) -> bool:
        return self.speed_range_min <= percentage <= self.speed_range_max

    def _preset_mode_state(self, payload: str) -> str | None:
        """Map a preset-mode command payload to the payload or ``None``.

        The payload is returned verbatim when it is in :attr:`preset_modes`
        or equals :attr:`payload_reset_percentage`; anything else maps to
        ``None``.
        """
        if payload in self.preset_modes or payload == self.payload_reset_percentage:
            return payload
        return None

    def _oscillation_state(self, payload: str) -> str | None:
        """Map an oscillation command payload to ``"on"``, ``"off"``, or ``None``."""
        if payload == self.payload_oscillation_on:
            return "on"
        if payload == self.payload_oscillation_off:
            return "off"
        return None

    def _direction_state(self, payload: str) -> str | None:
        """Map a direction command payload to ``"forward"``, ``"reverse"``, or ``None``."""
        if payload == "forward":
            return "forward"
        if payload == "reverse":
            return "reverse"
        return None

    def _require_enabled(self, enabled: bool, feature: str) -> None:
        """Raise when a feature's control methods are used while disabled."""
        if not enabled:
            raise ValueError(
                f"{type(self).__name__} {self.unique_id!r} has {feature} control "
                f"disabled; set {feature}_enabled=True"
            )

    def discovery_config(self) -> dict[str, object]:
        """Return this fan's ``cmps`` config entry for the discovery payload."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        config["cmd_t"] = self.command_topic
        if self.payload_on != DEFAULT_PAYLOAD_ON:
            config["pl_on"] = self.payload_on
        if self.payload_off != DEFAULT_PAYLOAD_OFF:
            config["pl_off"] = self.payload_off
        if self.percentage_enabled:
            config["pct_stat_t"] = self.percentage_state_topic
            config["pct_cmd_t"] = self.percentage_command_topic
            if self.payload_reset_percentage != DEFAULT_PAYLOAD_RESET_PERCENTAGE:
                config["pl_rst_pct"] = self.payload_reset_percentage
            if self.speed_range_min != DEFAULT_SPEED_RANGE_MIN:
                config["spd_rng_min"] = self.speed_range_min
            if self.speed_range_max != DEFAULT_SPEED_RANGE_MAX:
                config["spd_rng_max"] = self.speed_range_max
        if self.preset_mode_enabled:
            config["pr_mode_stat_t"] = self.preset_mode_state_topic
            config["pr_mode_cmd_t"] = self.preset_mode_command_topic
            if self.preset_modes != list(DEFAULT_PRESET_MODES):
                config["pr_modes"] = self.preset_modes
            if self.payload_reset_percentage != DEFAULT_PAYLOAD_RESET_PERCENTAGE:
                config["pl_rst_pct"] = self.payload_reset_percentage
        if self.oscillation_enabled:
            config["osc_stat_t"] = self.oscillation_state_topic
            config["osc_cmd_t"] = self.oscillation_command_topic
            if self.payload_oscillation_on != DEFAULT_PAYLOAD_OSCILLATION_ON:
                config["pl_osc_on"] = self.payload_oscillation_on
            if self.payload_oscillation_off != DEFAULT_PAYLOAD_OSCILLATION_OFF:
                config["pl_osc_off"] = self.payload_oscillation_off
        if self.direction_enabled:
            config["dir_stat_t"] = self.direction_state_topic
            config["dir_cmd_t"] = self.direction_command_topic
        if self.optimistic:
            config["opt"] = True
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        return config
