"""Example: an MQTT text entity."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Text

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="text_example", name="Example text device")
    text = Text(
        unique_id="message",
        name="Message",
        max_length=100,
        pattern=r"[A-Za-z0-9 ]*",
    )
    device = Device(provider, info, entities=[text])

    async def on_text_command(event: Event) -> None:
        logger.info("Text command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            # Apply the command to hardware and publish the resulting state.
            await text.set_state(event.state)

    async with provider:
        async with device:
            await text.on_event(on_text_command)
            await text.set_state("Ready")
            await asyncio.sleep(30)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
