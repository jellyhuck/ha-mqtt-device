"""Example: an MQTT lock."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Lock

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/lock.py --host=... --port=... --username=... --password=...


async def main(
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> None:
    provider = AioMqttProvider(
        hostname=host,
        port=port,
        username=username,
        password=password,
        logger=logger,
    )
    info = DeviceInfo(device_id="lock_example", name="Example lock")
    lock = Lock(unique_id="front_door_lock", name="Front door")
    device = Device(provider, info, entities=[lock])

    async def on_lock_command(event: Event) -> None:
        logger.info("Lock command %r -> %s", event.message, event.state)
        if event.state == "lock":
            # Command the hardware, then publish its confirmed state.
            await lock.set_state("locked")
        elif event.state in {"unlock", "open"}:
            await lock.set_state("unlocked")

    async with provider:
        async with device:
            await lock.on_event(on_lock_command)
        await device.remove()


def run_cli(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Run the example with MQTT settings supplied by Typer."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main(host=host, port=port, username=username, password=password))
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Interrupted")


if __name__ == "__main__":
    typer.run(run_cli)
