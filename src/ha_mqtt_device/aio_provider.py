"""MQTT provider implementation backed by the ``aiomqtt`` client library."""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

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
        self._run_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._stopped_event = asyncio.Event()
        self._pending_tasks: set[asyncio.Task[None]] = set()

    @property
    def is_running(self) -> bool:
        """Whether :meth:`run` is currently active."""
        return self._running

    async def __aenter__(self) -> Self:
        """Start the message loop when entering an ``async with`` block.

        Equivalent to calling :meth:`run` without awaiting the returned task.
        """
        self.run()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Gracefully shut the message loop down when leaving an ``async with`` block.

        Equivalent to awaiting :meth:`stop`. Exceptions raised inside the block
        are not suppressed; the provider is still stopped before they propagate.
        """
        await self.stop()

    async def publish(self, topic: str, message: str | bytes) -> None:
        """Publish ``message`` to ``topic``.

        When :meth:`run` is active the long-lived connection is reused;
        otherwise a short-lived connection is opened for the publish.

        The short-lived connection is entered and exited through aiomqtt's
        context manager, using only its public API. The ``__aexit__`` in the
        ``finally`` block runs even if the publish task is cancelled while the
        connect is in flight. Python delivers that cancellation immediately,
        while the executor-thread connect keeps running; if the connect only
        completes after ``__aexit__`` ran, aiomqtt/paho leave a residual
        socket and background task behind. That is an upstream limitation no
        provider design — with or without internals — can avoid (see
        ``experiments/midconnect_race_truth.py``).

        Raises:
            Exception: If the message could not be published.
        """
        if self._client is not None:
            await self._client.publish(topic, message)
            return
        client = self._new_client()
        try:
            await client.__aenter__()
            await client.publish(topic, message)
        finally:
            await client.__aexit__(None, None, None)

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

    def run(self) -> asyncio.Task[None]:
        """Start the message loop in a background task and return immediately.

        The returned task connects to the broker, subscribes to the registered
        topics, and processes messages until :meth:`stop` is called. Messages
        are dispatched to their callbacks concurrently as ``asyncio`` tasks; a
        failing callback is logged and does not stop the message pump.

        The task is scheduled on the current event loop but not awaited, so the
        provider keeps running while the caller does other work. Use
        :meth:`stop` (or the context manager protocol) to shut it down.

        Raises:
            RuntimeError: If the provider is already running.
        """
        if self._running:
            raise RuntimeError("AioMqttProvider is already running")
        self._running = True
        self._stop_event.clear()
        self._stopped_event.clear()
        self._run_task = asyncio.create_task(self._run())
        return self._run_task

    async def _run(self) -> None:
        """The message loop started by :meth:`run`; see there for details."""
        client: aiomqtt.Client | None = None
        try:
            client = self._new_client()
            # Entered directly (no intermediate task) and exited unconditionally:
            # see publish() for why this is safe under cancellation.
            await client.__aenter__()
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
            if client is not None:
                await client.__aexit__(None, None, None)
            self._client = None
            self._run_task = None
            self._running = False

    async def stop(self) -> None:
        """Gracefully stop the message loop started by :meth:`run`.

        Signals :meth:`run` to shut down, waits for the run task to finish
        draining in-flight callbacks and close the broker connection, then
        awaits any remaining pending callback tasks. Emits ``_stopped_event``
        once everything has shut down. Calling it when the provider is not
        running has no effect.
        """
        self._stop_event.set()
        run_task = self._run_task
        if run_task is not None:
            await asyncio.gather(run_task, return_exceptions=True)
        await self._drain_pending()
        self._stopped_event.set()

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
