"""Shared recording MQTT provider fake for entity and device tests."""

from __future__ import annotations

from ha_mqtt_device.provider import Message, MqttMessageCallback


class RecordingProvider:
    """Structural MQTT provider that records publishes and subscriptions."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str | bytes, bool]] = []
        self.subscriptions: dict[str, list[MqttMessageCallback]] = {}

    async def publish(
        self, topic: str, message: str | bytes, retain: bool = False
    ) -> None:
        self.published.append((topic, message, retain))

    async def subscribe(self, topic: str, callback: MqttMessageCallback) -> None:
        self.subscriptions.setdefault(topic, []).append(callback)

    async def run(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def deliver(self, topic: str, payload: str | bytes) -> None:
        """Invoke every callback registered for ``topic`` with ``payload``."""
        raw = payload.encode() if isinstance(payload, str) else payload
        for callback in self.subscriptions.get(topic, []):
            await callback(Message(topic=topic, payload=raw))
