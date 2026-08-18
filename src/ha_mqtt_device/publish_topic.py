"""Internal MQTT publish-topic descriptors."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PublishTopic"]


@dataclass(frozen=True, slots=True)
class PublishTopic:
    """A resolved MQTT topic and the retention policy for its publications."""

    topic: str
    retain: bool = False
