"""Adapter around Home Assistant's Backup Manager public API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.backup import BackupManager, Folder, async_get_manager
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


class BackupManagerActionsError(HomeAssistantError):
    """Base error raised by Backup Manager Actions."""


class BackupManagerActionsAdapter:
    """Small compatibility layer around Home Assistant's Backup Manager."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the adapter."""
        self._hass = hass

    @property
    def manager(self) -> BackupManager:
        """Return Home Assistant's Backup Manager."""
        return async_get_manager(self._hass)

    def list_agents(self) -> dict[str, str]:
        """Return currently registered backup agents keyed by agent id."""
        return {
            agent_id: agent.name
            for agent_id, agent in self.manager.backup_agents.items()
        }

    def validate_agent_ids(self, agent_ids: list[str]) -> None:
        """Ensure all requested agents are currently available."""
        available = set(self.manager.backup_agents)
        missing = sorted(set(agent_ids) - available)
        if missing:
            raise BackupManagerActionsError(
                "Backup agent(s) not available: " + ", ".join(missing)
            )

    async def async_create(
        self,
        *,
        agent_ids: list[str],
        include_homeassistant: bool,
        include_database: bool,
        include_all_addons: bool,
        include_addons: list[str] | None,
        include_folders: list[str] | None,
        name: str | None,
        password: str | None,
    ) -> dict[str, Any]:
        """Create a backup and verify that every requested agent stored it."""
        self.validate_agent_ids(agent_ids)

        if include_all_addons and include_addons:
            raise BackupManagerActionsError(
                "include_all_addons and include_addons are mutually exclusive"
            )

        folders = (
            [Folder(folder) for folder in include_folders]
            if include_folders is not None
            else None
        )

        manager = self.manager
        new_backup = await manager.async_create_backup(
            agent_ids=agent_ids,
            include_addons=include_addons,
            include_all_addons=include_all_addons,
            include_database=include_database,
            include_folders=folders,
            include_homeassistant=include_homeassistant,
            name=name,
            password=password,
        )

        backup_id = new_backup.backup_job_id
        backup, agent_errors = await manager.async_get_backup(backup_id)
        if backup is None:
            raise BackupManagerActionsError(
                f"Backup {backup_id} was created but could not be read back"
            )

        stored_agent_ids = sorted(backup.agents)
        missing_agent_ids = sorted(set(agent_ids) - set(stored_agent_ids))
        requested = set(agent_ids)
        errors = {
            agent_id: str(err)
            for agent_id, err in agent_errors.items()
            if agent_id in requested
        }

        if missing_agent_ids or errors:
            details: list[str] = []
            if missing_agent_ids:
                details.append(
                    "missing agent copies: " + ", ".join(missing_agent_ids)
                )
            if errors:
                details.append(
                    "agent errors: "
                    + "; ".join(
                        f"{agent_id}: {message}"
                        for agent_id, message in sorted(errors.items())
                    )
                )
            raise BackupManagerActionsError(
                f"Backup {backup_id} did not complete on every requested agent ("
                + " | ".join(details)
                + ")"
            )

        return {
            "backup_id": backup.backup_id,
            "name": backup.name,
            "date": backup.date,
            "requested_agent_ids": list(agent_ids),
            "stored_agent_ids": stored_agent_ids,
            "protected_by_agent": {
                agent_id: status.protected
                for agent_id, status in backup.agents.items()
            },
            "size_by_agent": {
                agent_id: status.size for agent_id, status in backup.agents.items()
            },
        }

    async def async_delete(
        self, *, backup_id: str, agent_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Delete a backup globally or from selected agents."""
        manager = self.manager
        backup, lookup_errors = await manager.async_get_backup(backup_id)
        relevant_lookup_errors = (
            lookup_errors
            if agent_ids is None
            else {
                agent_id: err
                for agent_id, err in lookup_errors.items()
                if agent_id in set(agent_ids)
            }
        )
        if relevant_lookup_errors:
            errors = "; ".join(
                f"{agent_id}: {err}"
                for agent_id, err in sorted(relevant_lookup_errors.items())
            )
            raise BackupManagerActionsError(
                f"Could not safely inspect backup {backup_id}: {errors}"
            )
        if backup is None:
            raise BackupManagerActionsError(f"Backup {backup_id} was not found")

        existing_agent_ids = sorted(backup.agents)
        if agent_ids is not None:
            self.validate_agent_ids(agent_ids)
            requested_agent_ids = list(agent_ids)
        else:
            # None deliberately means all registered agents to BackupManager.
            requested_agent_ids = existing_agent_ids

        delete_errors = await manager.async_delete_backup(
            backup_id, agent_ids=agent_ids
        )
        if delete_errors:
            errors = "; ".join(
                f"{agent_id}: {err}"
                for agent_id, err in sorted(delete_errors.items())
            )
            raise BackupManagerActionsError(
                f"Backup {backup_id} was not deleted cleanly: {errors}"
            )

        remaining, verify_errors = await manager.async_get_backup(backup_id)
        relevant_verify_errors = (
            verify_errors
            if agent_ids is None
            else {
                agent_id: err
                for agent_id, err in verify_errors.items()
                if agent_id in set(agent_ids)
            }
        )
        if relevant_verify_errors:
            errors = "; ".join(
                f"{agent_id}: {err}"
                for agent_id, err in sorted(relevant_verify_errors.items())
            )
            raise BackupManagerActionsError(
                f"Backup {backup_id} deletion could not be verified: {errors}"
            )

        remaining_agent_ids = sorted(remaining.agents) if remaining else []
        unexpectedly_remaining = sorted(
            set(requested_agent_ids) & set(remaining_agent_ids)
        )
        if unexpectedly_remaining:
            raise BackupManagerActionsError(
                f"Backup {backup_id} still exists on: "
                + ", ".join(unexpectedly_remaining)
            )

        return {
            "backup_id": backup_id,
            "requested_agent_ids": requested_agent_ids,
            "previous_agent_ids": existing_agent_ids,
            "remaining_agent_ids": remaining_agent_ids,
        }

    async def async_snapshot(self) -> dict[str, Any]:
        """Return a normalized snapshot of Backup Manager state."""
        manager = self.manager
        backups, agent_errors = await manager.async_get_backups()
        agents = self.list_agents()

        ordered_backups = sorted(
            backups.values(), key=lambda item: item.date, reverse=True
        )
        latest = ordered_backups[0] if ordered_backups else None

        return {
            "state": str(manager.state),
            "agent_count": len(agents),
            "agents": agents,
            "backup_count": len(backups),
            "latest_backup": self._backup_to_dict(latest) if latest else None,
            "agent_errors": {
                agent_id: str(error) for agent_id, error in agent_errors.items()
            },
        }

    @staticmethod
    def _backup_to_dict(backup) -> dict[str, Any]:
        """Convert a ManagerBackup to a JSON-friendly dictionary."""
        data = asdict(backup)
        data["folders"] = [str(folder) for folder in backup.folders]
        return data
