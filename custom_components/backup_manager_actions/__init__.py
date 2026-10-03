"""Backup Manager Actions integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .adapter import BackupManagerActionsAdapter
from .const import (
    DATA_ADAPTER,
    DATA_COORDINATORS,
    DATA_EVENT_TRACKER,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import BackupManagerActionsCoordinator
from .events import BackupCreatedEventTracker
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up Backup Manager Actions."""
    adapter = BackupManagerActionsAdapter(hass)
    event_tracker = BackupCreatedEventTracker()
    hass.data[DOMAIN] = {
        DATA_ADAPTER: adapter,
        DATA_COORDINATORS: set(),
        DATA_EVENT_TRACKER: event_tracker,
    }
    async_setup_services(hass, adapter, event_tracker)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Backup Manager Actions from a config entry."""
    domain_data: dict[str, Any] = hass.data[DOMAIN]
    adapter: BackupManagerActionsAdapter = domain_data[DATA_ADAPTER]
    event_tracker: BackupCreatedEventTracker = domain_data[DATA_EVENT_TRACKER]
    coordinator = BackupManagerActionsCoordinator(
        hass,
        entry,
        adapter,
        event_tracker,
    )

    await coordinator.async_config_entry_first_refresh()
    coordinator.async_subscribe()
    entry.async_on_unload(coordinator.async_unsubscribe)

    coordinators: set[BackupManagerActionsCoordinator] = domain_data[DATA_COORDINATORS]
    coordinators.add(coordinator)
    entry.async_on_unload(lambda: coordinators.discard(coordinator))

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Backup Manager Actions config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
