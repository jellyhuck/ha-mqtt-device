"""Tests for AioMqttProvider using a fake aiomqtt client — no broker needed."""

from __future__ import annotations

import asyncio
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


class FakeClient:
    """Fake aiomqtt.Client implementing the subset of the API used here."""

    instances: ClassVar[list[FakeClient]] = []

    def __init__(self, **config: Any) -> None:
        self.config = config
        self.subscribed: list[str] = []
        self.published: list[tuple[str, str | bytes]] = []
        self.inbox: asyncio.Queue[FakeMessage | None] = asyncio.Queue()
        self.entered = False
        self.exited = False
        FakeClient.instances.append(self)

    async def __aenter__(self) -> Self:
        self.entered = True
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.exited = True
        self.inbox.put_nowait(None)  # unblock the pump if it is still running

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
    provider = AioMqttProvider(host="localhost", port=1883)

    await provider.publish("home/device/state", b"on")

    client = FakeClient.instances[-1]
    assert client.entered
    assert client.exited
    assert client.published == [("home/device/state", b"on")]
    assert client.config == {"host": "localhost", "port": 1883}
    assert provider.is_running is False


async def test_publish_accepts_str_payload(fake_aiomqtt: types.SimpleNamespace) -> None:
    provider = AioMqttProvider(host="localhost")

    await provider.publish("home/device/state", "on")

    assert FakeClient.instances[-1].published == [("home/device/state", "on")]


async def test_subscribe_before_run_registers_callback(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(host="localhost")
    received: list[Message] = []

    async def on_message(message: Message) -> None:
        received.append(message)

    await provider.subscribe("home/device/cmd", on_message)

    assert provider._callbacks["home/device/cmd"] == [on_message]
    assert FakeClient.instances == []  # no connection opened yet

    run_task = asyncio.create_task(provider.run())
    await wait_for_running(provider)
    client = FakeClient.instances[-1]
    assert client.subscribed == ["home/device/cmd"]

    await provider.stop()
    await run_task


async def test_subscribe_while_running_subscribes_on_wire(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(host="localhost")

    async def on_message(message: Message) -> None:
        return None

    run_task = asyncio.create_task(provider.run())
    await wait_for_running(provider)

    await provider.subscribe("home/device/cmd", on_message)
    assert FakeClient.instances[-1].subscribed == ["home/device/cmd"]

    await provider.stop()
    await run_task


async def test_dispatch_delivers_message_to_callback(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(host="localhost")
    received: list[Message] = []
    delivered = asyncio.Event()

    async def on_message(message: Message) -> None:
        received.append(message)
        delivered.set()

    await provider.subscribe("home/device/cmd", on_message)
    run_task = asyncio.create_task(provider.run())
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
    provider = AioMqttProvider(host="localhost")
    received: list[Message] = []

    async def on_message(message: Message) -> None:
        received.append(message)

    await provider.subscribe("home/device/cmd", on_message)
    run_task = asyncio.create_task(provider.run())
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
    provider = AioMqttProvider(host="localhost")
    first: list[Message] = []
    second: list[Message] = []

    async def callback_a(message: Message) -> None:
        first.append(message)

    async def callback_b(message: Message) -> None:
        second.append(message)

    await provider.subscribe("home/device/cmd", callback_a)
    await provider.subscribe("home/device/cmd", callback_b)
    run_task = asyncio.create_task(provider.run())
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
    provider = AioMqttProvider(host="localhost")
    finished = asyncio.Event()

    async def slow_callback(message: Message) -> None:
        await asyncio.sleep(0.05)
        finished.set()

    await provider.subscribe("home/device/cmd", slow_callback)
    run_task = asyncio.create_task(provider.run())
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
    provider = AioMqttProvider(host="localhost")

    await provider.stop()

    assert FakeClient.instances == []


async def test_run_raises_when_already_running(
    fake_aiomqtt: types.SimpleNamespace,
) -> None:
    provider = AioMqttProvider(host="localhost")
    run_task = asyncio.create_task(provider.run())
    await wait_for_running(provider)

    with pytest.raises(RuntimeError, match="already running"):
        await provider.run()

    await provider.stop()
    await run_task


async def test_construct_raises_without_aiomqtt() -> None:
    with (
        patch.object(
            aio_provider_module,
            "_load_aiomqtt",
            side_effect=ImportError("no aiomqtt installed"),
        ),
        pytest.raises(ImportError, match="mqtt"),
    ):
        AioMqttProvider(host="localhost")
