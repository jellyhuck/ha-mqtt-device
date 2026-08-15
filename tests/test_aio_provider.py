"""Tests for AioMqttProvider using a fake aiomqtt client — no broker needed."""

from __future__ import annotations

import asyncio
import time
import types
from collections.abc import AsyncIterator, Generator
from typing import Any, ClassVar, Self
from unittest.mock import patch

import pytest

import ha_mqtt_device.aio_provider as aio_provider_module
from ha_mqtt_device.aio_provider import AioMqttProvider
from ha_mqtt_device.provider import Message


class FakeMessage:
    """Stand-in for an aiomqtt.Message."""

    def __init__(self, topic: str, payload: bytes | str | None) -> None:
        self.topic = topic
        self.payload = payload


class FakeSocket:
    """Minimal paho-like socket holder used to assert teardown closed it."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakePahoClient:
    """Minimal paho-mqtt stand-in exposing ``_sock`` and ``_reset_sockets``."""

    def __init__(self) -> None:
        self._sock: FakeSocket | None = None
        self.reset_count = 0

    def _reset_sockets(self) -> None:
        self.reset_count += 1
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class FakeClient:
    """Fake aiomqtt.Client implementing the subset of the API used here."""

    instances: ClassVar[list[FakeClient]] = []
    # When set, ``__aenter__`` mirrors aiomqtt's behaviour: the connect runs in
    # an executor thread (so it cannot be cancelled) and, once it finishes,
    # registers a background task and an open socket with the event loop.
    connect_delay: ClassVar[float] = 0.0
    simulate_socket: ClassVar[bool] = False

    def __init__(self, **config: Any) -> None:
        self.config = config
        self.subscribed: list[str] = []
        self.published: list[tuple[str, str | bytes]] = []
        self.inbox: asyncio.Queue[FakeMessage | None] = asyncio.Queue()
        self.entered = False
        self.exited = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._misc_task: asyncio.Task[None] | None = None
        self._client: FakePahoClient | None = None
        self.connect_started = asyncio.Event()
        FakeClient.instances.append(self)

    async def __aenter__(self) -> Self:
        self.entered = True
        if self.simulate_socket:
            # Faithful to aiomqtt: the connect runs in an executor thread and,
            # once it finishes, registers the socket and schedules the misc task
            # on the loop. Cancelling the awaiting task mid-connect therefore
            # cannot stop the connect — the socket and misc task still appear.
            self._loop = asyncio.get_running_loop()
            await self._loop.run_in_executor(None, self._blocking_connect)
        return self

    def _blocking_connect(self) -> None:
        # Runs in an executor thread; CANNOT be cancelled by the event loop.
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self.connect_started.set)
        time.sleep(self.connect_delay)
        self._client = FakePahoClient()
        self._client._sock = FakeSocket()
        self._loop.call_soon_threadsafe(self._create_misc_task)

    def _create_misc_task(self) -> None:
        self._misc_task = asyncio.create_task(self._fake_misc_loop())

    async def _fake_misc_loop(self) -> None:
        # Self-terminates once the socket is gone, like paho's loop_misc
        # returning MQTT_ERR_NO_CONN when _sock is None.
        while self._client is not None and self._client._sock is not None:
            await asyncio.sleep(1)

    async def __aexit__(self, *exc_info: object) -> None:
        # Mirrors aiomqtt's graceful disconnect: closing the socket triggers
        # the socket-close callback, which cancels the background misc task.
        self.exited = True
        self.inbox.put_nowait(None)  # unblock the pump if it is still running
        if self._client is not None and self._client._sock is not None:
            self._client._sock.close()
            self._client._sock = None
        if self._misc_task is not None and not self._misc_task.done():
            self._misc_task.cancel()

    async def subscribe(self, topic: str) -> None:
        self.subscribed.append(topic)

    async def publish(self, topic: str, message: str | bytes) -> None:
        self.published.append((topic, message))

    @property
    def messages(self) -> AsyncIterator[FakeMessage]:
        async def generator() -> AsyncIterator[FakeMessage]:
            while True:
                item = await self.inbox.get()
                if item is None:
                    break
                yield item

        return generator()


@pytest.fixture(autouse=True)
def fake_aiomqtt() -> Generator[types.SimpleNamespace]:
    """Replace the provider's aiomqtt loader with a fake aiomqtt module."""
    FakeClient.instances = []
    fake_module = types.SimpleNamespace(Client=FakeClient)
    with patch.object(aio_provider_module, "_load_aiomqtt", return_value=fake_module):
        yield fake_module


async def wait_for_running(provider: AioMqttProvider) -> None:
    """Wait until the provider's message loop is up and subscribed."""
    for _ in range(100):
        if provider.is_running and FakeClient.instances:
            client = FakeClient.instances[-1]
            if client.entered and client.subscribed == list(provider._callbacks):
                return
        await asyncio.sleep(0.01)
    pytest.fail("provider did not start running")


