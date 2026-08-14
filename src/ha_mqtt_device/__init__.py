"""Thin library for Home Assistant devices discoverable via MQTT device discovery."""

from __future__ import annotations

from ha_mqtt_device.aio_provider import AioMqttProvider
from ha_mqtt_device.alarm_control_panel import AlarmControlPanel
from ha_mqtt_device.binary_sensor import BinarySensor
from ha_mqtt_device.button import Button
from ha_mqtt_device.camera import Camera
from ha_mqtt_device.climate import Climate
from ha_mqtt_device.cover import Cover
from ha_mqtt_device.date import Date
from ha_mqtt_device.date_time import DateTime
from ha_mqtt_device.device import Device
from ha_mqtt_device.device_info import DeviceInfo
from ha_mqtt_device.device_tracker import DeviceTracker
from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.event_entity import EventEntity
from ha_mqtt_device.fan import Fan
from ha_mqtt_device.humidifier import Humidifier
from ha_mqtt_device.image import Image
from ha_mqtt_device.infrared import InfraredEmitter, InfraredReceiver
from ha_mqtt_device.lawn_mower import LawnMower
from ha_mqtt_device.light import Light
from ha_mqtt_device.lock import Lock
from ha_mqtt_device.notify import Notify
from ha_mqtt_device.number import Number
from ha_mqtt_device.provider import Message, MqttMessageCallback, MqttProvider
from ha_mqtt_device.scene import Scene
from ha_mqtt_device.select_entity import SelectEntity
from ha_mqtt_device.sensor import Sensor
from ha_mqtt_device.siren import Siren
from ha_mqtt_device.switch import Switch
from ha_mqtt_device.tag_scanner import TagScanner
from ha_mqtt_device.text import Text
from ha_mqtt_device.time import Time
from ha_mqtt_device.update import Update
from ha_mqtt_device.vacuum import Vacuum
from ha_mqtt_device.valve import Valve
from ha_mqtt_device.water_heater import WaterHeater

__all__ = [
    "AioMqttProvider",
    "AlarmControlPanel",
    "BinarySensor",
    "Button",
    "Camera",
    "Climate",
    "Cover",
    "Date",
    "DateTime",
    "Device",
    "DeviceInfo",
    "DeviceTracker",
    "Entity",
    "Event",
    "EventCallback",
    "EventEntity",
    "Fan",
    "Humidifier",
    "Image",
    "InfraredEmitter",
    "InfraredReceiver",
    "LawnMower",
    "Light",
    "Lock",
    "Message",
    "MqttMessageCallback",
    "MqttProvider",
    "Notify",
    "Number",
    "Scene",
    "SelectEntity",
    "Sensor",
    "Siren",
    "Switch",
    "TagScanner",
    "Text",
    "Time",
    "Update",
    "Vacuum",
    "Valve",
    "WaterHeater",
]


def main() -> None:
    print("Hello from ha-mqtt-device!")
