"""Example: an MQTT tag scanner."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, TagScanner

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="tag_reader", name="Example tag reader")
    scanner = TagScanner(
        unique_id="reader",
        topic="~/tag_scanned",
        value_template="{{ value_json.uid }}",
    )
    device = Device(provider, info, entities=[scanner])

    async def on_scan(event: Event) -> None:
        logger.info("Tag scan %r -> %s", event.message, event.state)

    async with provider:
        async with device:
            await scanner.on_event(on_scan)
            # Hardware integrations normally call this when their reader scans.
            await scanner.scan("E9F35959")
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
