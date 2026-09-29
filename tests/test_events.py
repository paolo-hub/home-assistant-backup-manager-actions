"""Behavioral tests for new-backup event tracking."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "events.py"

custom_components_module = types.ModuleType("custom_components")
custom_components_module.__path__ = [str(ROOT / "custom_components")]
package_module = types.ModuleType("custom_components.backup_manager_actions")
package_module.__path__ = [
    str(ROOT / "custom_components" / "backup_manager_actions")
]

sys.modules.setdefault("custom_components", custom_components_module)
sys.modules.setdefault("custom_components.backup_manager_actions", package_module)

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.events",
    MODULE,
)
events = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = events
spec.loader.exec_module(events)


def backup(
    backup_id: str,
    source_type: str,
    *,
    date: str,
    job_id: str | None = None,
    app_slug: str | None = None,
    agents: dict | None = None,
) -> dict:
    """Build one normalized backup for event tracking."""
    return {
        "backup_id": backup_id,
        "name": f"Backup {backup_id}",
        "date": date,
        "source_type": source_type,
        "job_id": job_id,
        "app_slug": app_slug,
        "agents": agents
        if agents is not None
        else {
            "local": {
                "size": 100,
                "protected": False,
            }
        },
        "failed_agent_ids": [],
        "with_automatic_settings": False,
    }


def verified_create_result(backup_id: str = "bma-new") -> dict:
    """Build one verified BMA create result."""
    return {
        "backup_id": backup_id,
        "backup_job_id": "native-job",
        "name": "BMA Full",
        "date": "2026-09-29T11:00:00+02:00",
        "source_type": "bma",
        "job_id": "full",
        "metadata_version": 1,
        "failed_agent_ids": [],
        "with_automatic_settings": False,
        "requested_agent_ids": ["local", "cloud"],
        "stored_agent_ids": ["cloud", "local"],
        "protected_by_agent": {
            "local": False,
            "cloud": True,
        },
        "size_by_agent": {
            "local": 100,
            "cloud": 120,
        },
    }


def test_startup_baseline_does_not_replay_history() -> None:
    """The first complete inventory is only a startup baseline."""
    tracker = events.BackupCreatedEventTracker()
    historical = [
        backup(
            "native-old",
            "ha_native",
            date="2026-09-27T09:00:00+02:00",
        ),
        backup(
            "app-old",
            "app_update",
            app_slug="core_mosquitto",
            date="2026-09-28T09:00:00+02:00",
        ),
        backup(
            "bma-old",
            "bma",
            job_id="full",
            date="2026-09-29T09:00:00+02:00",
        ),
    ]

    assert tracker.process_complete_inventory(historical) == []
    assert tracker.baseline_ready is True


def test_external_new_backup_emits_once() -> None:
    """A new native logical id emits exactly one event."""
    tracker = events.BackupCreatedEventTracker()
    old = backup(
        "old",
        "ha_native",
        date="2026-09-29T09:00:00+02:00",
    )
    new = backup(
        "new",
        "ha_native",
        date="2026-09-29T10:00:00+02:00",
    )

    assert tracker.process_complete_inventory([old]) == []
    emitted = tracker.process_complete_inventory([old, new])
    assert len(emitted) == 1
    assert emitted[0]["backup_id"] == "new"
    assert emitted[0]["source_type"] == "ha_native"

    assert tracker.process_complete_inventory([old, new]) == []


def test_app_update_payload_and_agent_copy_deduplication() -> None:
    """A later copy on another agent does not recreate the logical event."""
    tracker = events.BackupCreatedEventTracker()
    assert tracker.process_complete_inventory([]) == []

    first = backup(
        "app-new",
        "app_update",
        app_slug="core_mosquitto",
        date="2026-09-29T10:00:00+02:00",
        agents={
            "local": {
                "size": 100,
                "protected": False,
            }
        },
    )
    emitted = tracker.process_complete_inventory([first])
    assert len(emitted) == 1
    assert emitted[0]["app_slug"] == "core_mosquitto"
    assert emitted[0]["agent_ids"] == ["local"]

    second_copy = backup(
        "app-new",
        "app_update",
        app_slug="core_mosquitto",
        date="2026-09-29T10:00:00+02:00",
        agents={
            "cloud": {
                "size": 120,
                "protected": False,
            },
            "local": {
                "size": 100,
                "protected": False,
            },
        },
    )
    assert tracker.process_complete_inventory([second_copy]) == []


def test_multiple_external_backups_emit_in_chronological_order() -> None:
    """Multiple ids discovered together are emitted deterministically."""
    tracker = events.BackupCreatedEventTracker()
    assert tracker.process_complete_inventory([]) == []

    later = backup(
        "z-later",
        "ha_native",
        date="2026-09-29T12:00:00+02:00",
    )
    earlier = backup(
        "a-earlier",
        "app_update",
        app_slug="addon_a",
        date="2026-09-29T11:00:00+02:00",
    )

    emitted = tracker.process_complete_inventory([later, earlier])
    assert [item["backup_id"] for item in emitted] == [
        "a-earlier",
        "z-later",
    ]


def test_external_events_order_by_real_instant_across_offsets() -> None:
    """DST offsets must not invert chronological event ordering."""
    tracker = events.BackupCreatedEventTracker()
    assert tracker.process_complete_inventory([]) == []

    earlier = backup(
        "earlier-real-time",
        "ha_native",
        date="2026-10-25T02:30:00+02:00",
    )
    later = backup(
        "later-real-time",
        "ha_native",
        date="2026-10-25T02:15:00+01:00",
    )

    emitted = tracker.process_complete_inventory([later, earlier])
    assert [item["backup_id"] for item in emitted] == [
        "earlier-real-time",
        "later-real-time",
    ]


def test_bma_and_unknown_discovery_do_not_emit_external_events() -> None:
    """Only HA Native and App Update are discovery-driven in 1.1."""
    tracker = events.BackupCreatedEventTracker()
    assert tracker.process_complete_inventory([]) == []

    bma = backup(
        "bma-new",
        "bma",
        job_id="full",
        date="2026-09-29T11:00:00+02:00",
    )
    unknown = backup(
        "unknown-new",
        "unknown",
        date="2026-09-29T11:01:00+02:00",
    )

    assert tracker.process_complete_inventory([bma, unknown]) == []


def test_verified_bma_create_emits_after_early_inventory_visibility() -> None:
    """Seeing an in-flight BMA backup must not suppress its verified event."""
    tracker = events.BackupCreatedEventTracker()
    assert tracker.process_complete_inventory([]) == []

    discovered_early = backup(
        "bma-new",
        "bma",
        job_id="full",
        date="2026-09-29T11:00:00+02:00",
    )
    assert tracker.process_complete_inventory([discovered_early]) == []

    emitted = tracker.record_verified_bma_create(verified_create_result())
    assert emitted is not None
    assert emitted["backup_id"] == "bma-new"
    assert emitted["job_id"] == "full"
    assert emitted["agent_ids"] == ["cloud", "local"]
    assert emitted["size_by_agent"] == {
        "cloud": 120,
        "local": 100,
    }
    assert emitted["protected_by_agent"] == {
        "cloud": True,
        "local": False,
    }

    assert tracker.record_verified_bma_create(verified_create_result()) is None
    assert tracker.process_complete_inventory([discovered_early]) == []


def test_bma_visible_in_first_complete_snapshot_still_emits_after_verification() -> None:
    """Startup baseline must not suppress an in-flight verified BMA create."""
    tracker = events.BackupCreatedEventTracker()

    in_flight = backup(
        "bma-new",
        "bma",
        job_id="full",
        date="2026-09-29T11:00:00+02:00",
    )

    assert tracker.process_complete_inventory([in_flight]) == []
    assert tracker.baseline_ready is True

    emitted = tracker.record_verified_bma_create(verified_create_result())
    assert emitted is not None
    assert emitted["backup_id"] == "bma-new"

    assert tracker.record_verified_bma_create(verified_create_result()) is None


def test_verified_bma_before_baseline_is_not_replayed() -> None:
    """A verified create can safely race with the coordinator first refresh."""
    tracker = events.BackupCreatedEventTracker()

    emitted = tracker.record_verified_bma_create(verified_create_result())
    assert emitted is not None

    current = backup(
        "bma-new",
        "bma",
        job_id="full",
        date="2026-09-29T11:00:00+02:00",
    )
    assert tracker.process_complete_inventory([current]) == []
    assert tracker.baseline_ready is True
    assert tracker.record_verified_bma_create(verified_create_result()) is None


def main() -> None:
    test_startup_baseline_does_not_replay_history()
    test_external_new_backup_emits_once()
    test_app_update_payload_and_agent_copy_deduplication()
    test_multiple_external_backups_emit_in_chronological_order()
    test_external_events_order_by_real_instant_across_offsets()
    test_bma_and_unknown_discovery_do_not_emit_external_events()
    test_verified_bma_create_emits_after_early_inventory_visibility()
    test_bma_visible_in_first_complete_snapshot_still_emits_after_verification()
    test_verified_bma_before_baseline_is_not_replayed()
    print("event tracker simulation: OK")


if __name__ == "__main__":
    main()
