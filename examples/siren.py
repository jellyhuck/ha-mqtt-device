"""Example: an MQTT siren."""

from __future__ import annotations

import asyncio
import logging

import typer

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Siren

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883
# Usage: uv run examples/siren.py --host=... --port=... --username=... --password=...


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
    info = DeviceInfo(device_id="siren_example", name="Example siren")
    siren = Siren(
        unique_id="alarm_siren",
        name="Alarm siren",
        available_tones=["bell", "siren"],
    )
    device = Device(provider, info, entities=[siren])

    async def on_siren_command(event: Event) -> None:
        logger.info("Siren command %r -> %s", event.message, event.state)
        if isinstance(event.state, dict):
            state = event.state.get("state")
            if state == "ON":
                await siren.set_state(
                    True,
                    tone=event.state.get("tone"),
                    duration=event.state.get("duration"),
                    volume_level=event.state.get("volume_level"),
                )
            elif state == "OFF":
                await siren.set_state(False)

    async with provider:
        async with device:
            await siren.on_event(on_siren_command)
            await siren.set_state(True, tone="bell", duration=10, volume_level=0.5)
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
