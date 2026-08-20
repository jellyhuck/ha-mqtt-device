"""Example: standalone typed values published directly through MQTT."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from enum import StrEnum

import typer

from ha_mqtt_device import (
    AioMqttProvider,
    DateTimeValue,
    DateValue,
    StrEnumValue,
    StrValue,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1883


class Status(StrEnum):
    READY = "ready"


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

    async def update_status(payload: str | bytes) -> None:
        await provider.publish("home/example/status", payload, retain=True)

    async def update_enum_status(payload: str | bytes) -> None:
        await provider.publish("home/example/status_enum", payload, retain=True)

    async def update_target_date(payload: str | bytes) -> None:
        await provider.publish("home/example/date", payload, retain=True)

    async def update_alarm(payload: str | bytes) -> None:
        await provider.publish("home/example/alarm", payload, retain=True)

    status = StrValue()
    enum_status = StrEnumValue[Status]()
    target_date = DateValue()
    alarm = DateTimeValue()

    async with provider:
        logger.info("Initial status: %r", status.value)
        await status.set_value("ready", update_status)
        await status.set_value("ready", update_status)  # unchanged: no update
        await status.set_value("ready", update_status, force_update=True)
        await enum_status.set_value(Status.READY, update_enum_status)
        await target_date.set_value(date(2024, 2, 14), update_target_date)
        await alarm.set_value(datetime(2024, 2, 14, 10, 30, tzinfo=UTC), update_alarm)


def run_cli(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Run the example with MQTT settings supplied by Typer."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(host=host, port=port, username=username, password=password))


if __name__ == "__main__":
    typer.run(run_cli)
