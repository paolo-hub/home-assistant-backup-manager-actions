"""Behavioral tests for Backup Manager Actions diagnostic sensors."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "sensor.py"

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
sensor_module = types.ModuleType("homeassistant.components.sensor")


class SensorDeviceClass:
    """Sensor device-class stub."""

    DATA_SIZE = "data_size"


class SensorStateClass:
    """Sensor state-class stub."""

    MEASUREMENT = "measurement"


class SensorEntity:
    """Sensor entity stub."""


sensor_module.SensorDeviceClass = SensorDeviceClass
sensor_module.SensorStateClass = SensorStateClass
sensor_module.SensorEntity = SensorEntity

config_entries_module = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:
    """Config-entry stub."""

    def __init__(self, entry_id: str, runtime_data=None) -> None:
        self.entry_id = entry_id
        self.runtime_data = runtime_data


config_entries_module.ConfigEntry = ConfigEntry

const_module = types.ModuleType("homeassistant.const")


class UnitOfInformation:
    """Information unit stub."""

    BYTES = "B"


const_module.UnitOfInformation = UnitOfInformation

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
sys.modules["homeassistant.components.sensor"] = sensor_module
sys.modules["homeassistant.config_entries"] = config_entries_module
sys.modules["homeassistant.const"] = const_module
sys.modules["homeassistant.core"] = core_module
sys.modules.setdefault("homeassistant.helpers", helpers_module)
sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module
sys.modules["homeassistant.helpers.update_coordinator"] = update_module

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.sensor",
    MODULE,
)
sensor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = sensor
spec.loader.exec_module(sensor)


def sample_data(*, complete: bool = True) -> dict:
    """Return one realistic coordinator snapshot."""
    return {
        "agent_count": 3,
        "agents": {
            "cloud": {"name": "Google Drive", "domain": "google_drive"},
            "local": {"name": "local", "domain": "hassio"},
            "nas": {"name": "Backup", "domain": "hassio"},
        },
        "agent_errors": {} if complete else {"cloud": "provider unavailable"},
        "inventory_complete": complete,
        "backup_count": 7,
        "source_counts": {
            "bma": 2,
            "ha_native": 2,
            "app_update": 2,
            "unknown": 1,
        },
        "bma_by_job": {
            "full": 1,
            "unassigned": 1,
        },
        "ha_native_breakdown": {
            "automatic": 1,
            "manual_or_other": 1,
        },
        "app_update_by_app": {
            "addon_a": 1,
            "addon_b": 1,
        },
        "latest_backup": {
            "backup_id": "latest-id",
            "name": "Latest",
            "date": "2026-09-29T12:00:00+02:00",
            "source_type": "bma",
            "classification_reason": "bma_managed",
            "job_id": "full",
            "app_slug": None,
            "metadata_version": 1,
            "physical_size_bytes": 220,
            "physical_size_complete": True,
            "logical_size_bytes": 120,
            "logical_size_complete": True,
            "agents": {
                "local": {"size": 100, "protected": False},
                "nas": {"size": 120, "protected": False},
            },
            "extra_metadata": {
                "backup_manager_actions.managed": True,
                "backup_manager_actions.job_id": "full",
                "backup_manager_actions.metadata_version": "1",
            },
        },
        "archive_size": {
            "physical_total_bytes": 600,
            "physical_size_complete": complete,
            "logical_size_bytes": 500,
            "logical_size_complete": complete,
            "per_agent": {
                "cloud": {
                    "name": "Google Drive",
                    "domain": "google_drive",
                    "backup_count": 0,
                    "size_bytes": 0,
                    "size_complete": complete,
                },
                "local": {
                    "name": "local",
                    "domain": "hassio",
                    "backup_count": 5,
                    "size_bytes": 370,
                    "size_complete": True,
                },
                "nas": {
                    "name": "Backup",
                    "domain": "hassio",
                    "backup_count": 3,
                    "size_bytes": 230,
                    "size_complete": True,
                },
            },
            "per_source_type": {
                "bma": {
                    "backup_count": 2,
                    "physical_size_bytes": 300,
                    "physical_size_complete": complete,
                    "logical_size_bytes": 200,
                    "logical_size_complete": complete,
                },
                "ha_native": {
                    "backup_count": 2,
                    "physical_size_bytes": 150,
                    "physical_size_complete": complete,
                    "logical_size_bytes": 150,
                    "logical_size_complete": complete,
                },
                "app_update": {
                    "backup_count": 2,
                    "physical_size_bytes": 110,
                    "physical_size_complete": complete,
                    "logical_size_bytes": 110,
                    "logical_size_complete": complete,
                },
                "unknown": {
                    "backup_count": 1,
                    "physical_size_bytes": 40,
                    "physical_size_complete": complete,
                    "logical_size_bytes": 40,
                    "logical_size_complete": complete,
                },
            },
        },
    }


def build_sensors(data=None):
    """Create all sensor classes against one coordinator."""
    coordinator = BackupManagerActionsCoordinator(data)
    entry = ConfigEntry("entry123", coordinator)
    return [
        sensor.BackupAgentCountSensor(coordinator, entry),
        sensor.BackupCountSensor(coordinator, entry),
        sensor.LatestBackupSensor(coordinator, entry),
        sensor.BMABackupCountSensor(coordinator, entry),
        sensor.HANativeBackupCountSensor(coordinator, entry),
        sensor.AppUpdateBackupCountSensor(coordinator, entry),
        sensor.ArchiveSizeSensor(coordinator, entry),
    ]


def test_existing_unique_ids_are_preserved() -> None:
    """Keep the 1.0.x registry identities exactly unchanged."""
    sensors = build_sensors(sample_data())
    assert sensors[0]._attr_unique_id == "entry123_backup_agent_count"
    assert sensors[1]._attr_unique_id == "entry123_backup_count"
    assert sensors[2]._attr_unique_id == "entry123_latest_backup"


def test_new_unique_ids_are_stable() -> None:
    """Give every new diagnostic entity a deterministic registry identity."""
    sensors = build_sensors(sample_data())
    assert sensors[3]._attr_unique_id == "entry123_bma_backup_count"
    assert sensors[4]._attr_unique_id == "entry123_ha_native_backup_count"
    assert sensors[5]._attr_unique_id == "entry123_app_update_backup_count"
    assert sensors[6]._attr_unique_id == "entry123_archive_size"


def test_count_sensors_and_breakdowns() -> None:
    """Expose class counts while retaining unknowns in the total breakdown."""
    (
        _agents,
        total,
        _latest,
        bma,
        native,
        app_update,
        _archive,
    ) = build_sensors(sample_data())

    assert total.native_value == 7
    assert total.extra_state_attributes == {
        "inventory_complete": True,
        "source_counts": {
            "bma": 2,
            "ha_native": 2,
            "app_update": 2,
            "unknown": 1,
        },
    }

    assert bma.native_value == 2
    assert bma.extra_state_attributes == {
        "inventory_complete": True,
        "by_job": {
            "full": 1,
            "unassigned": 1,
        },
    }

    assert native.native_value == 2
    assert native.extra_state_attributes == {
        "inventory_complete": True,
        "automatic": 1,
        "manual_or_other": 1,
    }

    assert app_update.native_value == 2
    assert app_update.extra_state_attributes == {
        "inventory_complete": True,
        "by_app": {
            "addon_a": 1,
            "addon_b": 1,
        },
    }


def test_latest_backup_keeps_state_and_adds_normalized_metadata() -> None:
    """Keep the old state contract and expose the new normalized fields."""
    latest = build_sensors(sample_data())[2]

    assert latest.native_value == "latest-id"
    attributes = latest.extra_state_attributes
    assert attributes["source_type"] == "bma"
    assert attributes["classification_reason"] == "bma_managed"
    assert attributes["job_id"] == "full"
    assert attributes["app_slug"] is None
    assert attributes["metadata_version"] == 1
    assert attributes["physical_size_bytes"] == 220
    assert attributes["logical_size_bytes"] == 120
    assert attributes["agents"]["nas"]["size"] == 120


def test_archive_size_sensor() -> None:
    """Expose physical total as state and diagnostic dimensions as attributes."""
    archive = build_sensors(sample_data())[6]

    assert archive.native_value == 600
    assert archive._attr_device_class == "data_size"
    assert archive._attr_native_unit_of_measurement == "B"
    assert archive._attr_state_class == "measurement"

    attributes = archive.extra_state_attributes
    assert attributes["physical_total_bytes"] == 600
    assert attributes["physical_size_complete"] is True
    assert attributes["logical_size_bytes"] == 500
    assert attributes["logical_size_complete"] is True
    assert attributes["inventory_complete"] is True
    assert attributes["agent_errors"] == {}
    assert attributes["per_agent"]["local"]["size_bytes"] == 370
    assert attributes["per_agent"]["nas"]["size_bytes"] == 230
    assert attributes["per_source_type"]["bma"]["physical_size_bytes"] == 300
    assert attributes["per_source_type"]["unknown"]["backup_count"] == 1


def test_incomplete_inventory_is_explicit() -> None:
    """Never present partial archive diagnostics as complete."""
    sensors = build_sensors(sample_data(complete=False))
    total = sensors[1]
    archive = sensors[6]

    assert total.native_value == 7
    assert total.extra_state_attributes["inventory_complete"] is False

    assert archive.native_value == 600
    attributes = archive.extra_state_attributes
    assert attributes["inventory_complete"] is False
    assert attributes["physical_size_complete"] is False
    assert attributes["logical_size_complete"] is False
    assert attributes["agent_errors"] == {"cloud": "provider unavailable"}
    assert attributes["per_agent"]["cloud"]["size_complete"] is False


def test_uninitialized_sensors_are_safe() -> None:
    """Return unavailable-like values before coordinator data exists."""
    sensors = build_sensors(None)
    for item in sensors:
        assert item.native_value is None
        if hasattr(item, "extra_state_attributes"):
            assert item.extra_state_attributes == {}


async def test_setup_registers_all_sensors() -> None:
    """Register the three legacy and four new diagnostic sensors."""
    coordinator = BackupManagerActionsCoordinator(sample_data())
    entry = ConfigEntry("entry123", coordinator)
    added = []

    def add_entities(entities):
        added.extend(entities)

    await sensor.async_setup_entry(object(), entry, add_entities)

    assert [type(item).__name__ for item in added] == [
        "BackupAgentCountSensor",
        "BackupCountSensor",
        "LatestBackupSensor",
        "BMABackupCountSensor",
        "HANativeBackupCountSensor",
        "AppUpdateBackupCountSensor",
        "ArchiveSizeSensor",
    ]


async def main() -> None:
    test_existing_unique_ids_are_preserved()
    test_new_unique_ids_are_stable()
    test_count_sensors_and_breakdowns()
    test_latest_backup_keeps_state_and_adds_normalized_metadata()
    test_archive_size_sensor()
    test_incomplete_inventory_is_explicit()
    test_uninitialized_sensors_are_safe()
    await test_setup_registers_all_sensors()
    print("sensor simulation: OK")


if __name__ == "__main__":
    asyncio.run(main())
