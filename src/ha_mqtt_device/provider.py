"""Core MQTT provider interface, independent of any concrete MQTT client library."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["Message", "MqttMessageCallback", "MqttProvider"]


@dataclass(frozen=True, slots=True)
class Message:
    """A single MQTT message delivered to a subscribed callback.

    Attributes:
        topic: The topic the message was published on.
        payload: The raw message payload as bytes.
    """

    topic: str
    payload: bytes


MqttMessageCallback = Callable[[Message], Awaitable[None]]
"""Signature of an async callback invoked for each matching message."""


@runtime_checkable
class MqttProvider(Protocol):
    """Async interface for an MQTT client provider.

    Implementations must be able to publish messages, subscribe to topics,
    run a message loop, and shut down gracefully. All methods raise an
    exception when the underlying operation fails.
    """

    async def publish(
        self, topic: str, message: str | bytes, retain: bool = False
    ) -> None:
        """Publish ``message`` to ``topic``.

        Set ``retain`` to ``True`` to ask the broker to retain the message
        for future subscribers.

        Raises:
            Exception: If the message could not be published.
        """
        ...

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        """Register ``callback`` to be awaited for every message on ``topic``.

        Calling this multiple times for the same topic appends additional
        callbacks; all of them are invoked for each matching message.

        Raises:
            Exception: If the subscription could not be registered.
        """
        ...

    def run(self) -> Awaitable[None]:
        """Start the message loop in the background and return without awaiting.

        The returned awaitable completes once the loop has shut down; call
        :meth:`stop` to shut it down. Callers that want to block until the
        loop ends may await the returned awaitable directly.

        Raises:
            Exception: If the client could not be started.
        """
        ...

    async def stop(self) -> None:
        """Gracefully stop the message loop started by :meth:`run`.

        Calling this when the provider is not running has no effect.
        """
        ...