async def test_publish_uses_short_lived_connection(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883)

    await provider.publish("home/device/state", b"on")

    client = FakeClient.instances[-1]
    assert client.entered
    assert client.exited
    assert client.published == [("home/device/state", b"on")]
    assert client.config == {"hostname": "localhost", "port": 1883}
    assert provider.is_running is False


async def test_publish_accepts_str_payload(fake_aiomqtt: types.SimpleNamespace) -> None:
    provider = AioMqttProvider(hostname="localhost")

    await provider.publish("home/device/state", "on")

    assert FakeClient.instances[-1].published == [("home/device/state", "on")]


async def test_subscribe_before_run_registers_callback(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    received: list[Message] = []

    async def on_message(message: Message) -> None:
        received.append(message)

    await provider.subscribe("home/device/cmd", on_message)

    assert provider._callbacks["home/device/cmd"] == [on_message]
    assert FakeClient.instances == []  # no connection opened yet

    run_task = provider.run()
    await wait_for_running(provider)
    client = FakeClient.instances[-1]
    assert client.subscribed == ["home/device/cmd"]

    await provider.stop()
    await run_task


async def test_subscribe_while_running_subscribes_on_wire(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")

    async def on_message(message: Message) -> None:
        return None

    run_task = provider.run()
    await wait_for_running(provider)

    await provider.subscribe("home/device/cmd", on_message)
    assert FakeClient.instances[-1].subscribed == ["home/device/cmd"]

    await provider.stop()
    await run_task


async def test_dispatch_delivers_message_to_callback(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    received: list[Message] = []
    delivered = asyncio.Event()

    async def on_message(message: Message) -> None:
        received.append(message)
        delivered.set()

    await provider.subscribe("home/device/cmd", on_message)
    run_task = provider.run()
    await wait_for_running(provider)

    await FakeClient.instances[-1].inbox.put(
        FakeMessage(topic="home/device/cmd", payload=b"toggle")
    )
    await asyncio.wait_for(delivered.wait(), timeout=1)

    assert received == [Message(topic="home/device/cmd", payload=b"toggle")]
    assert provider.is_running is True

    await provider.stop()
    await run_task
    assert FakeClient.instances[-1].exited


async def test_dispatch_normalizes_str_and_none_payloads(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    received: list[Message] = []

    async def on_message(message: Message) -> None:
        received.append(message)

    await provider.subscribe("home/device/cmd", on_message)
    run_task = provider.run()
    await wait_for_running(provider)
    client = FakeClient.instances[-1]

    await client.inbox.put(FakeMessage(topic="home/device/cmd", payload="text"))
    await client.inbox.put(FakeMessage(topic="home/device/cmd", payload=None))
    for _ in range(100):
        if len(received) == 2:
            break
        await asyncio.sleep(0.01)
    assert received == [
        Message(topic="home/device/cmd", payload=b"text"),
        Message(topic="home/device/cmd", payload=b""),
    ]

    await provider.stop()
    await run_task


async def test_multiple_callbacks_for_same_topic(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    first: list[Message] = []
    second: list[Message] = []

    async def callback_a(message: Message) -> None:
        first.append(message)

    async def callback_b(message: Message) -> None:
        second.append(message)

    await provider.subscribe("home/device/cmd", callback_a)
    await provider.subscribe("home/device/cmd", callback_b)
    run_task = provider.run()
    await wait_for_running(provider)
    client = FakeClient.instances[-1]

    await client.inbox.put(FakeMessage(topic="home/device/cmd", payload=b"x"))
    for _ in range(100):
        if first and second:
            break
        await asyncio.sleep(0.01)
    assert first == [Message(topic="home/device/cmd", payload=b"x")]
    assert second == [Message(topic="home/device/cmd", payload=b"x")]
    assert client.subscribed == ["home/device/cmd"]  # subscribed only once on the wire

    await provider.stop()
    await run_task


async def test_stop_drains_in_flight_callback(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    finished = asyncio.Event()

    async def slow_callback(message: Message) -> None:
        await asyncio.sleep(0.05)
        finished.set()

    await provider.subscribe("home/device/cmd", slow_callback)
    run_task = provider.run()
    await wait_for_running(provider)
    client = FakeClient.instances[-1]

    await client.inbox.put(FakeMessage(topic="home/device/cmd", payload=b"slow"))
    await asyncio.sleep(0)  # let the pump pick the message up
    await provider.stop()
    await run_task

    assert finished.is_set()  # callback completed before run() returned
    assert client.exited


async def test_stop_when_not_running_is_noop(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")

    await provider.stop()

    assert FakeClient.instances == []


async def test_run_raises_when_already_running(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    run_task = provider.run()
    await wait_for_running(provider)

    with pytest.raises(RuntimeError, match="already running"):
        provider.run()

    await provider.stop()
    await run_task


async def test_run_returns_task_without_awaiting(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")

    run_task = provider.run()

    # run() schedules the message loop and returns immediately.
    assert isinstance(run_task, asyncio.Task)
    assert not run_task.done()
    await wait_for_running(provider)
    assert provider.is_running is True

    await provider.stop()
    await run_task
    assert provider.is_running is False
    assert FakeClient.instances[-1].exited


async def test_stop_emits_stopped_event_and_awaits_pending_tasks(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")
    finished = asyncio.Event()

    async def slow_callback(message: Message) -> None:
        await asyncio.sleep(0.05)
        finished.set()

    await provider.subscribe("home/device/cmd", slow_callback)
    run_task = provider.run()
    await wait_for_running(provider)
    client = FakeClient.instances[-1]

    await client.inbox.put(FakeMessage(topic="home/device/cmd", payload=b"slow"))
    await asyncio.sleep(0)  # let the pump pick the message up
    await provider.stop()

    assert finished.is_set()  # in-flight callback was awaited by stop()
    assert provider._stopped_event.is_set()
    assert provider.is_running is False
    await run_task
    assert client.exited


async def test_async_with_starts_and_stops_provider(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")

    async with provider:
        assert provider.is_running is True
        await wait_for_running(provider)
        assert provider._run_task is not None
        assert FakeClient.instances[-1].entered

    assert provider.is_running is False
    assert provider._run_task is None
    assert provider._stopped_event.is_set()
    assert FakeClient.instances[-1].exited


async def test_async_with_stops_provider_on_exception(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(hostname="localhost")

    with pytest.raises(RuntimeError, match="boom"):
        async with provider:
            await wait_for_running(provider)
            raise RuntimeError("boom")

    assert provider.is_running is False
    assert FakeClient.instances[-1].exited


async def test_publish_cancelled_during_connect_uses_public_api_only(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    """A publish cancelled mid-connect exits through aiomqtt's public API only.

    aiomqtt runs the TCP connect in an executor thread that cannot be
    cancelled. Python 3.14's asyncio delivers CancelledError to the task
    awaiting ``run_in_executor`` IMMEDIATELY, while the thread keeps running,
    so the provider's ``finally`` block runs aiomqtt's ``__aexit__`` *before*
    the connect has completed. The provider's contract is therefore:

    * ``__aexit__`` still runs (the graceful no-connection path);
    * no aiomqtt/paho internals are ever touched (``_misc_task``,
      ``_reset_sockets``, …).

    The residual race — the executor thread finishes the connect only *after*
    ``__aexit__`` ran, orphaning a socket and aiomqtt's background misc task —
    is a documented aiomqtt/paho/CPython limitation: a shielded design that
    reaches into internals leaks identically (proven by
    ``experiments/midconnect_race_truth.py``). This test pins the true
    behaviour so it cannot be "fixed" back into a false premise.
    """
    FakeClient.connect_delay = 0.05
    FakeClient.simulate_socket = True
    try:
        provider = AioMqttProvider(hostname="localhost")

        publish_task = asyncio.create_task(provider.publish("home/device/state", b"on"))
        await asyncio.sleep(0)  # let the task construct the client
        client = FakeClient.instances[-1]
        # Wait until the executor thread has started the blocking connect, so
        # the cancellation lands while the connect is genuinely in flight.
        await asyncio.wait_for(client.connect_started.wait(), timeout=5)
        publish_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await publish_task
        assert client.entered
        assert client.exited  # __aexit__ ran despite the cancellation
        # Cancellation is delivered immediately, so the connect had NOT
        # completed when __aexit__ ran — the paho client does not exist yet.
        assert client._client is None

        # Drain the executor: the thread still finishes the connect, creating
        # the socket and scheduling aiomqtt's background misc task AFTER the
        # provider already exited. This residual is the documented upstream
        # limitation, not a provider leak.
        loop = asyncio.get_running_loop()
        await loop.shutdown_default_executor()
        assert client._client is not None
        assert client._client._sock is not None  # socket was orphaned
        misc_task = client._misc_task
        assert misc_task is not None and not misc_task.done()  # task orphaned
        # …and the provider never reached for paho's _reset_sockets.
        assert client._client.reset_count == 0

        # Test-only cleanup: reclaim the orphaned resources so the shared test
        # loop stays clean. The provider itself must never do this.
        misc_task.cancel()
        await asyncio.gather(misc_task, return_exceptions=True)
        client._client._sock.close()
        client._client._sock = None
    finally:
        FakeClient.connect_delay = 0.0
        FakeClient.simulate_socket = False


async def test_construct_raises_without_aiomqtt() -> None:
    with (
        patch.object(
            aio_provider_module,
            "_load_aiomqtt",
            side_effect=ImportError("no aiomqtt installed"),
        ),
        pytest.raises(ImportError, match="mqtt"),
    ):
        AioMqttProvider(hostname="localhost")
