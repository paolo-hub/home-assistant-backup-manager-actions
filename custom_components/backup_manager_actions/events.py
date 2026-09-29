"""New-backup event helpers for Backup Manager Actions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .inventory import SOURCE_APP_UPDATE, SOURCE_BMA, SOURCE_HA_NATIVE

EXTERNAL_EVENT_SOURCES = frozenset({SOURCE_HA_NATIVE, SOURCE_APP_UPDATE})


def backup_created_event_data(backup: Mapping[str, Any]) -> dict[str, Any]:
    """Build the stable Home Assistant event payload from a normalized backup."""
    agents = backup.get("agents") or {}
    agent_ids = sorted(str(agent_id) for agent_id in agents)

    return {
        "backup_id": backup["backup_id"],
        "name": backup.get("name"),
        "date": backup.get("date"),
        "source_type": backup.get("source_type"),
        "job_id": backup.get("job_id"),
        "app_slug": backup.get("app_slug"),
        "agent_ids": agent_ids,
        "size_by_agent": {
            agent_id: agents[agent_id].get("size")
            for agent_id in agent_ids
        },
        "protected_by_agent": {
            agent_id: bool(agents[agent_id].get("protected", False))
            for agent_id in agent_ids
        },
        "failed_agent_ids": list(backup.get("failed_agent_ids") or []),
        "with_automatic_settings": backup.get("with_automatic_settings"),
    }


def backup_created_event_from_create_response(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the event payload after a verified BMA create action."""
    agent_ids = sorted(str(item) for item in result["stored_agent_ids"])
    size_by_agent = result.get("size_by_agent") or {}
    protected_by_agent = result.get("protected_by_agent") or {}

    return {
        "backup_id": result["backup_id"],
        "name": result.get("name"),
        "date": result.get("date"),
        "source_type": result.get("source_type"),
        "job_id": result.get("job_id"),
        "app_slug": None,
        "agent_ids": agent_ids,
        "size_by_agent": {
            agent_id: size_by_agent.get(agent_id)
            for agent_id in agent_ids
        },
        "protected_by_agent": {
            agent_id: bool(protected_by_agent.get(agent_id, False))
            for agent_id in agent_ids
        },
        "failed_agent_ids": list(result.get("failed_agent_ids") or []),
        "with_automatic_settings": result.get("with_automatic_settings"),
    }


class BackupCreatedEventTracker:
    """Track logical backup ids so new-backup events are emitted exactly once."""

    def __init__(self) -> None:
        """Initialize an empty tracker without a startup baseline."""
        self._baseline_ready = False
        self._seen_backup_ids: set[str] = set()
        self._emitted_backup_ids: set[str] = set()

    @property
    def baseline_ready(self) -> bool:
        """Return whether a complete startup inventory established the baseline."""
        return self._baseline_ready

    def process_complete_inventory(
        self,
        backups: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Process one complete inventory and return external events to fire."""
        backup_list = list(backups)
        by_id = {
            str(backup["backup_id"]): backup
            for backup in backup_list
        }
        current_ids = set(by_id)

        if not self._baseline_ready:
            self._seen_backup_ids.update(current_ids)
            # Startup history must suppress discovery-driven events, but a BMA
            # backup can be visible in this first complete snapshot while its
            # create action is still performing final verification. Mark only
            # external-source history as already emitted so that a verified
            # BMA create can still publish its gated event afterwards.
            self._emitted_backup_ids.update(
                backup_id
                for backup_id, backup in by_id.items()
                if backup.get("source_type") in EXTERNAL_EVENT_SOURCES
            )
            self._baseline_ready = True
            return []

        new_ids = current_ids - self._seen_backup_ids
        self._seen_backup_ids.update(current_ids)

        ordered_new = sorted(
            (by_id[backup_id] for backup_id in new_ids),
            key=lambda backup: (
                str(backup.get("date") or ""),
                str(backup["backup_id"]),
            ),
        )

        events: list[dict[str, Any]] = []
        for backup in ordered_new:
            if backup.get("source_type") not in EXTERNAL_EVENT_SOURCES:
                continue
            payload = backup_created_event_data(backup)
            backup_id = str(payload["backup_id"])
            if backup_id in self._emitted_backup_ids:
                continue
            self._emitted_backup_ids.add(backup_id)
            events.append(payload)

        return events

    def record_verified_bma_create(
        self,
        result: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return one event for a verified BMA create, suppressing duplicates."""
        payload = backup_created_event_from_create_response(result)
        if payload["source_type"] != SOURCE_BMA:
            raise ValueError("Verified create event must have source_type=bma")

        backup_id = str(payload["backup_id"])
        self._seen_backup_ids.add(backup_id)
        if backup_id in self._emitted_backup_ids:
            return None

        self._emitted_backup_ids.add(backup_id)
        return payload
