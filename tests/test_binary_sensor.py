"""Behavioral tests for the legacy Backup Agents healthy binary sensor."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "binary_sensor.py"

custom_components_module = types.ModuleType("custom_components")
custom_components_module.__path__ = [str(ROOT / "custom_components")]
package_module = types.ModuleType("custom_components.backup_manager_actions")
package_module.__path__ = [
    str(ROOT / "custom_components" / "backup_manager_actions")
]
sys.modules.setdefault("custom_components", custom_components_module)
sys.modules.setdefault("custom_components.backup_manager_actions", package_module)

coordinator_module = types.ModuleType(
    "custom_components.backup_manager_actions.coordinator"
)


class BackupManagerActionsCoordinator:
    """Minimal coordinator stub."""

    def __init__(self, data=None) -> None:
        self.data = data


coordinator_module.BackupManagerActionsCoordinator = BackupManagerActionsCoordinator
sys.modules[
    "custom_components.backup_manager_actions.coordinator"
] = coordinator_module

homeassistant_module = types.ModuleType("homeassistant")
components_module = types.ModuleType("homeassistant.components")
binary_sensor_module = types.ModuleType("homeassistant.components.binary_sensor")


class BinarySensorEntity:
    """Binary sensor entity stub."""


binary_sensor_module.BinarySensorEntity = BinarySensorEntity

config_entries_module = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:
    """Config-entry stub."""

    def __init__(self, entry_id: str, runtime_data=None) -> None:
        self.entry_id = entry_id
        self.runtime_data = runtime_data


config_entries_module.ConfigEntry = ConfigEntry

core_module = types.ModuleType("homeassistant.core")
core_module.HomeAssistant = object

entity_platform_module = types.ModuleType("homeassistant.helpers.entity_platform")
entity_platform_module.AddConfigEntryEntitiesCallback = object

update_module = types.ModuleType("homeassistant.helpers.update_coordinator")


class CoordinatorEntity:
    """Coordinator entity stub."""

    @classmethod
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


update_module.CoordinatorEntity = CoordinatorEntity
helpers_module = types.ModuleType("homeassistant.helpers")

sys.modules.setdefault("homeassistant", homeassistant_module)
sys.modules.setdefault("homeassistant.components", components_module)
sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_module
sys.modules["homeassistant.config_entries"] = config_entries_module
sys.modules["homeassistant.core"] = core_module
sys.modules.setdefault("homeassistant.helpers", helpers_module)
sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module
sys.modules["homeassistant.helpers.update_coordinator"] = update_module

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.binary_sensor",
    MODULE,
)
binary_sensor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = binary_sensor
spec.loader.exec_module(binary_sensor)


def build(data=None):
    """Build the binary sensor against one coordinator."""
    coordinator = BackupManagerActionsCoordinator(data)
    entry = ConfigEntry("entry123", coordinator)
    return binary_sensor.BackupAgentsHealthyBinarySensor(coordinator, entry)


def test_legacy_unique_id_is_preserved() -> None:
    """Keep the 1.0.x registry identity unchanged."""
    item = build({"agent_count": 1, "agent_errors": {}})
    assert item._attr_unique_id == "entry123_backup_agents_healthy"


def test_health_semantics() -> None:
    """Health is true only when at least one agent exists and none errored."""
    assert build({"agent_count": 2, "agent_errors": {}}).is_on is True
    assert (
        build(
            {
                "agent_count": 2,
                "agent_errors": {"cloud": "offline"},
            }
        ).is_on
        is False
    )
    assert build({"agent_count": 0, "agent_errors": {}}).is_on is False
    assert build(None).is_on is None


def test_error_attributes() -> None:
    """Expose current provider errors for diagnostics."""
    item = build(
        {
            "agent_count": 2,
            "agent_errors": {"cloud": "offline"},
        }
    )
    assert item.extra_state_attributes == {
        "agent_errors": {"cloud": "offline"}
    }
    assert build(None).extra_state_attributes == {}


async def test_setup_registers_binary_sensor() -> None:
    """Register exactly the existing health entity."""
    coordinator = BackupManagerActionsCoordinator(
        {"agent_count": 1, "agent_errors": {}}
    )
    entry = ConfigEntry("entry123", coordinator)
    added = []

    def add_entities(entities):
        added.extend(entities)

    await binary_sensor.async_setup_entry(object(), entry, add_entities)

    assert len(added) == 1
    assert type(added[0]).__name__ == "BackupAgentsHealthyBinarySensor"
    assert added[0]._attr_unique_id == "entry123_backup_agents_healthy"


async def main() -> None:
    test_legacy_unique_id_is_preserved()
    test_health_semantics()
    test_error_attributes()
    await test_setup_registers_binary_sensor()
    print("binary sensor simulation: OK")


if __name__ == "__main__":
    asyncio.run(main())
