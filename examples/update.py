"""Example: an MQTT firmware update entity."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Update

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="update_example", name="Example update device")
    update = Update(
        unique_id="firmware",
        name="Firmware update",
        title="Example device firmware",
        device_class="firmware",
        release_url="https://example.com/releases",
        latest_version_enabled=True,
    )
    device = Device(provider, info, entities=[update])

    async def on_install(event: Event) -> None:
        logger.info("Update command %r -> %s", event.message, event.state)
        if event.state == "install":
            # Start the update in hardware, then report progress via set_state.
            await update.set_state("1.21.0", latest_version="1.22.0", in_progress=True)

    async with provider:
        async with device:
            await update.on_event(on_install)
            await update.set_state("1.21.0", latest_version="1.22.0")
            await asyncio.sleep(30)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
