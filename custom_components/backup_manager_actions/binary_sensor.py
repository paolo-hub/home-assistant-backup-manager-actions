"""Binary sensors for Backup Manager Actions."""

from typing import Any, override

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Backup Manager Actions binary sensors."""
    coordinator: BackupManagerActionsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BackupAgentsHealthyBinarySensor(coordinator)])


class BackupAgentsHealthyBinarySensor(BackupManagerActionsEntity, BinarySensorEntity):
    """Whether all registered backup agents can be listed successfully."""

    _attr_translation_key = "backup_agents_healthy"
    _attr_unique_id = "backup_manager_actions_backup_agents_healthy"
    _attr_icon = "mdi:database-check"

    @property
    @override
    def is_on(self) -> bool:
        """Return true when at least one agent exists and none reports an error."""
        return bool(self.coordinator.data.agents) and not self.coordinator.data.agent_errors

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-agent errors."""
        return {"agent_errors": self.coordinator.data.agent_errors}
