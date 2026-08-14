"""Example: an MQTT time entity."""

from __future__ import annotations

import asyncio
import logging
from datetime import time

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Time

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="time_example", name="Example time device")
    alarm = Time(unique_id="alarm", name="Alarm time")
    device = Device(provider, info, entities=[alarm])

    async def on_time_command(event: Event) -> None:
        logger.info("Time command %r -> %s", event.message, event.state)
        if isinstance(event.state, str):
            await alarm.set_state(event.state)

    async with provider:
        async with device:
            await alarm.on_event(on_time_command)
            await alarm.set_state(time(7, 30))
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
