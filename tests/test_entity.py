from ha_mqtt_device.entity import Entity


def test_command_topic_for_builds_base_and_nested_topics() -> None:
    assert Entity.command_topic_for("relay") == "~/relay/command"
    assert Entity.command_topic_for("relay", "power") == "~/relay/command/power"
    assert Entity.command_topic_for("relay", "") == "~/relay/command"
    assert Entity.command_topic_for("relay", None) == "~/relay/command"


def test_state_topic_for_builds_base_and_nested_topics() -> None:
    assert Entity.state_topic_for("relay") == "~/relay/state"
    assert Entity.state_topic_for("relay", "power") == "~/relay/state/power"
    assert Entity.state_topic_for("relay", "") == "~/relay/state"
    assert Entity.state_topic_for("relay", None) == "~/relay/state"
