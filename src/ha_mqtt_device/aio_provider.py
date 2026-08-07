"""MQTT provider implementation backed by the ``aiomqtt`` client library."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from ha_mqtt_device.provider import Message, MqttMessageCallback

if TYPE_CHECKING:
    import aiomqtt

__all__ = ["AioMqttProvider"]

logger = logging.getLogger(__name__)

_aiomqtt: Any = None


def _load_aiomqtt() -> Any:
    """Import and cache the ``aiomqtt`` module, or raise a helpful error."""
    global _aiomqtt
    if _aiomqtt is None:
        try:
            import aiomqtt
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "AioMqttProvider requires the 'mqtt' extra: "
                "install it with `pip install 'ha-mqtt-device[mqtt]'`."
            ) from exc
        _aiomqtt = aiomqtt
    return _aiomqtt


class AioMqttProvider:
    """An :class:`~ha_mqtt_device.provider.MqttProvider` backed by an ``aiomqtt`` client.

    The MQTT client is created lazily from the keyword arguments passed to the
    constructor, which are forwarded unchanged to :class:`aiomqtt.Client` (for
    example ``host``, ``port``, ``username``, and ``password``).

    The ``aiomqtt`` package is only required when this provider is constructed;
    the rest of the library works without it. Install it with
    ``pip install "ha-mqtt-device[mqtt]"``.
    """

    def __init__(self, **config: Any) -> None:
        _load_aiomqtt()  # fail fast if the optional dependency is missing
        self._config = config
        self._callbacks: dict[str, list[MqttMessageCallback]] = {}
        self._client: aiomqtt.Client | None = None
        self._running = False
        self._stop_event = asyncio.Event()
        self._stopped_event = asyncio.Event()
        self._pending_tasks: set[asyncio.Task[None]] = set()

    @property
    def is_running(self) -> bool:
        """Whether :meth:`run` is currently active."""
        return self._running

    async def publish(self, topic: str, message: str | bytes) -> None:
        """Publish ``message`` to ``topic``.

        When :meth:`run` is active the long-lived connection is reused;
        otherwise a short-lived connection is opened for the publish.

        Raises:
            Exception: If the message could not be published.
        """
        if self._client is not None:
            await self._client.publish(topic, message)
            return
        async with self._new_client() as client:
            await client.publish(topic, message)

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        """Register ``callback`` for messages on ``topic``.

        Multiple callbacks may be registered for the same topic; each one is
        invoked for every matching message. If the provider is running, the
        subscription is also sent to the broker immediately.

        Raises:
            Exception: If the subscription could not be registered.
        """
        self._callbacks.setdefault(topic, []).append(callback)
        if self._client is not None:
            await self._client.subscribe(topic)

    async def run(self) -> None:
        """Connect to the broker and process messages until :meth:`stop`.

        Messages are dispatched to their registered callbacks concurrently as
        ``asyncio`` tasks; a failing callback is logged and does not stop the
        message pump.

        Raises:
            RuntimeError: If the provider is already running.
            Exception: If the client could not be started.
        """
        if self._running:
            raise RuntimeError("AioMqttProvider is already running")
        self._running = True
        self._stop_event.clear()
        self._stopped_event.clear()
        try:
            async with self._new_client() as client:
                self._client = client
                try:
                    for topic in self._callbacks:
                        await client.subscribe(topic)
                    pump = asyncio.create_task(self._pump(client))
                    try:
                        await self._stop_event.wait()
                    finally:
                        pump.cancel()
                        await asyncio.gather(pump, return_exceptions=True)
                finally:
                    await self._drain_pending()
        finally:
            self._client = None
            self._running = False
            self._stopped_event.set()

    async def stop(self) -> None:
        """Gracefully stop the message loop started by :meth:`run`.

        This signals :meth:`run` to shut down, waits for it to finish draining
        in-flight callbacks, and closes the broker connection. Calling it when
        the provider is not running has no effect.
        """
        self._stop_event.set()
        if self._running:
            await self._stopped_event.wait()

    def _new_client(self) -> aiomqtt.Client:
        aiomqtt = _load_aiomqtt()
        return aiomqtt.Client(**self._config)

    async def _pump(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            await self._dispatch(message)

    async def _dispatch(self, message: aiomqtt.Message) -> None:
        topic = str(message.topic)  # aiomqtt types topic as NewType over str
        callbacks = self._callbacks.get(topic)
        if not callbacks:
            return
        payload = message.payload
        if isinstance(payload, str):
            payload = payload.encode()
        elif payload is None:
            payload = b""
        wrapped = Message(topic=topic, payload=payload)
        for callback in callbacks:
            task = asyncio.create_task(self._invoke_callback(callback, wrapped))
            self._pending_tasks.add(task)
            task.add_done_callback(self._pending_tasks.discard)

    async def _invoke_callback(
        self, callback: MqttMessageCallback, message: Message
    ) -> None:
        try:
            await callback(message)
        except Exception:
            logger.exception("MQTT callback failed for topic %r", message.topic)

    async def _drain_pending(self) -> None:
        if not self._pending_tasks:
            return
        await asyncio.gather(*self._pending_tasks, return_exceptions=True)
