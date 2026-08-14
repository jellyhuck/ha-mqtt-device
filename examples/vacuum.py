"""Example: an MQTT vacuum entity."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Vacuum

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="vacuum_example", name="Example vacuum")
    vacuum = Vacuum(
        unique_id="cleaner",
        name="Cleaner",
        supported_features=[
            "start",
            "pause",
            "stop",
            "return_home",
            "status",
            "fan_speed",
            "send_command",
        ],
        fan_speed_list=["min", "medium", "max"],
        send_command_enabled=True,
    )
    device = Device(provider, info, entities=[vacuum])

    async def on_command(event: Event) -> None:
        logger.info("Vacuum command %r -> %s", event.message, event.state)

    async with provider:
        async with device:
            await vacuum.on_event(on_command)
            await vacuum.set_state("docked", fan_speed="min")
            await vacuum.start()
            await asyncio.sleep(30)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
