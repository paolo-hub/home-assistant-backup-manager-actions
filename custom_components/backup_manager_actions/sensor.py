"""Sensors for Backup Manager Actions."""

from typing import Any, override

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import BackupManagerActionsCoordinator
from .entity import BackupManagerActionsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Backup Manager Actions sensors."""
    coordinator: BackupManagerActionsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BackupCountSensor(coordinator),
            AgentCountSensor(coordinator),
            LatestBackupSensor(coordinator),
        ]
    )


class BackupCountSensor(BackupManagerActionsEntity, SensorEntity):
    """Number of logical backups visible to Backup Manager."""

    _attr_translation_key = "backup_count"
    _attr_unique_id = "backup_manager_actions_backup_count"
    _attr_icon = "mdi:backup-restore"

    @property
    @override
    def native_value(self) -> int:
        """Return the number of logical backups."""
        return len(self.coordinator.data.backups)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return Backup Manager listing errors."""
        return {"agent_errors": self.coordinator.data.agent_errors}


class AgentCountSensor(BackupManagerActionsEntity, SensorEntity):
    """Number of currently registered backup agents."""

    _attr_translation_key = "agent_count"
    _attr_unique_id = "backup_manager_actions_agent_count"
    _attr_icon = "mdi:database-sync"

    @property
    @override
    def native_value(self) -> int:
        """Return the number of registered backup agents."""
        return len(self.coordinator.data.agents)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return registered backup agents."""
        return {"agents": self.coordinator.data.agents}


class LatestBackupSensor(BackupManagerActionsEntity, SensorEntity):
    """Latest logical backup visible to Backup Manager."""

    _attr_translation_key = "latest_backup"
    _attr_unique_id = "backup_manager_actions_latest_backup"
    _attr_icon = "mdi:archive-clock"

    @property
    def _latest_backup(self):
        """Return the latest backup, if any."""
        backups = self.coordinator.data.backups.values()
        return max(backups, key=lambda backup: backup.date, default=None)

    @property
    @override
    def native_value(self) -> str | None:
        """Return the latest backup id."""
        backup = self._latest_backup
        return backup.backup_id if backup else None

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details of the latest backup."""
        backup = self._latest_backup
        if backup is None:
            return {}

        return {
            "name": backup.name,
            "date": backup.date,
            "homeassistant_version": backup.homeassistant_version,
            "homeassistant_included": backup.homeassistant_included,
            "database_included": backup.database_included,
            "addons": [addon.slug for addon in backup.addons],
            "folders": [folder.value for folder in backup.folders],
            "agents": {
                agent_id: {
                    "protected": status.protected,
                    "size": status.size,
                }
                for agent_id, status in backup.agents.items()
            },
            "failed_agent_ids": backup.failed_agent_ids,
        }
