"""Update entity for Home Assistant MQTT device discovery."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ha_mqtt_device.entity import Entity
from ha_mqtt_device.event import Event, EventCallback
from ha_mqtt_device.provider import Message

__all__ = ["Update"]

logger = logging.getLogger(__name__)
DEFAULT_INSTALL_PAYLOAD = "install"


@dataclass
class Update(Entity):
    """An MQTT software or firmware update entity.

    The device publishes a JSON update state on ``state_topic``. Home
    Assistant's install action is delivered on ``command_topic`` and is
    exposed through :meth:`on_event`.
    """

    component = "update"

    title: str | None = None
    device_class: str | None = None
    release_summary: str | None = None
    release_url: str | None = None
    entity_picture: str | None = None
    value_template: str | None = None
    latest_version_template: str | None = None
    payload_install: str = DEFAULT_INSTALL_PAYLOAD
    install_enabled: bool = True
    latest_version_enabled: bool = False

    _event_callbacks: list[EventCallback] = field(
        default_factory=list, init=False, repr=False
    )
    _subscribed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.payload_install:
            raise ValueError("payload_install must not be empty")
        for field_name in (
            "title",
            "device_class",
            "release_summary",
            "release_url",
            "entity_picture",
            "value_template",
            "latest_version_template",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string or None")

    @property
    def command_topic(self) -> str:
        """Install command topic as ``~`` shorthand."""
        return Entity.command_topic_for(self.unique_id)

    @property
    def latest_version_topic(self) -> str:
        """Latest-version topic as ``~`` shorthand."""
        return Entity.state_topic_for(self.unique_id, "latest")

    async def set_state(
        self,
        installed_version: str,
        *,
        latest_version: str | None = None,
        title: str | None = None,
        release_summary: str | None = None,
        release_url: str | None = None,
        entity_picture: str | None = None,
        in_progress: bool | None = None,
        update_percentage: float | None = None,
    ) -> None:
        """Publish a documented JSON update state payload."""
        payload: dict[str, object] = {"installed_version": installed_version}
        optional: dict[str, object] = {
            "latest_version": latest_version,
            "title": title,
            "release_summary": release_summary,
            "release_url": release_url,
            "entity_picture": entity_picture,
            "in_progress": in_progress,
            "update_percentage": update_percentage,
        }
        payload.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        self._validate_state(payload)
        await self.publish_state(payload)

    async def publish_state(self, state: Mapping[str, object]) -> None:
        """Publish a validated JSON state mapping on the state topic."""
        payload = self._validated_state(state)
        await self._publish(
            self._register_publish_topic(self.state_topic, retain=True),
            json.dumps(payload),
        )

    async def set_latest_version(self, version: str) -> None:
        """Publish a simple latest-version update when that topic is enabled."""
        self._require_device()
        if not self.latest_version_enabled:
            raise ValueError("latest version topic is disabled")
        self._validate_string("latest_version", version)
        await self._publish(
            self._register_publish_topic(self.latest_version_topic, retain=True),
            version,
        )

    async def install(self) -> None:
        """Publish the configured install action payload."""
        self._require_device()
        if not self.install_enabled:
            raise ValueError("install command is disabled")
        await self._publish(
            self._register_publish_topic(self.command_topic, retain=False),
            self.payload_install,
        )

    async def on_event(self, callback: EventCallback) -> None:
        """Register a callback for install commands from Home Assistant."""
        device = self._require_device()
        if not self.install_enabled:
            raise ValueError("install command is disabled")
        if not self._subscribed:
            await device.provider.subscribe(
                device.info.resolve_topic(self.command_topic), self._dispatch
            )
            self._subscribed = True
        self._event_callbacks.append(callback)

    async def _dispatch(self, message: Message) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        state = "install" if payload == self.payload_install else None
        event = Event(
            timestamp=datetime.now(UTC),
            event_type="command",
            topic=message.topic,
            topic_type="command_topic",
            message=payload,
            state=state,
        )
        for callback in tuple(self._event_callbacks):
            try:
                await callback(event)
            except Exception:
                logger.exception(
                    "event callback failed for %s %r on topic %r",
                    type(self).__name__,
                    self.unique_id,
                    message.topic,
                )

    @classmethod
    def _validated_state(cls, state: Mapping[str, object]) -> dict[str, object]:
        if not isinstance(state, Mapping):
            raise TypeError("update state must be a mapping")
        payload = dict(state)
        if "installed_version" not in payload:
            raise ValueError("update state requires installed_version")
        unknown = set(payload) - {
            "installed_version",
            "latest_version",
            "title",
            "release_summary",
            "release_url",
            "entity_picture",
            "in_progress",
            "update_percentage",
        }
        if unknown:
            raise ValueError(f"unsupported update state fields: {sorted(unknown)}")
        for key in (
            "installed_version",
            "latest_version",
            "title",
            "release_summary",
            "release_url",
            "entity_picture",
        ):
            if key in payload:
                cls._validate_string(key, payload[key])
        if "in_progress" in payload and not isinstance(payload["in_progress"], bool):
            raise TypeError("in_progress must be a boolean")
        if "update_percentage" in payload:
            percentage = payload["update_percentage"]
            if percentage is not None and (
                isinstance(percentage, bool)
                or not isinstance(percentage, (int, float))
                or not 0 <= percentage <= 100
            ):
                raise ValueError("update_percentage must be between 0 and 100")
        return payload

    @staticmethod
    def _validate_state(state: Mapping[str, object]) -> None:
        Update._validated_state(state)

    @staticmethod
    def _validate_string(name: str, value: object) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} must be a non-empty string")

    @property
    def state_topic(self) -> str:
        return Entity.state_topic_for(self.unique_id)

    def discovery_config(self) -> dict[str, object]:
        """Return this update entity's abbreviated discovery configuration."""
        config = super().discovery_config()
        config["stat_t"] = self.state_topic
        if self.install_enabled:
            config["cmd_t"] = self.command_topic
        if self.latest_version_enabled:
            config["l_ver_t"] = self.latest_version_topic
        if self.payload_install != DEFAULT_INSTALL_PAYLOAD:
            config["pl_inst"] = self.payload_install
        if self.title is not None:
            config["tit"] = self.title
        if self.device_class is not None:
            config["dev_cla"] = self.device_class
        if self.release_summary is not None:
            config["rel_s"] = self.release_summary
        if self.release_url is not None:
            config["rel_u"] = self.release_url
        if self.entity_picture is not None:
            config["ent_pic"] = self.entity_picture
        if self.value_template is not None:
            config["val_tpl"] = self.value_template
        if self.latest_version_template is not None:
            config["l_ver_tpl"] = self.latest_version_template
        return self._resolve_discovery_config(config)
