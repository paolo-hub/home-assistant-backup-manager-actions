"""Adapter around Home Assistant's Backup Manager public API."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from homeassistant.components.backup import (
    BackupManager,
    Folder,
    ManagerBackup,
    async_get_manager,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .inventory import (
    CURRENT_METADATA_VERSION,
    CURRENT_METADATA_VERSION_STORAGE,
    METADATA_CORRELATION_ID,
    METADATA_JOB_ID,
    METADATA_MANAGED,
    METADATA_VERSION,
    SOURCE_BMA,
    aggregate_inventory,
    normalize_backup,
    normalize_job_id,
)

CREATE_VERIFY_ATTEMPTS = 5
CREATE_VERIFY_DELAY_SECONDS = 1.0


class BackupManagerActionsError(HomeAssistantError):
    """Base error raised by Backup Manager Actions."""


class BackupManagerActionsAdapter:
    """Compatibility and safety layer around Home Assistant's Backup Manager."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the adapter."""
        self._hass = hass

    @property
    def manager(self) -> BackupManager:
        """Return Home Assistant's Backup Manager."""
        return async_get_manager(self._hass)

    def list_agents(self) -> dict[str, dict[str, str]]:
        """Return currently registered backup agents keyed by agent id."""
        return {
            agent_id: {
                "name": agent.name,
                "domain": agent.domain,
            }
            for agent_id, agent in self.manager.backup_agents.items()
        }

    def validate_agent_ids(self, agent_ids: list[str]) -> None:
        """Ensure all requested agents are currently registered."""
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
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a backup and verify destinations and BMA metadata."""
        self.validate_agent_ids(agent_ids)

        normalized_job_id: str | None = None
        if job_id is not None:
            normalized_job_id = normalize_job_id(job_id)
            if normalized_job_id is None:
                raise BackupManagerActionsError(
                    "Invalid job_id; expected ^[a-z0-9][a-z0-9_-]{0,63}$"
                )

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
        correlation_id = uuid4().hex
        extra_metadata: dict[str, bool | str] = {
            METADATA_MANAGED: True,
            METADATA_CORRELATION_ID: correlation_id,
            METADATA_VERSION: CURRENT_METADATA_VERSION_STORAGE,
        }
        if normalized_job_id is not None:
            extra_metadata[METADATA_JOB_ID] = normalized_job_id

        new_backup = await manager.async_create_backup(
            agent_ids=agent_ids,
            extra_metadata=extra_metadata,
            include_addons=include_addons,
            include_all_addons=include_all_addons,
            include_database=include_database,
            include_folders=folders,
            include_homeassistant=include_homeassistant,
            name=name,
            password=password,
        )

        # Home Assistant returns a Supervisor job id here, not the final backup id.
        # Correlate the completed backup through metadata written into the archive.
        requested = set(agent_ids)
        backup: ManagerBackup | None = None
        agent_errors: dict[str, Exception] = {}

        for attempt in range(CREATE_VERIFY_ATTEMPTS):
            backups, agent_errors = await manager.async_get_backups()
            backup = next(
                (
                    item
                    for item in backups.values()
                    if item.extra_metadata.get(METADATA_CORRELATION_ID)
                    == correlation_id
                ),
                None,
            )

            relevant_errors = {
                agent_id: str(error)
                for agent_id, error in agent_errors.items()
                if agent_id in requested
            }
            if backup is not None:
                stored_agent_ids = set(backup.agents)
                if requested.issubset(stored_agent_ids) and not relevant_errors:
                    break

            if attempt < CREATE_VERIFY_ATTEMPTS - 1:
                await asyncio.sleep(CREATE_VERIFY_DELAY_SECONDS)

        if backup is None:
            relevant_errors = {
                agent_id: str(error)
                for agent_id, error in agent_errors.items()
                if agent_id in requested
            }
            detail = (
                "; agent errors: "
                + "; ".join(
                    f"{agent_id}: {message}"
                    for agent_id, message in sorted(relevant_errors.items())
                )
                if relevant_errors
                else ""
            )
            raise BackupManagerActionsError(
                "Backup job "
                f"{new_backup.backup_job_id} completed but the final backup "
                f"could not be correlated{detail}"
            )

        stored_agent_ids = sorted(backup.agents)
        missing_agent_ids = sorted(requested - set(stored_agent_ids))
        relevant_errors = {
            agent_id: str(error)
            for agent_id, error in agent_errors.items()
            if agent_id in requested
        }

        if missing_agent_ids or relevant_errors:
            details: list[str] = []
            if missing_agent_ids:
                details.append(
                    "missing agent copies: " + ", ".join(missing_agent_ids)
                )
            if relevant_errors:
                details.append(
                    "agent errors: "
                    + "; ".join(
                        f"{agent_id}: {message}"
                        for agent_id, message in sorted(relevant_errors.items())
                    )
                )
            raise BackupManagerActionsError(
                f"Backup {backup.backup_id} did not complete on every requested agent ("
                + " | ".join(details)
                + ")"
            )

        normalized_backup = normalize_backup(backup)
        metadata_errors: list[str] = []
        if normalized_backup["source_type"] != SOURCE_BMA:
            metadata_errors.append(
                "source_type is " + str(normalized_backup["source_type"])
            )
        if normalized_backup["metadata_version"] != CURRENT_METADATA_VERSION:
            metadata_errors.append(
                "metadata_version is "
                + str(normalized_backup["metadata_version"])
                + f", expected {CURRENT_METADATA_VERSION}"
            )
        if normalized_backup["job_id"] != normalized_job_id:
            metadata_errors.append(
                "job_id is "
                + str(normalized_backup["job_id"])
                + f", expected {normalized_job_id}"
            )
        if metadata_errors:
            raise BackupManagerActionsError(
                f"Backup {backup.backup_id} metadata verification failed ("
                + " | ".join(metadata_errors)
                + ")"
            )

        return {
            "backup_id": backup.backup_id,
            "backup_job_id": new_backup.backup_job_id,
            "name": backup.name,
            "date": backup.date,
            "source_type": normalized_backup["source_type"],
            "job_id": normalized_backup["job_id"],
            "metadata_version": normalized_backup["metadata_version"],
            "requested_agent_ids": list(agent_ids),
            "stored_agent_ids": stored_agent_ids,
            "protected_by_agent": {
                agent_id: status.protected
                for agent_id, status in backup.agents.items()
                if agent_id in requested
            },
            "size_by_agent": {
                agent_id: status.size
                for agent_id, status in backup.agents.items()
                if agent_id in requested
            },
        }

    async def async_delete(
        self,
        *,
        backup_id: str,
        agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Delete a backup globally or from selected agents, then verify it."""
        manager = self.manager

        if agent_ids is not None:
            self.validate_agent_ids(agent_ids)
            target_agent_ids = set(agent_ids)
        else:
            target_agent_ids = set(manager.backup_agents)

        backup, lookup_errors = await manager.async_get_backup(backup_id)
        relevant_lookup_errors = {
            agent_id: error
            for agent_id, error in lookup_errors.items()
            if agent_ids is None or agent_id in target_agent_ids
        }
        if relevant_lookup_errors:
            errors = "; ".join(
                f"{agent_id}: {error}"
                for agent_id, error in sorted(relevant_lookup_errors.items())
            )
            raise BackupManagerActionsError(
                f"Could not safely inspect backup {backup_id}: {errors}"
            )
        if backup is None:
            return {
                "backup_id": backup_id,
                "found_before_delete": False,
                "target_agent_ids": sorted(target_agent_ids),
                "previous_agent_ids": [],
                "remaining_agent_ids": [],
            }

        existing_agent_ids = sorted(backup.agents)

        delete_errors = await manager.async_delete_backup(
            backup_id,
            agent_ids=agent_ids,
        )
        if delete_errors:
            errors = "; ".join(
                f"{agent_id}: {error}"
                for agent_id, error in sorted(delete_errors.items())
            )
            raise BackupManagerActionsError(
                f"Backup {backup_id} was not deleted cleanly: {errors}"
            )

        remaining, verify_errors = await manager.async_get_backup(backup_id)
        relevant_verify_errors = {
            agent_id: error
            for agent_id, error in verify_errors.items()
            if agent_ids is None or agent_id in target_agent_ids
        }
        if relevant_verify_errors:
            errors = "; ".join(
                f"{agent_id}: {error}"
                for agent_id, error in sorted(relevant_verify_errors.items())
            )
            raise BackupManagerActionsError(
                f"Backup {backup_id} deletion could not be verified: {errors}"
            )

        remaining_agent_ids = sorted(remaining.agents) if remaining else []
        unexpectedly_remaining = sorted(
            target_agent_ids.intersection(remaining_agent_ids)
        )
        if unexpectedly_remaining:
            raise BackupManagerActionsError(
                f"Backup {backup_id} still exists on: "
                + ", ".join(unexpectedly_remaining)
            )

        return {
            "backup_id": backup_id,
            "found_before_delete": True,
            "target_agent_ids": sorted(target_agent_ids),
            "previous_agent_ids": existing_agent_ids,
            "remaining_agent_ids": remaining_agent_ids,
        }

    async def async_list_backups(self) -> dict[str, Any]:
        """Return all logical backups known to Backup Manager."""
        backups, agent_errors = await self.manager.async_get_backups()
        ordered = sorted(backups.values(), key=lambda item: item.date, reverse=True)
        return {
            "backups": [normalize_backup(backup) for backup in ordered],
            "agent_errors": self._errors_to_dict(agent_errors),
        }

    async def async_get_backup(self, backup_id: str) -> dict[str, Any]:
        """Return one logical backup by id."""
        backup, agent_errors = await self.manager.async_get_backup(backup_id)
        return {
            "backup": normalize_backup(backup) if backup is not None else None,
            "agent_errors": self._errors_to_dict(agent_errors),
        }

    async def async_snapshot(self) -> dict[str, Any]:
        """Return a normalized snapshot of Backup Manager state."""
        manager = self.manager
        backups, agent_errors = await manager.async_get_backups()
        agents = self.list_agents()

        ordered_backups = sorted(
            backups.values(),
            key=lambda item: item.date,
            reverse=True,
        )
        normalized_backups = [normalize_backup(backup) for backup in ordered_backups]
        normalized_errors = self._errors_to_dict(agent_errors)
        inventory_summary = aggregate_inventory(
            normalized_backups,
            agents,
            normalized_errors,
        )

        return {
            "state": str(manager.state),
            "agent_count": len(agents),
            "agents": agents,
            "backup_count": len(backups),
            "latest_backup": normalized_backups[0] if normalized_backups else None,
            "agent_errors": normalized_errors,
            **inventory_summary,
        }

    @staticmethod
    def _errors_to_dict(errors: dict[str, Exception]) -> dict[str, str]:
        """Convert per-agent errors to JSON-friendly strings."""
        return {agent_id: str(error) for agent_id, error in errors.items()}

