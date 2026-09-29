"""Behavioral tests for normalized backup inventory helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "inventory.py"

spec = importlib.util.spec_from_file_location("backup_manager_actions_inventory", MODULE)
inventory = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = inventory
spec.loader.exec_module(inventory)


class Folder(StrEnum):
    SHARE = "share"
    SSL = "ssl"


@dataclass
class Status:
    protected: bool
    size: int | None


@dataclass
class Addon:
    slug: str
    name: str | None = None
    version: str | None = None


@dataclass
class Backup:
    addons: list
    backup_id: str
    date: str
    database_included: bool
    extra_metadata: dict
    failed_addons: list
    failed_agent_ids: list
    failed_folders: list
    folders: list
    homeassistant_included: bool
    homeassistant_version: str | None
    name: str
    with_automatic_settings: bool | None
    agents: dict


def make_backup(
    backup_id: str,
    *,
    metadata: dict | None = None,
    date: str = "2026-09-29T10:00:00+02:00",
    automatic: bool | None = False,
    agents: dict | None = None,
) -> Backup:
    """Build a backup stub with realistic defaults."""
    return Backup(
        addons=[],
        backup_id=backup_id,
        date=date,
        database_included=True,
        extra_metadata=metadata or {},
        failed_addons=[],
        failed_agent_ids=[],
        failed_folders=[],
        folders=[Folder.SHARE],
        homeassistant_included=True,
        homeassistant_version="2026.9.4",
        name=f"Backup {backup_id}",
        with_automatic_settings=automatic,
        agents=agents
        if agents is not None
        else {
            "local": Status(protected=False, size=100),
            "nas": Status(protected=False, size=120),
        },
    )


def test_classification() -> None:
    """Classify every source class without using backup names."""
    bma = inventory.classify_metadata(
        {
            inventory.METADATA_MANAGED: True,
            inventory.METADATA_JOB_ID: "full",
            inventory.METADATA_VERSION: "1",
        }
    )
    assert bma == {
        "source_type": "bma",
        "classification_reason": "bma_managed",
        "job_id": "full",
        "app_slug": None,
        "metadata_version": 1,
    }

    legacy = inventory.classify_metadata({inventory.METADATA_MANAGED: True})
    assert legacy["source_type"] == "bma"
    assert legacy["classification_reason"] == "bma_legacy_no_job"
    assert legacy["job_id"] is None
    assert legacy["metadata_version"] is None

    invalid_job = inventory.classify_metadata(
        {
            inventory.METADATA_MANAGED: True,
            inventory.METADATA_JOB_ID: "Full backup",
            inventory.METADATA_VERSION: "bogus",
        }
    )
    assert invalid_job["source_type"] == "bma"
    assert invalid_job["classification_reason"] == "bma_invalid_job_id"
    assert invalid_job["job_id"] is None
    assert invalid_job["metadata_version"] is None

    app = inventory.classify_metadata(
        {inventory.METADATA_APP_UPDATE: "core_mosquitto"}
    )
    assert app["source_type"] == "app_update"
    assert app["classification_reason"] == "app_update_metadata"
    assert app["app_slug"] == "core_mosquitto"

    invalid_app = inventory.classify_metadata({inventory.METADATA_APP_UPDATE: ""})
    assert invalid_app["source_type"] == "unknown"
    assert invalid_app["classification_reason"] == "invalid_app_update_metadata"

    conflict = inventory.classify_metadata(
        {
            inventory.METADATA_MANAGED: True,
            inventory.METADATA_APP_UPDATE: "core_mosquitto",
        }
    )
    assert conflict["source_type"] == "unknown"
    assert conflict["classification_reason"] == "conflicting_source_markers"

    native = inventory.classify_metadata({})
    assert native["source_type"] == "ha_native"
    assert native["classification_reason"] == "ha_native_default"


def test_backup_chronology_key_handles_timezone_offsets() -> None:
    """Order timestamps by real instant rather than their ISO text."""
    first = inventory.backup_chronology_key(
        "2026-10-25T02:30:00+02:00",
        "first",
    )
    second = inventory.backup_chronology_key(
        "2026-10-25T02:15:00+01:00",
        "second",
    )

    assert first < second
    assert inventory.backup_chronology_key(
        "not-a-date",
        "invalid",
    ) < first


def test_job_id_normalization() -> None:
    """Keep the public job-id grammar deterministic."""
    assert inventory.normalize_job_id("full") == "full"
    assert inventory.normalize_job_id("partial_daily") == "partial_daily"
    assert inventory.normalize_job_id("job-1") == "job-1"
    assert inventory.normalize_job_id(" full ") == "full"
    assert inventory.normalize_job_id("") is None
    assert inventory.normalize_job_id("Full") is None
    assert inventory.normalize_job_id("contains space") is None
    assert inventory.normalize_job_id("a" * 65) is None


def test_backup_normalization_and_sizes() -> None:
    """Normalize native fields, classification, and per-logical size semantics."""
    normalized = inventory.normalize_backup(
        make_backup(
            "bma-full",
            metadata={
                inventory.METADATA_MANAGED: True,
                inventory.METADATA_JOB_ID: "full",
                inventory.METADATA_VERSION: "1",
            },
            agents={
                "local": Status(protected=False, size=100),
                "nas": Status(protected=True, size=120),
            },
        )
    )

    assert normalized["backup_id"] == "bma-full"
    assert normalized["source_type"] == "bma"
    assert normalized["job_id"] == "full"
    assert normalized["agents"]["local"]["size"] == 100
    assert normalized["agents"]["nas"]["protected"] is True
    assert normalized["physical_size_bytes"] == 220
    assert normalized["physical_size_complete"] is True
    assert normalized["logical_size_bytes"] == 120
    assert normalized["logical_size_complete"] is True

    incomplete = inventory.normalize_backup(
        make_backup(
            "missing-size",
            agents={
                "local": Status(protected=False, size=100),
                "nas": Status(protected=False, size=None),
            },
        )
    )
    assert incomplete["physical_size_bytes"] == 100
    assert incomplete["physical_size_complete"] is False
    assert incomplete["logical_size_bytes"] == 100
    assert incomplete["logical_size_complete"] is True

    no_sizes = inventory.normalize_backup(
        make_backup(
            "no-sizes",
            agents={
                "local": Status(protected=False, size=None),
            },
        )
    )
    assert no_sizes["physical_size_bytes"] == 0
    assert no_sizes["physical_size_complete"] is False
    assert no_sizes["logical_size_bytes"] is None
    assert no_sizes["logical_size_complete"] is False


def test_inventory_aggregation() -> None:
    """Aggregate source counts, breakdowns, and archive sizes."""
    raw = [
        make_backup(
            "full",
            metadata={
                inventory.METADATA_MANAGED: True,
                inventory.METADATA_JOB_ID: "full",
                inventory.METADATA_VERSION: "1",
            },
            agents={
                "local": Status(False, 100),
                "nas": Status(False, 110),
            },
        ),
        make_backup(
            "legacy",
            metadata={inventory.METADATA_MANAGED: True},
            agents={"local": Status(False, 90)},
        ),
        make_backup(
            "native-auto",
            automatic=True,
            agents={"local": Status(False, 80)},
        ),
        make_backup(
            "native-manual",
            automatic=False,
            agents={"nas": Status(False, 70)},
        ),
        make_backup(
            "app-a",
            metadata={inventory.METADATA_APP_UPDATE: "addon_a"},
            agents={"local": Status(False, 60)},
        ),
        make_backup(
            "app-b",
            metadata={inventory.METADATA_APP_UPDATE: "addon_b"},
            agents={"nas": Status(False, 50)},
        ),
        make_backup(
            "unknown",
            metadata={inventory.METADATA_APP_UPDATE: ""},
            agents={"local": Status(False, 40)},
        ),
    ]
    normalized = [inventory.normalize_backup(item) for item in raw]

    summary = inventory.aggregate_inventory(
        normalized,
        {
            "local": {"name": "local", "domain": "hassio"},
            "nas": {"name": "Backup", "domain": "hassio"},
            "cloud": {"name": "Google Drive", "domain": "google_drive"},
        },
    )

    assert summary["inventory_complete"] is True
    assert summary["source_counts"] == {
        "bma": 2,
        "ha_native": 2,
        "app_update": 2,
        "unknown": 1,
    }
    assert summary["bma_by_job"] == {"full": 1, "unassigned": 1}
    assert summary["app_update_by_app"] == {"addon_a": 1, "addon_b": 1}
    assert summary["ha_native_breakdown"] == {
        "automatic": 1,
        "manual_or_other": 1,
    }

    archive = summary["archive_size"]
    assert archive["physical_total_bytes"] == 600
    assert archive["physical_size_complete"] is True
    assert archive["logical_size_bytes"] == 500
    assert archive["logical_size_complete"] is True

    assert archive["per_agent"]["local"] == {
        "name": "local",
        "domain": "hassio",
        "backup_count": 5,
        "size_bytes": 370,
        "size_complete": True,
    }
    assert archive["per_agent"]["nas"] == {
        "name": "Backup",
        "domain": "hassio",
        "backup_count": 3,
        "size_bytes": 230,
        "size_complete": True,
    }
    assert archive["per_agent"]["cloud"]["backup_count"] == 0
    assert archive["per_agent"]["cloud"]["size_bytes"] == 0

    assert archive["per_source_type"]["bma"]["backup_count"] == 2
    assert archive["per_source_type"]["bma"]["physical_size_bytes"] == 300
    assert archive["per_source_type"]["bma"]["logical_size_bytes"] == 200
    assert archive["per_source_type"]["app_update"]["physical_size_bytes"] == 110


def test_agent_errors_mark_inventory_incomplete() -> None:
    """Never claim complete sizes when a registered agent could not be read."""
    normalized = [
        inventory.normalize_backup(
            make_backup(
                "one",
                agents={"local": Status(False, 100)},
            )
        )
    ]
    summary = inventory.aggregate_inventory(
        normalized,
        {
            "local": {"name": "local", "domain": "hassio"},
            "cloud": {"name": "Google Drive", "domain": "google_drive"},
        },
        {"cloud": "provider unavailable"},
    )

    assert summary["inventory_complete"] is False
    assert summary["archive_size"]["physical_size_complete"] is False
    assert summary["archive_size"]["logical_size_complete"] is False
    assert summary["archive_size"]["per_agent"]["cloud"]["size_complete"] is False
    for source_summary in summary["archive_size"]["per_source_type"].values():
        assert source_summary["physical_size_complete"] is False
        assert source_summary["logical_size_complete"] is False


def main() -> None:
    test_classification()
    test_backup_chronology_key_handles_timezone_offsets()
    test_job_id_normalization()
    test_backup_normalization_and_sizes()
    test_inventory_aggregation()
    test_agent_errors_mark_inventory_incomplete()
    print("inventory simulation: OK")


if __name__ == "__main__":
    main()
