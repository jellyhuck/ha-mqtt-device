"""Thin library for Home Assistant devices discoverable via MQTT device discovery."""

from __future__ import annotations

from ha_mqtt_device.aio_provider import AioMqttProvider
from ha_mqtt_device.provider import Message, MqttMessageCallback, MqttProvider

__all__ = ["AioMqttProvider", "Message", "MqttMessageCallback", "MqttProvider"]


def main() -> None:
    print("Hello from ha-mqtt-device!")
