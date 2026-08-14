"""Example: an MQTT lock."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Lock

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
