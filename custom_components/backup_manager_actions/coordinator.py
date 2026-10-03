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
from .const import DOMAIN, EVENT_BACKUP_CREATED
from .events import BackupCreatedEventTracker

LOGGER = logging.getLogger(__name__)


class BackupManagerActionsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keep a small cached view of the Backup Manager."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        adapter: BackupManagerActionsAdapter,
        event_tracker: BackupCreatedEventTracker,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
        )
        self.adapter = adapter
        self._event_tracker = event_tracker
        self._pending_event_data: list[dict[str, Any]] = []
        self._unsubscribers: list[Callable[[], None]] = []

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch a coherent snapshot and emit events from complete inventories."""
        try:
            snapshot, backups = await self.adapter.async_snapshot_with_backups()
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        self._pending_event_data = []
        if snapshot.get("inventory_complete") is True:
            self._pending_event_data = self._event_tracker.process_complete_inventory(
                backups
            )

        return snapshot

    @callback
    def _async_refresh_finished(self) -> None:
        """Publish pending events after coordinator data has been committed."""
        if not self._pending_event_data:
            return

        pending = self._pending_event_data
        self._pending_event_data = []
        self.hass.async_create_task(
            self._async_fire_pending_events(pending), eager_start=False
        )

    async def _async_fire_pending_events(
        self,
        pending: list[dict[str, Any]],
    ) -> None:
        """Fire events in a separate task after refresh listeners can update."""
        for event_data in pending:
            self.hass.bus.async_fire(EVENT_BACKUP_CREATED, event_data)

    @callback
    def async_publish_verified_bma_create(
        self,
        result: dict[str, Any],
    ) -> None:
        """Emit one event after a BMA create completed verification."""
        event_data = self._event_tracker.record_verified_bma_create(result)
        if event_data is not None:
            self.hass.bus.async_fire(EVENT_BACKUP_CREATED, event_data)

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
