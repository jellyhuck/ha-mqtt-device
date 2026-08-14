"""Example: an MQTT valve."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Valve

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    valve = Valve(unique_id="water_valve", name="Water valve", payload_stop="STOP")
    device = Device(
        provider,
        DeviceInfo(device_id="valve_example", name="Example valve"),
        entities=[valve],
    )

    async def on_command(event: Event) -> None:
        logger.info("Valve command %r -> %s", event.message, event.state)
        if event.state == "open":
            await valve.set_state("open")
        elif event.state == "closed":
            await valve.set_state("closed")

    async with provider:
        async with device:
            await valve.on_event(on_command)
            await valve.set_state("closed")
            await valve.open()
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
