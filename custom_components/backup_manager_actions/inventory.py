"""Pure helpers for Backup Manager Actions inventory normalization."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import re
from typing import Any

SOURCE_BMA = "bma"
SOURCE_HA_NATIVE = "ha_native"
SOURCE_APP_UPDATE = "app_update"
SOURCE_UNKNOWN = "unknown"
SOURCE_TYPES = (
    SOURCE_BMA,
    SOURCE_HA_NATIVE,
    SOURCE_APP_UPDATE,
    SOURCE_UNKNOWN,
)

METADATA_MANAGED = "backup_manager_actions.managed"
METADATA_CORRELATION_ID = "backup_manager_actions.correlation_id"
METADATA_VERSION = "backup_manager_actions.metadata_version"
METADATA_JOB_ID = "backup_manager_actions.job_id"
METADATA_APP_UPDATE = "supervisor.addon_update"

CURRENT_METADATA_VERSION = 1
CURRENT_METADATA_VERSION_STORAGE = str(CURRENT_METADATA_VERSION)

JOB_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalize_job_id(value: Any) -> str | None:
    """Return a valid normalized job id or None."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not JOB_ID_PATTERN.fullmatch(normalized):
        return None
    return normalized


def normalize_metadata_version(value: Any) -> int | None:
    """Normalize the stored decimal-string metadata version."""
    if not isinstance(value, str) or not value.isdecimal():
        return None
    normalized = int(value)
    return normalized if normalized > 0 else None


