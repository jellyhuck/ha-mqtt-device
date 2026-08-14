"""Example: an MQTT alarm control panel."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import (
    AioMqttProvider,
    AlarmControlPanel,
    Device,
    DeviceInfo,
    Event,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(host="localhost", port=1883, logger=logger)
    info = DeviceInfo(device_id="alarm_example", name="Example alarm")
    alarm = AlarmControlPanel(unique_id="alarm", name="Alarm")
    device = Device(provider, info, entities=[alarm])

    async def on_alarm_command(event: Event) -> None:
        logger.info("Alarm command %r -> %s", event.message, event.state)
        # Send the command to the alarm hardware, then report its state.
        if isinstance(event.state, str):
            await alarm.set_state(event.state)

    async with provider:
        async with device:
            await alarm.on_event(on_alarm_command)
            await asyncio.sleep(30)
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
