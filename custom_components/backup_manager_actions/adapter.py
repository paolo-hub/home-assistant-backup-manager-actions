"""Adapter around Home Assistant's native Backup Manager API."""

from __future__ import annotations

from homeassistant.components.backup import (
    BackupManager,
    Folder,
    ManagerBackup,
    NewBackup,
    async_get_manager,
)
from homeassistant.core import HomeAssistant


class BackupManagerAdapter:
    """Keep Home Assistant Backup Manager calls isolated in one place."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the adapter."""
        self.manager: BackupManager = async_get_manager(hass)

    @property
    def backup_agents(self):
        """Return currently registered backup agents."""
        return self.manager.backup_agents

    async def async_create_backup(
        self,
        *,
        agent_ids: list[str],
        include_addons: list[str] | None,
        include_all_addons: bool,
        include_database: bool,
        include_folders: list[Folder] | None,
        include_homeassistant: bool,
        name: str | None,
        password: str | None,
    ) -> NewBackup:
        """Create and wait for a custom backup."""
        return await self.manager.async_create_backup(
            agent_ids=agent_ids,
            include_addons=include_addons,
            include_all_addons=include_all_addons,
            include_database=include_database,
            include_folders=include_folders,
            include_homeassistant=include_homeassistant,
            name=name,
            password=password,
        )

    async def async_get_backups(
        self,
    ) -> tuple[dict[str, ManagerBackup], dict[str, Exception]]:
        """Return logical backups merged across agents."""
        return await self.manager.async_get_backups()

    async def async_get_backup(
        self, backup_id: str
    ) -> tuple[ManagerBackup | None, dict[str, Exception]]:
        """Return a logical backup by id."""
        return await self.manager.async_get_backup(backup_id)

    async def async_delete_backup(
        self,
        backup_id: str,
        *,
        agent_ids: list[str] | None = None,
    ) -> dict[str, Exception]:
        """Delete a backup from all or selected agents."""
        return await self.manager.async_delete_backup(
            backup_id,
            agent_ids=agent_ids,
        )
