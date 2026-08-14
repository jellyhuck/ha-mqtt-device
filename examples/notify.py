"""Example: an MQTT notification service."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, Notify

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="notify_example", name="Example notifier")
    notifier = Notify(unique_id="notifications", name="Notifications")
    device = Device(provider, info, entities=[notifier])

    async def on_notification(event: Event) -> None:
        # The message remains in event.message; JSON object payloads are also
        # available as a dictionary in event.state.
        logger.info("Notification received: %r", event.message)

    async with provider:
        async with device:
            await notifier.on_event(on_notification)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
