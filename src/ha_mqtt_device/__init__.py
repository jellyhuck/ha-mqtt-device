"""Thin library for Home Assistant devices discoverable via MQTT device discovery."""

from __future__ import annotations

from ha_mqtt_device.aio_provider import AioMqttProvider
from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.button import Button
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message, MqttMessageCallback, MqttProvider
from ha_mqtt_device.switch import Switch

__all__ = [
    "AioMqttProvider",
    "BinarySensor",
    "Button",
    "Device",
    "DeviceInfo",
    "Entity",
    "Event",
    "EventCallback",
    "Message",
    "MqttMessageCallback",
    "MqttProvider",
    "Switch",
]


def main() -> None:
    print("Hello from ha-mqtt-device!")
