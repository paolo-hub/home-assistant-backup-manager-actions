"""Sensors for Backup Manager Actions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import BackupManagerActionsCoordinator
from .inventory import SOURCE_APP_UPDATE, SOURCE_BMA, SOURCE_HA_NATIVE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Backup Manager Actions sensors."""
    coordinator: BackupManagerActionsCoordinator = entry.runtime_data
    async_add_entities(
        [
            BackupAgentCountSensor(coordinator, entry),
            BackupCountSensor(coordinator, entry),
            LatestBackupSensor(coordinator, entry),
            BMABackupCountSensor(coordinator, entry),
            HANativeBackupCountSensor(coordinator, entry),
            AppUpdateBackupCountSensor(coordinator, entry),
            ArchiveSizeSensor(coordinator, entry),
        ]
    )


class BackupManagerActionsSensor(
    CoordinatorEntity[BackupManagerActionsCoordinator],
    SensorEntity,
):
    """Base sensor for the integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _inventory_complete(self) -> bool | None:
        """Return inventory completeness when coordinator data is available."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("inventory_complete")


class BackupAgentCountSensor(BackupManagerActionsSensor):
    """Number of currently registered Backup Agents."""

    _attr_translation_key = "backup_agents"
    _attr_icon = "mdi:database-cog-outline"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_backup_agent_count"

    @property
    def native_value(self) -> int | None:
        """Return the number of agents."""
        return self.coordinator.data.get("agent_count") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return agent ids, names, domains, and errors."""
        if not self.coordinator.data:
            return {}
        return {
            "agents": self.coordinator.data.get("agents", {}),
            "agent_errors": self.coordinator.data.get("agent_errors", {}),
        }


class BackupCountSensor(BackupManagerActionsSensor):
    """Number of logical backups known to Backup Manager."""

    _attr_translation_key = "backups"
    _attr_icon = "mdi:backup-restore"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_backup_count"

    @property
    def native_value(self) -> int | None:
        """Return backup count."""
        return self.coordinator.data.get("backup_count") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose source counts without changing the existing sensor identity."""
        if not self.coordinator.data:
            return {}
        return {
            "inventory_complete": self._inventory_complete(),
            "source_counts": self.coordinator.data.get("source_counts", {}),
        }


class LatestBackupSensor(BackupManagerActionsSensor):
    """Latest logical backup seen across all Backup Agents."""

    _attr_translation_key = "latest_backup"
    _attr_icon = "mdi:archive-clock-outline"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_latest_backup"

    @property
    def native_value(self) -> str | None:
        """Return the latest backup id."""
        if not self.coordinator.data:
            return None
        latest = self.coordinator.data.get("latest_backup")
        return latest.get("backup_id") if latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose normalized latest-backup metadata."""
        if not self.coordinator.data:
            return {}
        latest = self.coordinator.data.get("latest_backup")
        return latest or {}


class BMABackupCountSensor(BackupManagerActionsSensor):
    """Number of logical backups classified as BMA."""

    _attr_translation_key = "bma_backups"
    _attr_icon = "mdi:archive-cog-outline"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_bma_backup_count"

    @property
    def native_value(self) -> int | None:
        """Return BMA backup count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("source_counts", {}).get(SOURCE_BMA, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose BMA job breakdown."""
        if not self.coordinator.data:
            return {}
        return {
            "inventory_complete": self._inventory_complete(),
            "by_job": self.coordinator.data.get("bma_by_job", {}),
        }


class HANativeBackupCountSensor(BackupManagerActionsSensor):
    """Number of logical backups classified as Home Assistant native."""

    _attr_translation_key = "ha_native_backups"
    _attr_icon = "mdi:home-assistant"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_ha_native_backup_count"

    @property
    def native_value(self) -> int | None:
        """Return Home Assistant native backup count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("source_counts", {}).get(
            SOURCE_HA_NATIVE,
            0,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose native automatic/manual informational breakdown."""
        if not self.coordinator.data:
            return {}
        return {
            "inventory_complete": self._inventory_complete(),
            **self.coordinator.data.get("ha_native_breakdown", {}),
        }


class AppUpdateBackupCountSensor(BackupManagerActionsSensor):
    """Number of logical backups classified as App Update."""

    _attr_translation_key = "app_update_backups"
    _attr_icon = "mdi:package-up"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_app_update_backup_count"

    @property
    def native_value(self) -> int | None:
        """Return App Update backup count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("source_counts", {}).get(
            SOURCE_APP_UPDATE,
            0,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose App Update backup count by App slug."""
        if not self.coordinator.data:
            return {}
        return {
            "inventory_complete": self._inventory_complete(),
            "by_app": self.coordinator.data.get("app_update_by_app", {}),
        }


class ArchiveSizeSensor(BackupManagerActionsSensor):
    """Physical size of all visible backup copies across Backup Agents."""

    _attr_translation_key = "archive_size"
    _attr_icon = "mdi:database-arrow-up-outline"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_archive_size"

    @property
    def native_value(self) -> int | None:
        """Return total known physical bytes across every visible copy."""
        if not self.coordinator.data:
            return None
        archive = self.coordinator.data.get("archive_size")
        return archive.get("physical_total_bytes") if archive else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose logical totals and per-agent/source archive breakdowns."""
        if not self.coordinator.data:
            return {}
        archive = self.coordinator.data.get("archive_size")
        if not archive:
            return {}
        return {
            **archive,
            "inventory_complete": self._inventory_complete(),
            "agent_errors": self.coordinator.data.get("agent_errors", {}),
        }
