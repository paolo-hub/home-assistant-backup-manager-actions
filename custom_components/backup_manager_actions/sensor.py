"""Sensors for Backup Manager Actions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BackupManagerActionsCoordinator


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
        ]
    )


class BackupManagerActionsSensor(
    CoordinatorEntity[BackupManagerActionsCoordinator], SensorEntity
):
    """Base sensor for the integration."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BackupManagerActionsCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry_id = entry.entry_id


class BackupAgentCountSensor(BackupManagerActionsSensor):
    """Number of currently registered Backup Agents."""

    _attr_translation_key = "backup_agents"
    _attr_icon = "mdi:database-cog-outline"

    def __init__(
        self, coordinator: BackupManagerActionsCoordinator, entry: ConfigEntry
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
        """Return agent ids and names."""
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
        self, coordinator: BackupManagerActionsCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_backup_count"

    @property
    def native_value(self) -> int | None:
        """Return backup count."""
        return self.coordinator.data.get("backup_count") if self.coordinator.data else None


class LatestBackupSensor(BackupManagerActionsSensor):
    """Latest logical backup seen across all Backup Agents."""

    _attr_translation_key = "latest_backup"
    _attr_icon = "mdi:archive-clock-outline"

    def __init__(
        self, coordinator: BackupManagerActionsCoordinator, entry: ConfigEntry
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
        """Expose latest backup metadata."""
        if not self.coordinator.data:
            return {}
        latest = self.coordinator.data.get("latest_backup")
        return latest or {}
