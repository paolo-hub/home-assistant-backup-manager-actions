"""Pure calendar-based retention planning for Backup Manager Actions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .inventory import (
    SOURCE_APP_UPDATE,
    SOURCE_BMA,
    SOURCE_HA_NATIVE,
    normalize_job_id,
)

RETENTION_SOURCE_TYPES = frozenset(
    {
        SOURCE_BMA,
        SOURCE_HA_NATIVE,
        SOURCE_APP_UPDATE,
    }
)
APP_GROUP_BY_APP = "app"
APP_GROUP_BY_ALL = "all"
APP_GROUP_BY_VALUES = frozenset({APP_GROUP_BY_APP, APP_GROUP_BY_ALL})


class RetentionPolicyError(ValueError):
    """Raised when a retention policy or target inventory is unsafe."""


def normalize_retention_counter(value: Any) -> int:
    """Normalize one public retention counter without truncating fractions."""
    error = "Retention counters must be integers >= 0"

    if isinstance(value, bool):
        raise RetentionPolicyError(error)

    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise RetentionPolicyError(error)
        normalized = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped.isascii() or not stripped.isdecimal():
            raise RetentionPolicyError(error)
        normalized = int(stripped)
    else:
        raise RetentionPolicyError(error)

    if normalized < 0:
        raise RetentionPolicyError(error)
    return normalized


def validate_retention_policy(
    *,
    source_type: str,
    job_id: str | None,
    group_by: str | None,
    keep_last: int,
    daily: int,
    weekly: int,
    monthly: int,
    yearly: int,
) -> tuple[str | None, str | None]:
    """Validate policy combinations and return normalized job/group values."""
    if source_type not in RETENTION_SOURCE_TYPES:
        raise RetentionPolicyError(
            "source_type must be one of: bma, ha_native, app_update"
        )

    counters = {
        "keep_last": keep_last,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "yearly": yearly,
    }
    for name, value in counters.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RetentionPolicyError(f"{name} must be an integer >= 0")
    if not any(counters.values()):
        raise RetentionPolicyError(
            "At least one retention counter must be greater than zero"
        )

    normalized_job_id: str | None = None
    normalized_group_by: str | None = None

    if source_type == SOURCE_BMA:
        normalized_job_id = normalize_job_id(job_id)
        if normalized_job_id is None:
            raise RetentionPolicyError(
                "job_id is required for source_type=bma and must match "
                "^[a-z0-9][a-z0-9_-]{0,63}$"
            )
        if group_by is not None:
            raise RetentionPolicyError(
                "group_by is not allowed for source_type=bma"
            )

    elif source_type == SOURCE_HA_NATIVE:
        if job_id is not None:
            raise RetentionPolicyError(
                "job_id is not allowed for source_type=ha_native"
            )
        if group_by is not None:
            raise RetentionPolicyError(
                "group_by is not allowed for source_type=ha_native"
            )

    else:
        if job_id is not None:
            raise RetentionPolicyError(
                "job_id is not allowed for source_type=app_update"
            )
        normalized_group_by = group_by or APP_GROUP_BY_APP
        if normalized_group_by not in APP_GROUP_BY_VALUES:
            raise RetentionPolicyError(
                "group_by must be app or all for source_type=app_update"
            )

    return normalized_job_id, normalized_group_by


def _parse_backup_datetime(value: Any, timezone: ZoneInfo) -> datetime:
    """Parse and convert a backup timestamp into the configured HA timezone."""
    if not isinstance(value, str) or not value.strip():
        raise RetentionPolicyError("Backup date is missing or invalid")

    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as err:
        raise RetentionPolicyError(f"Invalid backup date: {value}") from err

    if parsed.tzinfo is None:
        raise RetentionPolicyError(
            f"Backup date must include timezone information: {value}"
        )
    return parsed.astimezone(timezone)


def _month_index(value: datetime) -> int:
    """Return a monotonic calendar-month index."""
    return value.year * 12 + (value.month - 1)


def _previous_month_keys(now_local: datetime, count: int) -> set[tuple[int, int]]:
    """Return current and previous calendar month keys."""
    current = _month_index(now_local)
    result: set[tuple[int, int]] = set()
    for offset in range(count):
        index = current - offset
        year, month_zero = divmod(index, 12)
        result.add((year, month_zero + 1))
    return result


def _previous_years(now_local: datetime, count: int) -> set[int]:
    """Return current and previous calendar years."""
    return {now_local.year - offset for offset in range(count)}


def _previous_days(now_local: datetime, count: int) -> set[str]:
    """Return current and previous local calendar dates as ISO strings."""
    return {
        (now_local.date() - timedelta(days=offset)).isoformat()
        for offset in range(count)
    }


def _previous_iso_weeks(
    now_local: datetime,
    count: int,
) -> set[tuple[int, int]]:
    """Return current and previous ISO week keys."""
    monday = now_local.date() - timedelta(days=now_local.weekday())
    result: set[tuple[int, int]] = set()
    for offset in range(count):
        candidate = monday - timedelta(weeks=offset)
        iso = candidate.isocalendar()
        result.add((iso.year, iso.week))
    return result


def _backup_sort_key(item: Mapping[str, Any]) -> tuple[datetime, str]:
    """Return the precomputed deterministic backup sort key."""
    return item["_retention_local_date"], str(item["backup_id"])


def _group_name(
    backup: Mapping[str, Any],
    *,
    source_type: str,
    job_id: str | None,
    group_by: str | None,
) -> str:
    """Return the retention group for one already-matched backup."""
    if source_type == SOURCE_BMA:
        assert job_id is not None
        return job_id
    if source_type == SOURCE_HA_NATIVE:
        return SOURCE_HA_NATIVE
    if group_by == APP_GROUP_BY_ALL:
        return APP_GROUP_BY_ALL

    app_slug = backup.get("app_slug")
    if not isinstance(app_slug, str) or not app_slug.strip():
        raise RetentionPolicyError(
            f"App Update backup {backup.get('backup_id')} has no valid app_slug"
        )
    return app_slug.strip()


def _matches_policy_source(
    backup: Mapping[str, Any],
    *,
    source_type: str,
    job_id: str | None,
) -> bool:
    """Return whether a normalized backup belongs to the requested class."""
    if backup.get("source_type") != source_type:
        return False
    if source_type == SOURCE_BMA:
        return backup.get("job_id") == job_id
    return True


def _scope_backup(
    backup: Mapping[str, Any],
    scope_agent_ids: set[str],
) -> tuple[list[str], bool]:
    """Return target copies and whether any in-scope copy is protected."""
    agents = backup.get("agents")
    if not isinstance(agents, Mapping):
        raise RetentionPolicyError(
            f"Backup {backup.get('backup_id')} has invalid agent data"
        )

    target_agent_ids = sorted(scope_agent_ids.intersection(agents))
    protected = any(
        bool(agents[agent_id].get("protected", False))
        for agent_id in target_agent_ids
    )
    return target_agent_ids, protected


def _reclaimable_size(
    backup: Mapping[str, Any],
    target_agent_ids: list[str],
) -> tuple[int, bool]:
    """Return known bytes and completeness for copies inside the scope."""
    agents = backup["agents"]
    total = 0
    complete = True
    for agent_id in target_agent_ids:
        size = agents[agent_id].get("size")
        if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
            total += size
        else:
            complete = False
    return total, complete


def _plan_group(
    backups: list[dict[str, Any]],
    *,
    group: str,
    now_local: datetime,
    keep_last: int,
    daily: int,
    weekly: int,
    monthly: int,
    yearly: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Plan one independent retention group."""
    protected: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []

    for backup in backups:
        if backup["_retention_protected"]:
            protected.append(backup)
        else:
            eligible.append(backup)

    protected.sort(key=_backup_sort_key, reverse=True)
    eligible.sort(key=_backup_sort_key, reverse=True)

    reasons: dict[str, set[str]] = defaultdict(set)
    by_id = {str(item["backup_id"]): item for item in eligible}

    for backup in eligible[:keep_last]:
        reasons[str(backup["backup_id"])].add("keep_last")

    selected_days = _previous_days(now_local, daily)
    selected_weeks = _previous_iso_weeks(now_local, weekly)
    selected_months = _previous_month_keys(now_local, monthly)
    selected_years = _previous_years(now_local, yearly)

    seen_days: set[str] = set()
    seen_weeks: set[tuple[int, int]] = set()
    seen_months: set[tuple[int, int]] = set()
    seen_years: set[int] = set()

    for backup in eligible:
        backup_id = str(backup["backup_id"])
        local_date: datetime = backup["_retention_local_date"]

        if daily:
            day_key = local_date.date().isoformat()
            if day_key in selected_days and day_key not in seen_days:
                reasons[backup_id].add(f"daily:{day_key}")
                seen_days.add(day_key)

        if weekly:
            iso = local_date.isocalendar()
            week_key = (iso.year, iso.week)
            if week_key in selected_weeks and week_key not in seen_weeks:
                reasons[backup_id].add(
                    f"weekly:{iso.year}-W{iso.week:02d}"
                )
                seen_weeks.add(week_key)

        if monthly:
            month_key = (local_date.year, local_date.month)
            if month_key in selected_months and month_key not in seen_months:
                reasons[backup_id].add(
                    f"monthly:{local_date.year}-{local_date.month:02d}"
                )
                seen_months.add(month_key)

        if yearly:
            year_key = local_date.year
            if year_key in selected_years and year_key not in seen_years:
                reasons[backup_id].add(f"yearly:{year_key}")
                seen_years.add(year_key)

    keep: list[dict[str, Any]] = []
    delete: list[dict[str, Any]] = []

    for backup in eligible:
        backup_id = str(backup["backup_id"])
        if backup_id in reasons:
            keep.append(
                {
                    "backup_id": backup_id,
                    "group": group,
                    "reasons": sorted(reasons[backup_id]),
                }
            )
            continue

        reclaimable_bytes, reclaimable_complete = _reclaimable_size(
            backup,
            backup["_retention_target_agent_ids"],
        )
        delete.append(
            {
                "backup_id": backup_id,
                "group": group,
                "date": backup["date"],
                "target_agent_ids": list(
                    backup["_retention_target_agent_ids"]
                ),
                "reclaimable_size_bytes": reclaimable_bytes,
                "reclaimable_size_complete": reclaimable_complete,
            }
        )

    protected_result = [
        {
            "backup_id": str(backup["backup_id"]),
            "group": group,
            "reasons": ["protected"],
            "protected_agent_ids": [
                agent_id
                for agent_id in backup["_retention_target_agent_ids"]
                if bool(backup["agents"][agent_id].get("protected", False))
            ],
        }
        for backup in protected
    ]

    # Apply executes deletion oldest first.
    delete.sort(
        key=lambda item: (
            by_id.get(item["backup_id"], {}).get(
                "_retention_local_date",
                datetime.max.replace(tzinfo=now_local.tzinfo),
            ),
            item["backup_id"],
        )
    )

    return keep, protected_result, delete