def classify_metadata(extra_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Classify backup metadata without relying on backup names."""
    bma_marker = extra_metadata.get(METADATA_MANAGED) is True
    app_marker_present = METADATA_APP_UPDATE in extra_metadata
    metadata_version = normalize_metadata_version(extra_metadata.get(METADATA_VERSION))

    if bma_marker and app_marker_present:
        return {
            "source_type": SOURCE_UNKNOWN,
            "classification_reason": "conflicting_source_markers",
            "job_id": None,
            "app_slug": None,
            "metadata_version": metadata_version,
        }

    if bma_marker:
        raw_job_id = extra_metadata.get(METADATA_JOB_ID)
        if raw_job_id is None:
            job_id = None
            reason = "bma_legacy_no_job"
        else:
            job_id = normalize_job_id(raw_job_id)
            reason = "bma_managed" if job_id is not None else "bma_invalid_job_id"

        return {
            "source_type": SOURCE_BMA,
            "classification_reason": reason,
            "job_id": job_id,
            "app_slug": None,
            "metadata_version": metadata_version,
        }

    if app_marker_present:
        raw_slug = extra_metadata.get(METADATA_APP_UPDATE)
        app_slug = raw_slug.strip() if isinstance(raw_slug, str) else ""
        if app_slug:
            return {
                "source_type": SOURCE_APP_UPDATE,
                "classification_reason": "app_update_metadata",
                "job_id": None,
                "app_slug": app_slug,
                "metadata_version": metadata_version,
            }
        return {
            "source_type": SOURCE_UNKNOWN,
            "classification_reason": "invalid_app_update_metadata",
            "job_id": None,
            "app_slug": None,
            "metadata_version": metadata_version,
        }

    return {
        "source_type": SOURCE_HA_NATIVE,
        "classification_reason": "ha_native_default",
        "job_id": None,
        "app_slug": None,
        "metadata_version": metadata_version,
    }


def _known_size(value: Any) -> int | None:
    """Return a usable copy size or None for invalid/missing data."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def normalize_backup(backup: Any) -> dict[str, Any]:
    """Convert a ManagerBackup-like object to normalized JSON-friendly data."""
    extra_metadata = dict(backup.extra_metadata)
    classification = classify_metadata(extra_metadata)

    agents: dict[str, dict[str, Any]] = {}
    known_sizes: list[int] = []
    physical_size_complete = True

    for agent_id, status in sorted(backup.agents.items()):
        size = _known_size(getattr(status, "size", None))
        if size is None:
            physical_size_complete = False
        else:
            known_sizes.append(size)

        agents[agent_id] = {
            "protected": bool(getattr(status, "protected", False)),
            "size": size,
        }

    physical_size_bytes = sum(known_sizes)
    logical_size_bytes = max(known_sizes) if known_sizes else None
    logical_size_complete = logical_size_bytes is not None

    return {
        "backup_id": backup.backup_id,
        "name": backup.name,
        "date": backup.date,
        "homeassistant_version": backup.homeassistant_version,
        "homeassistant_included": backup.homeassistant_included,
        "database_included": backup.database_included,
        "addons": [
            {
                "slug": addon.slug,
                "name": addon.name,
                "version": addon.version,
            }
            for addon in backup.addons
        ],
        "folders": [folder.value for folder in backup.folders],
        "agents": agents,
        "failed_addons": [
            {
                "slug": addon.slug,
                "name": addon.name,
                "version": addon.version,
            }
            for addon in backup.failed_addons
        ],
        "failed_agent_ids": list(backup.failed_agent_ids),
        "failed_folders": [folder.value for folder in backup.failed_folders],
        "with_automatic_settings": backup.with_automatic_settings,
        "extra_metadata": extra_metadata,
        **classification,
        "physical_size_bytes": physical_size_bytes,
        "physical_size_complete": physical_size_complete,
        "logical_size_bytes": logical_size_bytes,
        "logical_size_complete": logical_size_complete,
    }


def _empty_source_size_summary() -> dict[str, Any]:
    """Return an empty source-size accumulator."""
    return {
        "backup_count": 0,
        "physical_size_bytes": 0,
        "physical_size_complete": True,
        "logical_size_bytes": 0,
        "logical_size_complete": True,
    }


def aggregate_inventory(
    backups: Iterable[Mapping[str, Any]],
    agents: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Aggregate normalized logical backups into snapshot-friendly summaries."""
    normalized_backups = list(backups)

    source_counts = {source_type: 0 for source_type in SOURCE_TYPES}
    bma_by_job: Counter[str] = Counter()
    app_update_by_app: Counter[str] = Counter()
    ha_native_breakdown = {
        "automatic": 0,
        "manual_or_other": 0,
    }

    per_agent: dict[str, dict[str, Any]] = {
        agent_id: {
            "name": details.get("name"),
            "domain": details.get("domain"),
            "backup_count": 0,
            "size_bytes": 0,
            "size_complete": True,
        }
        for agent_id, details in sorted(agents.items())
    }
    per_source_type = {
        source_type: _empty_source_size_summary()
        for source_type in SOURCE_TYPES
    }

    physical_total_bytes = 0
    physical_size_complete = True
    logical_size_bytes = 0
    logical_size_complete = True

    for backup in normalized_backups:
        source_type = backup.get("source_type")
        if source_type not in source_counts:
            source_type = SOURCE_UNKNOWN

        source_counts[source_type] += 1

        if source_type == SOURCE_BMA:
            bma_by_job[backup.get("job_id") or "unassigned"] += 1
        elif source_type == SOURCE_APP_UPDATE:
            app_slug = backup.get("app_slug")
            if app_slug:
                app_update_by_app[str(app_slug)] += 1
        elif source_type == SOURCE_HA_NATIVE:
            key = (
                "automatic"
                if backup.get("with_automatic_settings") is True
                else "manual_or_other"
            )
            ha_native_breakdown[key] += 1

        physical = backup.get("physical_size_bytes")
        if isinstance(physical, int) and not isinstance(physical, bool):
            physical_total_bytes += physical
        if backup.get("physical_size_complete") is not True:
            physical_size_complete = False

        logical = backup.get("logical_size_bytes")
        if isinstance(logical, int) and not isinstance(logical, bool):
            logical_size_bytes += logical
        else:
            logical_size_complete = False
        if backup.get("logical_size_complete") is not True:
            logical_size_complete = False

        source_summary = per_source_type[source_type]
        source_summary["backup_count"] += 1
        if isinstance(physical, int) and not isinstance(physical, bool):
            source_summary["physical_size_bytes"] += physical
        if backup.get("physical_size_complete") is not True:
            source_summary["physical_size_complete"] = False
        if isinstance(logical, int) and not isinstance(logical, bool):
            source_summary["logical_size_bytes"] += logical
        else:
            source_summary["logical_size_complete"] = False
        if backup.get("logical_size_complete") is not True:
            source_summary["logical_size_complete"] = False

        for agent_id, status in backup.get("agents", {}).items():
            agent_summary = per_agent.setdefault(
                agent_id,
                {
                    "name": None,
                    "domain": None,
                    "backup_count": 0,
                    "size_bytes": 0,
                    "size_complete": True,
                },
            )
            agent_summary["backup_count"] += 1
            size = status.get("size")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                agent_summary["size_bytes"] += size
            else:
                agent_summary["size_complete"] = False

    return {
        "source_counts": source_counts,
        "bma_by_job": dict(sorted(bma_by_job.items())),
        "app_update_by_app": dict(sorted(app_update_by_app.items())),
        "ha_native_breakdown": ha_native_breakdown,
        "archive_size": {
            "physical_total_bytes": physical_total_bytes,
            "physical_size_complete": physical_size_complete,
            "logical_size_bytes": logical_size_bytes,
            "logical_size_complete": logical_size_complete,
            "per_agent": dict(sorted(per_agent.items())),
            "per_source_type": per_source_type,
        },
    }
