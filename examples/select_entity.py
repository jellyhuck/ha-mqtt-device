"""Example: an MQTT select."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, SelectEntity

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="select_example", name="Example selector")
    select = SelectEntity(
        unique_id="mode",
        name="Mode",
        options=["Automatic", "Manual"],
    )
    device = Device(provider, info, entities=[select])

    async def on_selection(event: Event) -> None:
        logger.info("Selection command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            # Apply the selection to the hardware, then report it.
            await select.set_state(event.state)

    async with provider:
        async with device:
            await select.on_event(on_selection)
            await select.set_state("Automatic")
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
