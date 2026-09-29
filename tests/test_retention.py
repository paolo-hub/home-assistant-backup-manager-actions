"""Behavioral tests for the pure calendar retention planner."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "retention.py"

custom_components_module = types.ModuleType("custom_components")
custom_components_module.__path__ = [str(ROOT / "custom_components")]
package_module = types.ModuleType("custom_components.backup_manager_actions")
package_module.__path__ = [
    str(ROOT / "custom_components" / "backup_manager_actions")
]
sys.modules.setdefault("custom_components", custom_components_module)
sys.modules.setdefault("custom_components.backup_manager_actions", package_module)

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.retention",
    MODULE,
)
retention = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = retention
spec.loader.exec_module(retention)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
TZ = "Europe/Rome"


def backup(
    backup_id: str,
    date: str,
    *,
    source_type: str = "bma",
    job_id: str | None = "full",
    app_slug: str | None = None,
    agents: dict | None = None,
) -> dict:
    """Build one normalized logical backup."""
    return {
        "backup_id": backup_id,
        "name": backup_id,
        "date": date,
        "source_type": source_type,
        "job_id": job_id,
        "app_slug": app_slug,
        "agents": agents
        if agents is not None
        else {
            "local": {
                "protected": False,
                "size": 100,
            }
        },
    }


def plan(
    backups,
    *,
    source_type="bma",
    job_id="full",
    group_by=None,
    scope_agent_ids=("local",),
    keep_last=1,
    daily=0,
    weekly=0,
    monthly=0,
    yearly=0,
    now=NOW,
):
    """Call the planner with concise defaults."""
    return retention.plan_retention(
        backups,
        source_type=source_type,
        job_id=job_id,
        group_by=group_by,
        scope_agent_ids=scope_agent_ids,
        keep_last=keep_last,
        daily=daily,
        weekly=weekly,
        monthly=monthly,
        yearly=yearly,
        now=now,
        timezone_name=TZ,
    )


def ids(items):
    """Return backup ids from one result list."""
    return [item["backup_id"] for item in items]


def find_item(items, backup_id):
    """Return one result item by backup id."""
    return next(item for item in items if item["backup_id"] == backup_id)


def test_policy_validation() -> None:
    """Reject unsafe or contradictory policy combinations."""
    try:
        plan([], keep_last=0)
    except retention.RetentionPolicyError as err:
        assert "At least one retention counter" in str(err)
    else:
        raise AssertionError("Zero retention policy should fail")

    try:
        plan([], source_type="bma", job_id=None)
    except retention.RetentionPolicyError as err:
        assert "job_id is required" in str(err)
    else:
        raise AssertionError("BMA without job_id should fail")

    try:
        plan(
            [],
            source_type="ha_native",
            job_id=None,
            group_by="all",
        )
    except retention.RetentionPolicyError as err:
        assert "group_by is not allowed" in str(err)
    else:
        raise AssertionError("HA Native group_by should fail")

    app = plan(
        [],
        source_type="app_update",
        job_id=None,
        group_by=None,
    )
    assert app["scope"]["group_by"] == "app"


def test_keep_last_and_equal_date_tie_break() -> None:
    """Keep newest backups and use backup_id descending for equal dates."""
    same = "2026-09-29T10:00:00+02:00"
    result = plan(
        [
            backup("a", same),
            backup("c", same),
            backup("b", same),
            backup("old", "2026-09-28T10:00:00+02:00"),
        ],
        keep_last=2,
    )

    assert set(ids(result["keep"])) == {"c", "b"}
    assert ids(result["delete"]) == ["old", "a"]
    assert result["summary"]["keep"] == 2
    assert result["summary"]["delete"] == 2


def test_daily_calendar_buckets_and_no_backfill() -> None:
    """Use actual calendar days and never search farther for empty buckets."""
    result = plan(
        [
            backup("today-old", "2026-09-29T08:00:00+02:00"),
            backup("today-new", "2026-09-29T11:00:00+02:00"),
            backup("d-2", "2026-09-27T12:00:00+02:00"),
            backup("d-8", "2026-09-21T12:00:00+02:00"),
        ],
        keep_last=0,
        daily=3,
    )

    assert set(ids(result["keep"])) == {"today-new", "d-2"}
    assert set(ids(result["delete"])) == {"today-old", "d-8"}
    assert find_item(result["keep"], "today-new")["reasons"] == [
        "daily:2026-09-29"
    ]
    assert find_item(result["keep"], "d-2")["reasons"] == [
        "daily:2026-09-27"
    ]


def test_iso_week_buckets_across_year_boundary() -> None:
    """Keep the newest backup in each selected ISO week across New Year."""
    now = datetime(2027, 1, 5, 12, 0, tzinfo=timezone.utc)
    result = plan(
        [
            backup("w01-old", "2027-01-04T08:00:00+01:00"),
            backup("w01-new", "2027-01-05T08:00:00+01:00"),
            backup("w53", "2027-01-03T08:00:00+01:00"),
            backup("w52", "2026-12-27T08:00:00+01:00"),
        ],
        keep_last=0,
        weekly=2,
        now=now,
    )

    assert set(ids(result["keep"])) == {"w01-new", "w53"}
    assert find_item(result["keep"], "w01-new")["reasons"] == [
        "weekly:2027-W01"
    ]
    assert find_item(result["keep"], "w53")["reasons"] == [
        "weekly:2026-W53"
    ]
    assert set(ids(result["delete"])) == {"w01-old", "w52"}


def test_monthly_and_yearly_calendar_buckets() -> None:
    """Select newest backups in current/previous months and years."""
    result = plan(
        [
            backup("sep-old", "2026-09-01T10:00:00+02:00"),
            backup("sep-new", "2026-09-20T10:00:00+02:00"),
            backup("aug", "2026-08-20T10:00:00+02:00"),
            backup("jul", "2026-07-20T10:00:00+02:00"),
            backup("y2025", "2025-12-20T10:00:00+01:00"),
            backup("y2024", "2024-12-20T10:00:00+01:00"),
        ],
        keep_last=0,
        monthly=2,
        yearly=2,
    )

    assert set(ids(result["keep"])) == {"sep-new", "aug", "y2025"}
    sep_reasons = set(find_item(result["keep"], "sep-new")["reasons"])
    assert sep_reasons == {"monthly:2026-09", "yearly:2026"}
    assert find_item(result["keep"], "aug")["reasons"] == [
        "monthly:2026-08"
    ]
    assert find_item(result["keep"], "y2025")["reasons"] == [
        "yearly:2025"
    ]
    assert set(ids(result["delete"])) == {"sep-old", "jul", "y2024"}


def test_union_and_deduplicated_reasons() -> None:
    """One backup can satisfy multiple rules but appears only once."""
    result = plan(
        [
            backup("new", "2026-09-29T11:00:00+02:00"),
            backup("old", "2026-09-20T11:00:00+02:00"),
        ],
        keep_last=1,
        daily=1,
        weekly=1,
        monthly=1,
        yearly=1,
    )

    assert ids(result["keep"]) == ["new"]
    assert set(result["keep"][0]["reasons"]) == {
        "keep_last",
        "daily:2026-09-29",
        "weekly:2026-W40",
        "monthly:2026-09",
        "yearly:2026",
    }
    assert ids(result["delete"]) == ["old"]


def test_protected_backup_is_additional_to_quota() -> None:
    """Protected backups never consume keep_last or GFS quota."""
    result = plan(
        [
            backup(
                "new-protected",
                "2026-09-29T11:00:00+02:00",
                agents={
                    "local": {
                        "protected": True,
                        "size": 100,
                    }
                },
            ),
            backup("new-unprotected", "2026-09-29T10:00:00+02:00"),
            backup("old", "2026-09-28T10:00:00+02:00"),
        ],
        keep_last=1,
    )

    assert ids(result["protected"]) == ["new-protected"]
    assert ids(result["keep"]) == ["new-unprotected"]
    assert ids(result["delete"]) == ["old"]
    assert result["summary"]["protected"] == 1


def test_agent_scope_and_reclaimable_size() -> None:
    """Only in-scope copies affect protection and reclaimable bytes."""
    result = plan(
        [
            backup(
                "mixed",
                "2026-09-28T10:00:00+02:00",
                agents={
                    "local": {"protected": False, "size": 100},
                    "cloud": {"protected": True, "size": 120},
                },
            ),
            backup(
                "cloud-only",
                "2026-09-27T10:00:00+02:00",
                agents={
                    "cloud": {"protected": False, "size": 130},
                },
            ),
            backup(
                "keep",
                "2026-09-29T10:00:00+02:00",
                agents={
                    "local": {"protected": False, "size": 140},
                },
            ),
        ],
        scope_agent_ids=("local",),
        keep_last=1,
    )

    delete = find_item(result["delete"], "mixed")
    assert delete["target_agent_ids"] == ["local"]
    assert delete["reclaimable_size_bytes"] == 100
    assert delete["reclaimable_size_complete"] is True
    assert result["summary"]["out_of_scope"] == 1
    assert result["skipped"] == [
        {
            "backup_id": "cloud-only",
            "reason": "no_in_scope_copy",
        }
    ]


def test_missing_copy_size_marks_reclaimable_incomplete() -> None:
    """Unknown target copy sizes do not masquerade as exact bytes."""
    result = plan(
        [
            backup("keep", "2026-09-29T10:00:00+02:00"),
            backup(
                "delete",
                "2026-09-28T10:00:00+02:00",
                agents={
                    "local": {"protected": False, "size": None},
                    "nas": {"protected": False, "size": 200},
                },
            ),
        ],
        scope_agent_ids=("local", "nas"),
        keep_last=1,
    )

    item = result["delete"][0]
    assert item["reclaimable_size_bytes"] == 200
    assert item["reclaimable_size_complete"] is False
    assert result["summary"]["reclaimable_size_bytes"] == 200
    assert result["summary"]["reclaimable_size_complete"] is False


def test_bma_job_filter_and_legacy_exclusion() -> None:
    """Only the requested BMA job participates in its retention policy."""
    result = plan(
        [
            backup("full-new", "2026-09-29T10:00:00+02:00", job_id="full"),
            backup("full-old", "2026-09-28T10:00:00+02:00", job_id="full"),
            backup(
                "partial",
                "2026-09-27T10:00:00+02:00",
                job_id="partial",
            ),
            backup("legacy", "2026-09-26T10:00:00+02:00", job_id=None),
        ],
        keep_last=1,
    )

    assert ids(result["keep"]) == ["full-new"]
    assert ids(result["delete"]) == ["full-old"]
    assert result["summary"]["considered"] == 2


def test_ha_native_mixes_manual_and_automatic() -> None:
    """Native automatic/manual metadata does not split retention groups."""
    backups = [
        {
            **backup(
                "native-new",
                "2026-09-29T10:00:00+02:00",
                source_type="ha_native",
                job_id=None,
            ),
            "with_automatic_settings": True,
        },
        {
            **backup(
                "native-old",
                "2026-09-28T10:00:00+02:00",
                source_type="ha_native",
                job_id=None,
            ),
            "with_automatic_settings": False,
        },
    ]
    result = plan(
        backups,
        source_type="ha_native",
        job_id=None,
        keep_last=1,
    )

    assert ids(result["keep"]) == ["native-new"]
    assert ids(result["delete"]) == ["native-old"]
    assert result["keep"][0]["group"] == "ha_native"


def test_app_group_by_app() -> None:
    """Each App gets an independent retention quota."""
    backups = [
        backup(
            "a-new",
            "2026-09-29T10:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_a",
        ),
        backup(
            "a-old",
            "2026-09-28T10:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_a",
        ),
        backup(
            "b-new",
            "2026-09-29T09:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_b",
        ),
        backup(
            "b-old",
            "2026-09-27T10:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_b",
        ),
    ]
    result = plan(
        backups,
        source_type="app_update",
        job_id=None,
        group_by="app",
        keep_last=1,
    )

    assert set(ids(result["keep"])) == {"a-new", "b-new"}
    assert set(ids(result["delete"])) == {"a-old", "b-old"}
    assert {item["group"] for item in result["keep"]} == {
        "addon_a",
        "addon_b",
    }


def test_app_group_by_all() -> None:
    """Global App Update policy makes all Apps compete together."""
    backups = [
        backup(
            "a-new",
            "2026-09-29T10:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_a",
        ),
        backup(
            "b-newer",
            "2026-09-29T11:00:00+02:00",
            source_type="app_update",
            job_id=None,
            app_slug="addon_b",
        ),
    ]
    result = plan(
        backups,
        source_type="app_update",
        job_id=None,
        group_by="all",
        keep_last=1,
    )

    assert ids(result["keep"]) == ["b-newer"]
    assert ids(result["delete"]) == ["a-new"]
    assert result["keep"][0]["group"] == "all"


def test_timezone_controls_calendar_bucket() -> None:
    """Bucket assignment follows Home Assistant local time, not source offset."""
    result = plan(
        [
            backup("keep", "2026-09-28T23:30:00Z"),
            backup("old", "2026-09-27T23:30:00Z"),
        ],
        keep_last=0,
        daily=1,
    )

    assert ids(result["keep"]) == ["keep"]
    assert find_item(result["keep"], "keep")["reasons"] == [
        "daily:2026-09-29"
    ]
    assert ids(result["delete"]) == ["old"]


def test_invalid_target_date_fails_closed() -> None:
    """Malformed dates in target inventory stop planning."""
    try:
        plan([backup("bad", "not-a-date")])
    except retention.RetentionPolicyError as err:
        assert "Invalid backup date" in str(err)
    else:
        raise AssertionError("Invalid backup date should fail")


def main() -> None:
    test_policy_validation()
    test_keep_last_and_equal_date_tie_break()
    test_daily_calendar_buckets_and_no_backfill()
    test_iso_week_buckets_across_year_boundary()
    test_monthly_and_yearly_calendar_buckets()
    test_union_and_deduplicated_reasons()
    test_protected_backup_is_additional_to_quota()
    test_agent_scope_and_reclaimable_size()
    test_missing_copy_size_marks_reclaimable_incomplete()
    test_bma_job_filter_and_legacy_exclusion()
    test_ha_native_mixes_manual_and_automatic()
    test_app_group_by_app()
    test_app_group_by_all()
    test_timezone_controls_calendar_bucket()
    test_invalid_target_date_fails_closed()
    print("retention planner simulation: OK")


if __name__ == "__main__":
    main()
