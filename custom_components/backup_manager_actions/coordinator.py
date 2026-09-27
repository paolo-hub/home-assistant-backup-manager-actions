"""Coordinator for Backup Manager Actions."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.backup import BackupPlatformEvent, IdleEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapter import BackupManagerActionsAdapter
from .const import DOMAIN

LOGGER = logging.getLogger(__name__)


class BackupManagerActionsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep a small cached view of the Backup Manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        adapter: BackupManagerActionsAdapter,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
        )
        self.adapter = adapter
        self._unsubscribers: list[Callable[[], None]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch a coherent snapshot from the Backup Manager."""
        try:
            return await self.adapter.async_snapshot()
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_subscribe(self) -> None:
        """Refresh after Backup Manager operations and agent changes."""
        manager = self.adapter.manager

        @callback
        def _on_backup_event(event: Any) -> None:
            if isinstance(event, IdleEvent):
                self.hass.async_create_task(self.async_request_refresh())

        @callback
        def _on_platform_event(_event: BackupPlatformEvent) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self._unsubscribers.extend(
            [
                manager.async_subscribe_events(_on_backup_event),
                manager.async_subscribe_platform_events(_on_platform_event),
            ]
        )

    @callback
    def async_unsubscribe(self) -> None:
        """Remove Backup Manager listeners."""
        while self._unsubscribers:
            self._unsubscribers.pop()()
