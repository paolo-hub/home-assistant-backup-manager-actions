"""Coordinator for Backup Manager Actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.backup import BackupPlatformEvent, IdleEvent, ManagerBackup
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapter import BackupManagerAdapter
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackupManagerActionsData:
    """Data exposed by the coordinator."""

    backups: dict[str, ManagerBackup]
    agents: dict[str, dict[str, str]]
    agent_errors: dict[str, str]


class BackupManagerActionsCoordinator(
    DataUpdateCoordinator[BackupManagerActionsData]
):
    """Keep Backup Manager information synchronized."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.adapter = BackupManagerAdapter(hass)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
        )

    async def _async_update_data(self) -> BackupManagerActionsData:
        """Fetch current backup and agent information."""
        try:
            backups, agent_errors = await self.adapter.async_get_backups()
        except Exception as err:
            raise UpdateFailed(f"Unable to read Backup Manager data: {err}") from err

        agents = {
            agent_id: {
                "name": agent.name,
                "domain": agent.domain,
            }
            for agent_id, agent in self.adapter.backup_agents.items()
        }

        return BackupManagerActionsData(
            backups=backups,
            agents=agents,
            agent_errors={
                agent_id: str(error) for agent_id, error in agent_errors.items()
            },
        )

    @callback
    def _handle_manager_event(self, event: Any) -> None:
        """Refresh after a Backup Manager operation finishes."""
        if isinstance(event, IdleEvent):
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _handle_platform_event(self, event: BackupPlatformEvent) -> None:
        """Refresh when backup agents are added or removed."""
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_subscribe(self) -> list[Callable[[], None]]:
        """Subscribe to Backup Manager events."""
        manager = self.adapter.manager
        return [
            manager.async_subscribe_events(self._handle_manager_event),
            manager.async_subscribe_platform_events(self._handle_platform_event),
        ]
