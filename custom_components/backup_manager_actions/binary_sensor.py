"""Binary sensors for Backup Manager Actions."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import BackupManagerActionsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Backup Manager Actions binary sensors."""
    coordinator: BackupManagerActionsCoordinator = entry.runtime_data
    async_add_entities([BackupAgentsHealthyBinarySensor(coordinator, entry)])


class BackupAgentsHealthyBinarySensor(
    CoordinatorEntity[BackupManagerActionsCoordinator],
    BinarySensorEntity,
):
    """Whether registered Backup Agents can all be queried."""

    _attr_has_entity_name = True
    _attr_translation_key = "backup_agents_healthy"
    _attr_icon = "mdi:database-check"

    def __init__(
        self,
        coordinator: BackupManagerActionsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_backup_agents_healthy"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true when agents exist and the latest listing has no errors."""
        if not self.coordinator.data:
            return None
        return (
            self.coordinator.data.get("agent_count", 0) > 0
            and not self.coordinator.data.get("agent_errors")
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return listing errors for diagnostics."""
        if not self.coordinator.data:
            return {}
        return {
            "agent_errors": self.coordinator.data.get("agent_errors", {}),
        }
