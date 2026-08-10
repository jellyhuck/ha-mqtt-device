"""Events delivered to entity ``on_event`` callbacks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

__all__ = ["Event", "EventCallback"]


@dataclass(frozen=True, slots=True)
class Event:
    """A single update delivered to an entity's ``on_event`` callback.

    Entities that subscribe to MQTT topics (for example a switch listening for
    Home Assistant commands) turn each incoming message into an
    :class:`Event`. The common fields describe where the message came from;
    ``state`` is populated for event types that carry a switch state.

    Attributes:
        timestamp: UTC time the message was received.
        event_type: Kind of event, for example ``"command"`` for a command
            received on a switch's command topic.
        topic: The resolved MQTT topic the message arrived on.
        topic_type: The discovery config field that names the topic, for
            example ``"command_topic"``.
        message: The MQTT payload, decoded as UTF-8 text.
        state: Optional state derived from the payload, for example ``"on"``
            or ``"off"`` for a switch command. ``None`` when the payload
            cannot be mapped to a known state.
    """

    timestamp: datetime
    event_type: str
    topic: str
    topic_type: str
    message: str
    state: str | None = None


EventCallback = Callable[[Event], Awaitable[None]]
"""Signature of an async callback invoked for every entity event."""
