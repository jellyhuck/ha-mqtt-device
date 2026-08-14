"""Example: an MQTT water heater."""

from __future__ import annotations

import asyncio
import logging

from ha_mqtt_device import AioMqttProvider, Device, DeviceInfo, Event, WaterHeater

logger = logging.getLogger(__name__)


async def main() -> None:
    provider = AioMqttProvider(hostname="localhost", port=1883, logger=logger)
    heater = WaterHeater(
        unique_id="boiler",
        name="Boiler",
        modes=["off", "eco", "electric"],
        temperature_unit="C",
        min_temp=43.3,
        max_temp=60,
        power_enabled=True,
    )
    device = Device(
        provider,
        DeviceInfo(device_id="water_heater_example", name="Example water heater"),
        entities=[heater],
    )

    async def on_command(event: Event) -> None:
        logger.info("Water-heater %s command %r", event.event_type, event.message)
        if event.event_type == "mode" and isinstance(event.state, str):
            await heater.set_mode(event.state)
        elif event.event_type == "temperature" and isinstance(event.state, str):
            await heater.set_target_temperature(float(event.state))

    async with provider:
        async with device:
            await heater.on_event(on_command)
            await heater.set_current_temperature(52.5)
            await heater.set_target_temperature(55)
            await heater.set_mode("eco")
        await device.remove()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
