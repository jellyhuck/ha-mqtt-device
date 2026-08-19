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
from ha_mqtt_device.publish_topic import PublishTopic

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
    status = StrValue(PublishTopic("home/example/status", retain=True))
    enum_status = StrEnumValue[Status](
        PublishTopic("home/example/status_enum", retain=True)
    )
    target_date = DateValue(PublishTopic("home/example/date", retain=True))
    alarm = DateTimeValue(PublishTopic("home/example/alarm", retain=True))

    async with provider:
        logger.info("Initial status: %r", status.value)
        await status.set_value("ready", provider)
        await status.set_value("ready", provider)  # unchanged: no publication
        await status.set_value("ready", provider, force_publish=True)
        await enum_status.set_value(Status.READY, provider)
        await target_date.set_value(date(2024, 2, 14), provider)
        await alarm.set_value(datetime(2024, 2, 14, 10, 30, tzinfo=UTC), provider)


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
