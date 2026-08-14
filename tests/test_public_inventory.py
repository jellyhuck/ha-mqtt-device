"""Public API, examples, and documentation inventory checks."""

from __future__ import annotations

import re
from pathlib import Path

import ha_mqtt_device

ROOT = Path(__file__).parents[1]
IN_SCOPE = {
    "AlarmControlPanel": ("alarm_control_panel.py", "Alarm control panel"),
    "Lock": ("lock.py", "Lock"),
    "Notify": ("notify.py", "Notify"),
    "Scene": ("scene.py", "Scene"),
    "SelectEntity": ("select_entity.py", "Select"),
    "Siren": ("siren.py", "Siren"),
    "TagScanner": ("tag_scanner.py", "Tag scanner"),
    "Text": ("text.py", "Text"),
    "Time": ("mqtt_time.py", "Time"),
    "Update": ("update.py", "Update"),
    "Vacuum": ("vacuum.py", "Vacuum"),
    "Valve": ("valve.py", "Valve"),
    "WaterHeater": ("water_heater.py", "Water heater"),
}


def test_sprint_platforms_have_one_public_export_example_and_section() -> None:
    docs = (ROOT / "EXAMPLES.md").read_text()
    exports = ha_mqtt_device.__all__

    for class_name, (example_name, heading) in IN_SCOPE.items():
        assert getattr(ha_mqtt_device, class_name).__name__ == class_name
        assert exports.count(class_name) == 1

        example = (ROOT / "examples" / example_name).read_text()
        assert f"{class_name}" in example
        assert re.search(r"from ha_mqtt_device import", example)

        assert len(re.findall(rf"^### {re.escape(heading)}$", docs, re.MULTILINE)) == 1


def test_documentation_has_no_stale_platform_todos_and_excludes_device_trigger() -> (
    None
):
    docs = (ROOT / "EXAMPLES.md").read_text()

    assert "not yet supported" not in docs
    assert "TODO" not in docs
    assert "Device Trigger" in docs
    assert "intentionally excluded" in docs
    assert "EventEntity" in docs