def plan_retention(
    backups: Iterable[Mapping[str, Any]],
    *,
    source_type: str,
    job_id: str | None,
    group_by: str | None,
    scope_agent_ids: Iterable[str],
    keep_last: int,
    daily: int,
    weekly: int,
    monthly: int,
    yearly: int,
    now: datetime,
    timezone_name: str,
) -> dict[str, Any]:
    """Build a deterministic, read-only retention plan."""
    normalized_job_id, normalized_group_by = validate_retention_policy(
        source_type=source_type,
        job_id=job_id,
        group_by=group_by,
        keep_last=keep_last,
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        yearly=yearly,
    )

    if now.tzinfo is None:
        raise RetentionPolicyError("now must be timezone-aware")

    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as err:
        raise RetentionPolicyError(
            f"Unknown Home Assistant timezone: {timezone_name}"
        ) from err

    now_local = now.astimezone(timezone)
    scope = sorted({str(agent_id) for agent_id in scope_agent_ids})
    if not scope or any(not agent_id for agent_id in scope):
        raise RetentionPolicyError(
            "Retention agent scope must contain at least one valid agent id"
        )
    scope_set = set(scope)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: list[dict[str, Any]] = []
    out_of_scope = 0

    for original in backups:
        backup = dict(original)
        if not _matches_policy_source(
            backup,
            source_type=source_type,
            job_id=normalized_job_id,
        ):
            continue

        backup_id = backup.get("backup_id")
        if not isinstance(backup_id, str) or not backup_id:
            raise RetentionPolicyError(
                "A retention candidate has no valid backup_id"
            )

        target_agent_ids, protected = _scope_backup(backup, scope_set)
        if not target_agent_ids:
            out_of_scope += 1
            skipped.append(
                {
                    "backup_id": backup_id,
                    "reason": "no_in_scope_copy",
                }
            )
            continue

        backup["_retention_local_date"] = _parse_backup_datetime(
            backup.get("date"),
            timezone,
        )
        backup["_retention_target_agent_ids"] = target_agent_ids
        backup["_retention_protected"] = protected
        group = _group_name(
            backup,
            source_type=source_type,
            job_id=normalized_job_id,
            group_by=normalized_group_by,
        )
        grouped[group].append(backup)

    keep_result: list[dict[str, Any]] = []
    protected_result: list[dict[str, Any]] = []
    delete_result: list[dict[str, Any]] = []

    for group in sorted(grouped):
        keep, protected, delete = _plan_group(
            grouped[group],
            group=group,
            now_local=now_local,
            keep_last=keep_last,
            daily=daily,
            weekly=weekly,
            monthly=monthly,
            yearly=yearly,
        )
        keep_result.extend(keep)
        protected_result.extend(protected)
        delete_result.extend(delete)

    keep_result.sort(key=lambda item: (item["group"], item["backup_id"]))
    protected_result.sort(
        key=lambda item: (item["group"], item["backup_id"])
    )

    local_date_by_id = {
        str(backup["backup_id"]): backup["_retention_local_date"]
        for group_backups in grouped.values()
        for backup in group_backups
    }
    delete_result.sort(
        key=lambda item: (
            local_date_by_id[item["backup_id"]],
            item["backup_id"],
        )
    )

    reclaimable_size_bytes = sum(
        item["reclaimable_size_bytes"]
        for item in delete_result
    )
    reclaimable_size_complete = all(
        item["reclaimable_size_complete"]
        for item in delete_result
    )

    considered = (
        len(keep_result)
        + len(protected_result)
        + len(delete_result)
    )

    return {
        "evaluated_at": now_local.isoformat(),
        "timezone": timezone_name,
        "scope": {
            "source_type": source_type,
            "job_id": normalized_job_id,
            "group_by": normalized_group_by,
            "agent_ids": scope,
        },
        "policy": {
            "keep_last": keep_last,
            "daily": daily,
            "weekly": weekly,
            "monthly": monthly,
            "yearly": yearly,
        },
        "summary": {
            "considered": considered,
            "protected": len(protected_result),
            "keep": len(keep_result),
            "delete": len(delete_result),
            "out_of_scope": out_of_scope,
            "reclaimable_size_bytes": reclaimable_size_bytes,
            "reclaimable_size_complete": reclaimable_size_complete,
        },
        "keep": keep_result,
        "protected": protected_result,
        "delete": delete_result,
        "skipped": sorted(
            skipped,
            key=lambda item: item["backup_id"],
        ),
    }
