"""Lightweight behavioral tests for the adapter using local stubs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "adapter.py"


class Folder(StrEnum):
    SHARE = "share"
    ADDONS = "addons/local"
    SSL = "ssl"
    MEDIA = "media"


class HomeAssistantError(Exception):
    """Stub Home Assistant error."""


backup_module = types.ModuleType("homeassistant.components.backup")
backup_module.Folder = Folder
backup_module.BackupManager = object
backup_module.ManagerBackup = object
backup_module.async_get_manager = lambda hass: hass.manager
core_module = types.ModuleType("homeassistant.core")
core_module.HomeAssistant = object
exceptions_module = types.ModuleType("homeassistant.exceptions")
exceptions_module.HomeAssistantError = HomeAssistantError
components_module = types.ModuleType("homeassistant.components")
homeassistant_module = types.ModuleType("homeassistant")
custom_components_module = types.ModuleType("custom_components")
custom_components_module.__path__ = [str(ROOT / "custom_components")]
package_module = types.ModuleType("custom_components.backup_manager_actions")
package_module.__path__ = [
    str(ROOT / "custom_components" / "backup_manager_actions")
]

sys.modules.setdefault("homeassistant", homeassistant_module)
sys.modules.setdefault("homeassistant.components", components_module)
sys.modules["homeassistant.components.backup"] = backup_module
sys.modules["homeassistant.core"] = core_module
sys.modules["homeassistant.exceptions"] = exceptions_module
sys.modules.setdefault("custom_components", custom_components_module)
sys.modules.setdefault("custom_components.backup_manager_actions", package_module)

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.adapter", MODULE
)
adapter_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = adapter_module
spec.loader.exec_module(adapter_module)

BackupManagerActionsAdapter = adapter_module.BackupManagerActionsAdapter
BackupManagerActionsError = adapter_module.BackupManagerActionsError
adapter_module.CREATE_VERIFY_DELAY_SECONDS = 0


@dataclass
class Status:
    protected: bool = True
    size: int = 123


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
    homeassistant_version: str
    name: str
    with_automatic_settings: bool
    agents: dict


class Agent:
    def __init__(self, name: str, domain: str) -> None:
        self.name = name
        self.domain = domain


class NewBackup:
    def __init__(self, backup_job_id: str) -> None:
        self.backup_job_id = backup_job_id


class Manager:
    def __init__(self) -> None:
        self.state = "idle"
        self.backup_agents = {
            "local": Agent("Local", "hassio"),
            "cloud": Agent("Cloud", "s3_compatible"),
            "third": Agent("Third", "test"),
        }
        self.backups: dict[str, Backup] = {}
        self.create_agents = ["local", "cloud"]
        self.create_failed_agent_ids: list[str] = []
        self.lookup_errors: dict[str, Exception] = {}
        self.delete_errors: dict[str, Exception] = {}
        self.sticky_delete_agents: set[str] = set()
        self.sticky_delete_backup_ids: set[str] = set()
        self.protect_on_lookup_backup_ids: set[str] = set()
        self.late_copy_on_lookup: dict[str, str] = {}
        self.remove_on_lookup_backup_ids: set[str] = set()
        self.remove_agent_on_lookup: dict[str, str] = {}
        self.remove_agent_on_lookup_countdown: dict[str, tuple[str, int]] = {}
        self.metadata_on_lookup: dict[str, dict] = {}
        self.lookup_errors_on_get_backup: dict[str, dict[str, Exception]] = {}
        self.delete_delay_seconds = 0.0
        self.delete_active = 0
        self.max_delete_active = 0
        self.remove_backup_after_delete: dict[str, str] = {}
        self.omit_metadata_keys: set[str] = set()
        self.override_metadata: dict[str, object] = {}

    async def async_create_backup(self, **kwargs):
        backup_id = "abc12345"
        extra_metadata = dict(kwargs["extra_metadata"])
        for key in self.omit_metadata_keys:
            extra_metadata.pop(key, None)
        extra_metadata.update(self.override_metadata)
        self.backups[backup_id] = Backup(
            addons=[Addon("core_mosquitto", "Mosquitto", "1.0")],
            backup_id=backup_id,
            date="2026-09-27T20:00:00+02:00",
            database_included=kwargs["include_database"],
            extra_metadata=extra_metadata,
            failed_addons=[],
            failed_agent_ids=list(self.create_failed_agent_ids),
            failed_folders=[],
            folders=kwargs["include_folders"] or [],
            homeassistant_included=kwargs["include_homeassistant"],
            homeassistant_version="2026.9.3",
            name=kwargs["name"] or "Custom backup",
            with_automatic_settings=False,
            agents={agent_id: Status() for agent_id in self.create_agents},
        )
        return NewBackup("f6815a2f443f442bb89193410e2bb41f")

    async def async_get_backup(self, backup_id):
        if backup_id in self.remove_on_lookup_backup_ids:
            self.remove_on_lookup_backup_ids.discard(backup_id)
            self.backups.pop(backup_id, None)
            return None, dict(
                self.lookup_errors_on_get_backup.get(
                    backup_id,
                    self.lookup_errors,
                )
            )

        backup = self.backups.get(backup_id)
        if backup is not None and backup_id in self.remove_agent_on_lookup:
            agent_id = self.remove_agent_on_lookup.pop(backup_id)
            backup.agents.pop(agent_id, None)
            if not backup.agents:
                self.backups.pop(backup_id, None)
                backup = None
        if (
            backup is not None
            and backup_id in self.remove_agent_on_lookup_countdown
        ):
            agent_id, remaining = self.remove_agent_on_lookup_countdown[backup_id]
            remaining -= 1
            if remaining <= 0:
                self.remove_agent_on_lookup_countdown.pop(backup_id, None)
                backup.agents.pop(agent_id, None)
                if not backup.agents:
                    self.backups.pop(backup_id, None)
                    backup = None
            else:
                self.remove_agent_on_lookup_countdown[backup_id] = (
                    agent_id,
                    remaining,
                )
        if backup is not None and backup_id in self.protect_on_lookup_backup_ids:
            if "local" in backup.agents:
                backup.agents["local"].protected = True
        if backup is not None and backup_id in self.late_copy_on_lookup:
            agent_id = self.late_copy_on_lookup[backup_id]
            backup.agents.setdefault(
                agent_id,
                Status(protected=False, size=150),
            )
        if backup is not None and backup_id in self.metadata_on_lookup:
            backup.extra_metadata.update(self.metadata_on_lookup[backup_id])

        return backup, dict(
            self.lookup_errors_on_get_backup.get(
                backup_id,
                self.lookup_errors,
            )
        )

    async def async_get_backups(self):
        return self.backups, dict(self.lookup_errors)

    async def async_delete_backup(self, backup_id, *, agent_ids=None):
        backup = self.backups.get(backup_id)
        if backup is None:
            return {}

        self.delete_active += 1
        self.max_delete_active = max(
            self.max_delete_active,
            self.delete_active,
        )
        try:
            if self.delete_delay_seconds:
                await asyncio.sleep(self.delete_delay_seconds)

            targets = set(backup.agents) if agent_ids is None else set(agent_ids)
            sticky_agents = set(self.sticky_delete_agents)
            if backup_id in self.sticky_delete_backup_ids:
                sticky_agents.update(targets)
            for agent_id in targets - sticky_agents:
                backup.agents.pop(agent_id, None)

            if not backup.agents:
                self.backups.pop(backup_id, None)

            if backup_id in self.remove_backup_after_delete:
                other_backup_id = self.remove_backup_after_delete.pop(backup_id)
                self.backups.pop(other_backup_id, None)

            return dict(self.delete_errors)
        finally:
            self.delete_active -= 1


class Hass:
    def __init__(self, manager):
        self.manager = manager
        self.config = types.SimpleNamespace(time_zone="Europe/Rome")


async def create_default_backup(adapter) -> None:
    await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=False,
        include_addons=None,
        include_folders=None,
        name=None,
        password=None,
    )


def add_bma_backup(
    manager,
    backup_id,
    date,
    *,
    job_id="full",
    agents=None,
):
    """Insert one normalized BMA-style backup into the manager stub."""
    metadata = {
        "backup_manager_actions.managed": True,
        "backup_manager_actions.metadata_version": "1",
    }
    if job_id is not None:
        metadata["backup_manager_actions.job_id"] = job_id

    manager.backups[backup_id] = Backup(
        addons=[],
        backup_id=backup_id,
        date=date,
        database_included=True,
        extra_metadata=metadata,
        failed_addons=[],
        failed_agent_ids=[],
        failed_folders=[],
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2026.9.4",
        name=backup_id,
        with_automatic_settings=False,
        agents=agents
        if agents is not None
        else {"local": Status(protected=False, size=100)},
    )


def add_raw_backup(
    manager,
    backup_id,
    date,
    *,
    metadata=None,
    automatic=False,
    agents=None,
):
    """Insert one raw Backup Manager-style backup into the manager stub."""
    manager.backups[backup_id] = Backup(
        addons=[],
        backup_id=backup_id,
        date=date,
        database_included=True,
        extra_metadata=dict(metadata or {}),
        failed_addons=[],
        failed_agent_ids=[],
        failed_folders=[],
        folders=[],
        homeassistant_included=True,
        homeassistant_version="2026.9.4",
        name=backup_id,
        with_automatic_settings=automatic,
        agents=agents
        if agents is not None
        else {"local": Status(protected=False, size=100)},
    )


async def test_create_success() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    result = await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=True,
        include_addons=None,
        include_folders=["share", "ssl"],
        name="Test",
        password="secret",
    )
    assert result["backup_id"] == "abc12345"
    assert result["backup_job_id"] == "f6815a2f443f442bb89193410e2bb41f"
    assert result["stored_agent_ids"] == ["cloud", "local"]
    metadata = manager.backups["abc12345"].extra_metadata
    assert metadata["backup_manager_actions.managed"] is True
    assert "backup_manager_actions.correlation_id" in metadata
    assert metadata["backup_manager_actions.metadata_version"] == "1"
    assert "backup_manager_actions.job_id" not in metadata
    assert result["source_type"] == "bma"
    assert result["job_id"] is None
    assert result["metadata_version"] == 1
    assert result["failed_agent_ids"] == []
    assert result["with_automatic_settings"] is False
    assert result["size_by_agent"] == {"local": 123, "cloud": 123}


async def test_create_with_full_job_id() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    result = await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=False,
        include_addons=None,
        include_folders=None,
        name="Full backup",
        password=None,
        job_id="full",
    )

    metadata = manager.backups["abc12345"].extra_metadata
    assert metadata["backup_manager_actions.job_id"] == "full"
    assert metadata["backup_manager_actions.metadata_version"] == "1"
    assert result["source_type"] == "bma"
    assert result["job_id"] == "full"
    assert result["metadata_version"] == 1

    listing = await adapter.async_list_backups()
    assert listing["backups"][0]["job_id"] == "full"
    assert listing["backups"][0]["classification_reason"] == "bma_managed"

    snapshot = await adapter.async_snapshot()
    assert snapshot["bma_by_job"] == {"full": 1}


async def test_create_with_partial_job_id() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    result = await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=False,
        include_addons=["core_mosquitto"],
        include_folders=["share"],
        name="Partial backup",
        password=None,
        job_id="partial",
    )

    assert manager.backups["abc12345"].extra_metadata[
        "backup_manager_actions.job_id"
    ] == "partial"
    assert result["job_id"] == "partial"


async def test_create_normalizes_job_id() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    result = await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=False,
        include_addons=None,
        include_folders=None,
        name=None,
        password=None,
        job_id=" full ",
    )

    assert result["job_id"] == "full"
    assert manager.backups["abc12345"].extra_metadata[
        "backup_manager_actions.job_id"
    ] == "full"


async def test_create_rejects_invalid_job_id_before_creation() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_create(
            agent_ids=["local", "cloud"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
            job_id="Full backup",
        )
    except BackupManagerActionsError as err:
        assert "Invalid job_id" in str(err)
    else:
        raise AssertionError("Invalid job_id should fail")

    assert manager.backups == {}


async def test_create_verifies_metadata_version_persistence() -> None:
    manager = Manager()
    manager.omit_metadata_keys = {"backup_manager_actions.metadata_version"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_create(
            agent_ids=["local", "cloud"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
            job_id="full",
        )
    except BackupManagerActionsError as err:
        assert "metadata verification failed" in str(err)
        assert "metadata_version is None, expected 1" in str(err)
    else:
        raise AssertionError("Missing metadata_version should fail verification")


async def test_create_rejects_noncanonical_metadata_version() -> None:
    manager = Manager()
    manager.override_metadata = {
        "backup_manager_actions.metadata_version": "01"
    }
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_create(
            agent_ids=["local", "cloud"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
            job_id="full",
        )
    except BackupManagerActionsError as err:
        assert "stored metadata_version is '01', expected '1'" in str(err)
    else:
        raise AssertionError("Noncanonical persisted metadata_version must fail")


async def test_legacy_create_rejects_unexpected_invalid_stored_job_id() -> None:
    manager = Manager()
    manager.override_metadata = {
        "backup_manager_actions.job_id": "INVALID"
    }
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await create_default_backup(adapter)
    except BackupManagerActionsError as err:
        assert "unexpected stored job_id 'INVALID'" in str(err)
    else:
        raise AssertionError(
            "A legacy-compatible create must not accept injected job metadata"
        )


async def test_create_verifies_job_id_persistence() -> None:
    manager = Manager()
    manager.omit_metadata_keys = {"backup_manager_actions.job_id"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_create(
            agent_ids=["local", "cloud"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
            job_id="full",
        )
    except BackupManagerActionsError as err:
        assert "metadata verification failed" in str(err)
        assert "job_id is None, expected full" in str(err)
    else:
        raise AssertionError("Missing job_id should fail verification")


async def test_create_detects_missing_copy() -> None:
    manager = Manager()
    manager.create_agents = ["local"]
    adapter = BackupManagerActionsAdapter(Hass(manager))
    try:
        await adapter.async_create(
            agent_ids=["local", "cloud"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
        )
    except BackupManagerActionsError as err:
        assert "missing agent copies: cloud" in str(err)
    else:
        raise AssertionError("Missing cloud copy should fail")


async def test_create_ignores_unrelated_agent_lookup_error() -> None:
    manager = Manager()
    manager.lookup_errors = {"third": RuntimeError("offline")}
    adapter = BackupManagerActionsAdapter(Hass(manager))
    result = await adapter.async_create(
        agent_ids=["local", "cloud"],
        include_homeassistant=True,
        include_database=True,
        include_all_addons=False,
        include_addons=None,
        include_folders=None,
        name=None,
        password=None,
    )
    assert result["stored_agent_ids"] == ["cloud", "local"]


async def test_create_rejects_reported_requested_agent_failure() -> None:
    manager = Manager()
    manager.create_failed_agent_ids = ["cloud"]
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await create_default_backup(adapter)
    except BackupManagerActionsError as err:
        message = str(err)
        assert "reported failed agent copies" in message
        assert "cloud" in message
    else:
        raise AssertionError(
            "A requested agent reported as failed must block create verification"
        )


async def test_create_rejects_requested_agent_lookup_error() -> None:
    manager = Manager()
    manager.lookup_errors = {"cloud": RuntimeError("cloud unreadable")}
    adapter = BackupManagerActionsAdapter(Hass(manager))
    try:
        await create_default_backup(adapter)
    except BackupManagerActionsError as err:
        assert "agent errors" in str(err)
        assert "cloud unreadable" in str(err)
    else:
        raise AssertionError("Requested agent lookup error should fail")


async def test_create_rejects_unavailable_requested_agent() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    try:
        await adapter.async_create(
            agent_ids=["local", "missing"],
            include_homeassistant=True,
            include_database=True,
            include_all_addons=False,
            include_addons=None,
            include_folders=None,
            name=None,
            password=None,
        )
    except BackupManagerActionsError as err:
        assert "Backup agent(s) not available: missing" in str(err)
    else:
        raise AssertionError("Unavailable requested agent should fail")



async def test_delete_missing_backup_is_idempotent() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_delete(
        backup_id="already-gone",
        agent_ids=["local", "cloud"],
    )
    assert result["found_before_delete"] is False
    assert result["remaining_agent_ids"] == []


async def test_delete_global() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    result = await adapter.async_delete(backup_id="abc12345")
    assert result["remaining_agent_ids"] == []
    assert "abc12345" not in manager.backups


async def test_delete_selected_copy() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    result = await adapter.async_delete(
        backup_id="abc12345",
        agent_ids=["cloud"],
    )
    assert result["remaining_agent_ids"] == ["local"]


async def test_delete_selected_ignores_unrelated_lookup_error() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    manager.lookup_errors = {"third": RuntimeError("offline")}
    result = await adapter.async_delete(
        backup_id="abc12345",
        agent_ids=["cloud"],
    )
    assert result["remaining_agent_ids"] == ["local"]


async def test_delete_explicit_rejects_missing_agent_before_delete() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    manager.backup_agents.pop("cloud")

    try:
        await adapter.async_delete(
            backup_id="abc12345",
            agent_ids=["local", "cloud"],
        )
    except BackupManagerActionsError as err:
        assert "Backup agent(s) not available: cloud" in str(err)
    else:
        raise AssertionError("Missing expected agent must block retention deletion")

    assert set(manager.backups["abc12345"].agents) == {"local", "cloud"}


async def test_delete_global_rejects_unverifiable_agent() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    manager.lookup_errors = {"third": RuntimeError("offline")}

    try:
        await adapter.async_delete(backup_id="abc12345")
    except BackupManagerActionsError as err:
        assert "Could not safely inspect backup" in str(err)
    else:
        raise AssertionError("Global deletion must fail when an agent is unverifiable")


async def test_delete_reports_agent_error() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    manager.delete_errors = {"cloud": RuntimeError("delete failed")}

    try:
        await adapter.async_delete(backup_id="abc12345")
    except BackupManagerActionsError as err:
        assert "was not deleted cleanly" in str(err)
    else:
        raise AssertionError("Agent deletion error should fail")


async def test_delete_post_verification_detects_remaining_copy() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)
    manager.sticky_delete_agents = {"cloud"}

    try:
        await adapter.async_delete(
            backup_id="abc12345",
            agent_ids=["cloud"],
        )
    except BackupManagerActionsError as err:
        assert "still exists on: cloud" in str(err)
    else:
        raise AssertionError("A copy that remains after delete must fail verification")


async def test_snapshot_and_serialization() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)

    snapshot = await adapter.async_snapshot()
    assert snapshot["state"] == "idle"
    assert snapshot["agent_count"] == 3
    assert snapshot["backup_count"] == 1
    assert snapshot["agents"]["cloud"]["domain"] == "s3_compatible"
    assert snapshot["latest_backup"]["backup_id"] == "abc12345"
    assert snapshot["latest_backup"]["addons"][0]["slug"] == "core_mosquitto"
    assert snapshot["latest_backup"]["source_type"] == "bma"
    assert snapshot["latest_backup"]["classification_reason"] == "bma_legacy_no_job"
    assert snapshot["inventory_complete"] is True
    assert snapshot["source_counts"] == {
        "bma": 1,
        "ha_native": 0,
        "app_update": 0,
        "unknown": 0,
    }
    assert snapshot["bma_by_job"] == {"unassigned": 1}
    assert snapshot["archive_size"]["physical_total_bytes"] == 246
    assert snapshot["archive_size"]["logical_size_bytes"] == 123


async def test_snapshot_latest_uses_real_timestamp_across_offsets() -> None:
    manager = Manager()
    add_raw_backup(
        manager,
        "earlier-real-time",
        "2026-10-25T02:30:00+02:00",
    )
    add_raw_backup(
        manager,
        "later-real-time",
        "2026-10-25T02:15:00+01:00",
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    snapshot = await adapter.async_snapshot()
    listing = await adapter.async_list_backups()

    assert snapshot["latest_backup"]["backup_id"] == "later-real-time"
    assert [item["backup_id"] for item in listing["backups"]] == [
        "later-real-time",
        "earlier-real-time",
    ]


async def test_list_and_get_backup() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
    await create_default_backup(adapter)

    listing = await adapter.async_list_backups()
    details = await adapter.async_get_backup("abc12345")
    assert listing["backups"][0]["backup_id"] == "abc12345"
    assert listing["backups"][0]["source_type"] == "bma"
    assert listing["backups"][0]["physical_size_bytes"] == 246
    assert listing["backups"][0]["logical_size_bytes"] == 123
    assert details["backup"]["agents"]["cloud"]["size"] == 123
    assert details["backup"]["classification_reason"] == "bma_legacy_no_job"


async def test_plan_retention_is_read_only() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "new",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "old",
        "2026-09-28T10:00:00+02:00",
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_plan_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert [item["backup_id"] for item in result["keep"]] == ["new"]
    assert [item["backup_id"] for item in result["delete"]] == ["old"]
    assert result["scope"]["agent_ids"] == ["local"]
    assert set(manager.backups) == {"new", "old"}
    assert set(manager.backups["old"].agents) == {"local"}


async def test_plan_retention_explicit_scope_ignores_unrelated_agent_error() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "new",
        "2026-09-29T10:00:00+02:00",
    )
    manager.lookup_errors = {"cloud": RuntimeError("cloud unavailable")}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_plan_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["summary"]["considered"] == 1


async def test_plan_retention_omitted_scope_fails_on_any_agent_error() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "new",
        "2026-09-29T10:00:00+02:00",
    )
    manager.lookup_errors = {"cloud": RuntimeError("cloud unavailable")}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_plan_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=None,
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
        )
    except BackupManagerActionsError as err:
        assert "Retention inventory is incomplete" in str(err)
        assert "cloud" in str(err)
    else:
        raise AssertionError("All-agent retention should fail closed")


async def test_plan_retention_omitted_scope_uses_all_registered_agents() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "new",
        "2026-09-29T10:00:00+02:00",
        agents={"local": Status(protected=False, size=100)},
    )
    add_bma_backup(
        manager,
        "old",
        "2026-09-28T10:00:00+02:00",
        agents={"local": Status(protected=False, size=90)},
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_plan_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=None,
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["scope"]["agent_ids"] == ["cloud", "local", "third"]
    assert result["delete"][0]["target_agent_ids"] == ["local"]


async def test_plan_retention_rejects_missing_agent() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_plan_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["missing"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
        )
    except BackupManagerActionsError as err:
        assert "Backup agent(s) not available: missing" in str(err)
    else:
        raise AssertionError("Unknown retention agent should fail")


async def test_plan_and_apply_agree_when_inventory_is_unchanged() -> None:
    """The dry plan and apply plan must be identical when state is unchanged."""
    manager = Manager()
    for backup_id, date in (
        ("today-new", "2026-09-29T11:00:00+02:00"),
        ("today-old", "2026-09-29T08:00:00+02:00"),
        ("yesterday", "2026-09-28T10:00:00+02:00"),
        ("last-week", "2026-09-20T10:00:00+02:00"),
        ("last-month", "2026-08-20T10:00:00+02:00"),
        ("last-year", "2025-12-20T10:00:00+01:00"),
        ("ancient", "2024-06-20T10:00:00+02:00"),
    ):
        add_bma_backup(manager, backup_id, date, job_id="full")

    adapter = BackupManagerActionsAdapter(Hass(manager))
    now = adapter_module.datetime(
        2026,
        9,
        29,
        12,
        0,
        tzinfo=adapter_module.timezone.utc,
    )
    policy = {
        "source_type": "bma",
        "job_id": "full",
        "group_by": None,
        "agent_ids": ["local"],
        "keep_last": 1,
        "daily": 2,
        "weekly": 2,
        "monthly": 2,
        "yearly": 2,
        "now": now,
    }

    dry_plan = await adapter.async_plan_retention(**policy)
    applied = await adapter.async_apply_retention(**policy)

    assert applied["plan"] == dry_plan
    assert [
        item["backup_id"]
        for item in applied["execution"]["deleted"]
    ] == [
        item["backup_id"]
        for item in dry_plan["delete"]
    ]
    assert applied["execution"]["deleted_count"] == len(dry_plan["delete"])
    assert applied["execution"]["already_absent_count"] == 0


async def test_apply_retention_recalculates_current_state() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "new-before-dry-run",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "old",
        "2026-09-27T10:00:00+02:00",
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))
    now = adapter_module.datetime(
        2026,
        9,
        29,
        12,
        0,
        tzinfo=adapter_module.timezone.utc,
    )

    dry_run = await adapter.async_plan_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=now,
    )
    assert [item["backup_id"] for item in dry_run["delete"]] == ["old"]

    # State changes after the dry-run. Apply must not execute that stale plan.
    add_bma_backup(
        manager,
        "new-after-dry-run",
        "2026-09-29T11:00:00+02:00",
    )

    applied = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=now,
    )

    assert [item["backup_id"] for item in applied["plan"]["keep"]] == [
        "new-after-dry-run"
    ]
    assert [item["backup_id"] for item in applied["plan"]["delete"]] == [
        "old",
        "new-before-dry-run",
    ]
    assert applied["execution"]["deleted_count"] == 2
    assert set(manager.backups) == {"new-after-dry-run"}


async def test_apply_retention_preserves_out_of_scope_copies() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
        agents={"local": Status(protected=False, size=100)},
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
        agents={
            "local": Status(protected=False, size=100),
            "cloud": Status(protected=False, size=120),
        },
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["execution"]["deleted_count"] == 1
    assert set(manager.backups["expire"].agents) == {"cloud"}
    deleted = result["execution"]["deleted"][0]
    assert deleted["target_agent_ids"] == ["local"]
    assert deleted["remaining_agent_ids"] == ["cloud"]


async def test_apply_retention_allows_late_encryption_flag() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
    )
    manager.protect_on_lookup_backup_ids = {"expire"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(**review_policy(["local"]))
    assert result["execution"]["deleted_count"] == 1
    assert "expire" not in manager.backups


async def test_apply_retention_deletes_late_in_scope_copy() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
        agents={
            "local": Status(protected=False, size=100),
            "cloud": Status(protected=False, size=120),
        },
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
        agents={"local": Status(protected=False, size=100)},
    )
    manager.late_copy_on_lookup = {"expire": "cloud"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local", "cloud"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert "expire" not in manager.backups
    assert result["execution"]["deleted"][0]["target_agent_ids"] == [
        "cloud",
        "local",
    ]


async def test_apply_retention_handles_candidate_removed_by_other_actor() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
    )
    manager.remove_on_lookup_backup_ids = {"expire"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["execution"]["deleted_count"] == 0
    assert result["execution"]["already_absent_count"] == 1
    assert result["execution"]["deleted"][0]["found_before_delete"] is False
    assert set(manager.backups) == {"keep"}


async def test_apply_retention_aborts_on_late_classification_change() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
    )
    manager.metadata_on_lookup = {
        "expire": {"backup_manager_actions.job_id": "partial"}
    }
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=adapter_module.datetime(
                2026,
                9,
                29,
                12,
                0,
                tzinfo=adapter_module.timezone.utc,
            ),
        )
    except BackupManagerActionsError as err:
        assert "changed classification before deletion" in str(err)
    else:
        raise AssertionError("Late classification changes must block deletion")

    assert "expire" in manager.backups


async def test_apply_retention_aborts_on_late_scoped_agent_error() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
    )
    manager.lookup_errors_on_get_backup = {
        "expire": {"local": RuntimeError("local became unreadable")}
    }
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=adapter_module.datetime(
                2026,
                9,
                29,
                12,
                0,
                tzinfo=adapter_module.timezone.utc,
            ),
        )
    except BackupManagerActionsError as err:
        message = str(err)
        assert "could not be revalidated" in message
        assert "local became unreadable" in message
    else:
        raise AssertionError("Late scoped agent errors must block deletion")

    assert "expire" in manager.backups


async def test_apply_retention_counts_disappeared_scoped_copy_as_already_absent() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
        agents={"local": Status(protected=False, size=100)},
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
        agents={
            "local": Status(protected=False, size=100),
            "cloud": Status(protected=False, size=120),
        },
    )
    manager.remove_agent_on_lookup = {"expire": "local"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["execution"]["deleted_count"] == 0
    assert result["execution"]["already_absent_count"] == 1
    item = result["execution"]["deleted"][0]
    assert item["found_before_delete"] is True
    assert item["target_copies_found_before_delete"] is False
    assert item["previous_agent_ids"] == ["cloud"]
    assert item["remaining_agent_ids"] == ["cloud"]
    assert set(manager.backups["expire"].agents) == {"cloud"}


async def test_apply_retention_reports_copy_removed_after_revalidation() -> None:
    """A target copy vanishing just before delete is already absent, not deleted."""
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
        agents={"local": Status(protected=False, size=100)},
    )
    add_bma_backup(
        manager,
        "expire",
        "2026-09-28T10:00:00+02:00",
        agents={
            "local": Status(protected=False, size=100),
            "cloud": Status(protected=False, size=120),
        },
    )

    # First get happens during retention revalidation; second get happens
    # inside async_delete immediately before deletion.
    manager.remove_agent_on_lookup_countdown = {
        "expire": ("local", 2)
    }
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert result["execution"]["deleted_count"] == 0
    assert result["execution"]["already_absent_count"] == 1
    item = result["execution"]["deleted"][0]
    assert item["found_before_delete"] is True
    assert item["target_copies_found_before_delete"] is False
    assert item["previous_agent_ids"] == ["cloud"]
    assert item["remaining_agent_ids"] == ["cloud"]
    assert set(manager.backups["expire"].agents) == {"cloud"}


async def test_apply_retention_revalidates_policy_between_candidates() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "middle",
        "2026-09-28T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "oldest",
        "2026-09-27T10:00:00+02:00",
    )

    # Simulate another actor removing the retained backup after the first
    # deletion. The remaining middle backup must be promoted to keep_last.
    manager.remove_backup_after_delete = {"oldest": "keep"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=adapter_module.datetime(
                2026,
                9,
                29,
                12,
                0,
                tzinfo=adapter_module.timezone.utc,
            ),
        )
    except BackupManagerActionsError as err:
        message = str(err)
        assert "middle" in message
        assert "no longer eligible for deletion" in message
        assert "deleted before failure: oldest" in message
    else:
        raise AssertionError(
            "Policy drift between destructive candidates must abort apply"
        )

    assert "oldest" not in manager.backups
    assert "keep" not in manager.backups
    assert "middle" in manager.backups


async def test_apply_retention_failure_reports_prior_deletions() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "oldest",
        "2026-09-26T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "fails-second",
        "2026-09-27T10:00:00+02:00",
    )
    manager.sticky_delete_backup_ids = {"fails-second"}
    adapter = BackupManagerActionsAdapter(Hass(manager))

    try:
        await adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=adapter_module.datetime(
                2026,
                9,
                29,
                12,
                0,
                tzinfo=adapter_module.timezone.utc,
            ),
        )
    except BackupManagerActionsError as err:
        message = str(err)
        assert "Retention apply failed at backup fails-second" in message
        assert "deleted before failure: oldest" in message
    else:
        raise AssertionError("Verification failure should abort apply")

    assert "oldest" not in manager.backups
    assert "fails-second" in manager.backups
    assert "keep" in manager.backups


async def test_scenario_full_job_retention_isolated_from_other_sources() -> None:
    """Exercise classification -> plan -> apply for one Full job policy."""
    manager = Manager()
    add_bma_backup(
        manager,
        "full-new",
        "2026-09-29T10:00:00+02:00",
        job_id="full",
    )
    add_bma_backup(
        manager,
        "full-old",
        "2026-09-28T10:00:00+02:00",
        job_id="full",
    )
    add_bma_backup(
        manager,
        "partial-old",
        "2026-09-20T10:00:00+02:00",
        job_id="partial",
    )
    add_raw_backup(
        manager,
        "native-old",
        "2026-09-19T10:00:00+02:00",
    )
    add_raw_backup(
        manager,
        "app-old",
        "2026-09-18T10:00:00+02:00",
        metadata={"supervisor.addon_update": "core_mosquitto"},
    )
    add_raw_backup(
        manager,
        "unknown-conflict",
        "2026-09-17T10:00:00+02:00",
        metadata={
            "backup_manager_actions.managed": True,
            "supervisor.addon_update": "core_mosquitto",
        },
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="bma",
        job_id="full",
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert [item["backup_id"] for item in result["plan"]["keep"]] == [
        "full-new"
    ]
    assert [item["backup_id"] for item in result["plan"]["delete"]] == [
        "full-old"
    ]
    assert result["execution"]["deleted_count"] == 1
    assert set(manager.backups) == {
        "full-new",
        "partial-old",
        "native-old",
        "app-old",
        "unknown-conflict",
    }


async def test_scenario_ha_native_manual_and_automatic_share_one_policy() -> None:
    """Exercise HA Native retention without touching BMA or App Update."""
    manager = Manager()
    add_raw_backup(
        manager,
        "native-auto-new",
        "2026-09-29T10:00:00+02:00",
        automatic=True,
    )
    add_raw_backup(
        manager,
        "native-manual-old",
        "2026-09-28T10:00:00+02:00",
        automatic=False,
    )
    add_bma_backup(
        manager,
        "bma-old",
        "2026-09-20T10:00:00+02:00",
        job_id="full",
    )
    add_raw_backup(
        manager,
        "app-old",
        "2026-09-19T10:00:00+02:00",
        metadata={"supervisor.addon_update": "addon_a"},
    )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="ha_native",
        job_id=None,
        group_by=None,
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert [item["backup_id"] for item in result["plan"]["keep"]] == [
        "native-auto-new"
    ]
    assert [item["backup_id"] for item in result["plan"]["delete"]] == [
        "native-manual-old"
    ]
    assert set(manager.backups) == {
        "native-auto-new",
        "bma-old",
        "app-old",
    }


async def test_scenario_app_update_per_app_is_independent_end_to_end() -> None:
    """Exercise independent per-App retention through the adapter executor."""
    manager = Manager()
    for backup_id, date, slug in (
        ("a-new", "2026-09-29T10:00:00+02:00", "addon_a"),
        ("a-old", "2026-09-27T10:00:00+02:00", "addon_a"),
        ("b-new", "2026-09-29T09:00:00+02:00", "addon_b"),
        ("b-old", "2026-09-26T10:00:00+02:00", "addon_b"),
    ):
        add_raw_backup(
            manager,
            backup_id,
            date,
            metadata={"supervisor.addon_update": slug},
        )
    adapter = BackupManagerActionsAdapter(Hass(manager))

    result = await adapter.async_apply_retention(
        source_type="app_update",
        job_id=None,
        group_by="app",
        agent_ids=["local"],
        keep_last=1,
        daily=0,
        weekly=0,
        monthly=0,
        yearly=0,
        now=adapter_module.datetime(
            2026,
            9,
            29,
            12,
            0,
            tzinfo=adapter_module.timezone.utc,
        ),
    )

    assert {item["backup_id"] for item in result["plan"]["keep"]} == {
        "a-new",
        "b-new",
    }
    assert [item["backup_id"] for item in result["plan"]["delete"]] == [
        "b-old",
        "a-old",
    ]
    assert result["execution"]["deleted_count"] == 2
    assert set(manager.backups) == {"a-new", "b-new"}


async def test_apply_retention_is_serialized() -> None:
    manager = Manager()
    add_bma_backup(
        manager,
        "keep",
        "2026-09-29T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "old-1",
        "2026-09-27T10:00:00+02:00",
    )
    add_bma_backup(
        manager,
        "old-2",
        "2026-09-28T10:00:00+02:00",
    )
    manager.delete_delay_seconds = 0.01
    adapter = BackupManagerActionsAdapter(Hass(manager))
    now = adapter_module.datetime(
        2026,
        9,
        29,
        12,
        0,
        tzinfo=adapter_module.timezone.utc,
    )

    first, second = await asyncio.gather(
        adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=now,
        ),
        adapter.async_apply_retention(
            source_type="bma",
            job_id="full",
            group_by=None,
            agent_ids=["local"],
            keep_last=1,
            daily=0,
            weekly=0,
            monthly=0,
            yearly=0,
            now=now,
        ),
    )

    assert manager.max_delete_active == 1
    assert sorted(
        [
            first["execution"]["deleted_count"],
            second["execution"]["deleted_count"],
        ]
    ) == [0, 2]
    assert set(manager.backups) == {"keep"}


def review_policy(agent_ids=None):
    """Return a small deterministic retention policy for review regressions."""
    return dict(source_type="bma", job_id="full", group_by=None,
                agent_ids=agent_ids, keep_last=1, daily=0, weekly=0,
                monthly=0, yearly=0)


def review_inventory():
    """Create a retained backup and an older candidate."""
    manager = Manager()
    add_bma_backup(manager, "keep", "2026-09-29T10:00:00+02:00")
    add_bma_backup(manager, "expire", "2026-09-28T10:00:00+02:00")
    return manager, BackupManagerActionsAdapter(Hass(manager))


async def test_retention_final_read_rechecks_metadata() -> None:
    """The delete pre-read must enforce retention guards as well."""
    for change in ("job", "date"):
        manager, adapter = review_inventory()
        original = manager.async_get_backup
        reads = 0

        async def changing_lookup(backup_id):
            nonlocal reads
            reads += 1
            if reads == 2:
                item = manager.backups[backup_id]
                if change == "job":
                    item.extra_metadata["backup_manager_actions.job_id"] = "partial"
                else:
                    item.date = "2026-09-30T10:00:00+02:00"
            return await original(backup_id)

        manager.async_get_backup = changing_lookup
        try:
            await adapter.async_apply_retention(**review_policy(["local"]))
        except BackupManagerActionsError:
            pass
        else:
            raise AssertionError(f"Final-read {change} change was ignored")
        assert "expire" in manager.backups


async def test_retention_agent_removed_during_listing_fails_closed() -> None:
    """An agent disappearing during an awaited listing cannot yield a safe plan."""
    manager, adapter = review_inventory()
    original = manager.async_get_backups

    async def changing_inventory():
        result = await original()
        manager.backup_agents.pop("cloud", None)
        return result

    manager.async_get_backups = changing_inventory
    try:
        await adapter.async_plan_retention(**review_policy(["local", "cloud"]))
    except BackupManagerActionsError as err:
        assert "cloud" in str(err)
    else:
        raise AssertionError("A vanished scoped agent was treated as readable")


async def test_retention_omitted_scope_is_frozen_during_apply() -> None:
    """A newly registered provider must not become a destructive target mid-apply."""
    manager, adapter = review_inventory()
    original = manager.async_get_backups
    reads = 0

    async def changing_inventory():
        nonlocal reads
        reads += 1
        if reads == 1:
            manager.backup_agents["new_provider"] = Agent("New", "test")
            manager.backups["expire"].agents["new_provider"] = Status(False, 150)
        return await original()

    manager.async_get_backups = changing_inventory
    result = await adapter.async_apply_retention(**review_policy())
    assert result["plan"]["scope"]["agent_ids"] == ["cloud", "local", "third"]
    assert set(manager.backups["expire"].agents) == {"new_provider"}


async def test_delete_cannot_verify_an_unregistered_target() -> None:
    """A provider disappearing after delete must not be reported as absent."""
    manager, adapter = review_inventory()
    original = manager.async_delete_backup

    async def disappearing_delete(backup_id, *, agent_ids=None):
        result = await original(backup_id, agent_ids=agent_ids)
        manager.backup_agents.pop("local")
        return result

    manager.async_delete_backup = disappearing_delete
    try:
        await adapter.async_delete(backup_id="expire", agent_ids=["local"])
    except BackupManagerActionsError as err:
        assert "local" in str(err)
    else:
        raise AssertionError("An unregistered provider was reported as verified")


async def test_create_rejects_partial_content_failure() -> None:
    """Stored copies alone do not prove that the requested contents succeeded."""
    for field, value in (("failed_addons", [Addon("core_mosquitto")]),
                         ("failed_folders", [Folder.SHARE])):
        manager = Manager()
        adapter = BackupManagerActionsAdapter(Hass(manager))
        original = manager.async_create_backup

        async def partial_create(**kwargs):
            result = await original(**kwargs)
            setattr(manager.backups["abc12345"], field, value)
            return result

        manager.async_create_backup = partial_create
        try:
            await create_default_backup(adapter)
        except BackupManagerActionsError as err:
            assert "content" in str(err)
        else:
            raise AssertionError(f"Create succeeded with {field}")


async def test_apply_preserves_progress_on_native_manager_error() -> None:
    """A native HA exception after one delete must still report prior progress."""
    manager, adapter = review_inventory()
    add_bma_backup(manager, "oldest", "2026-09-27T10:00:00+02:00")
    original = manager.async_get_backups

    async def fail_after_first_delete():
        if "oldest" not in manager.backups:
            raise HomeAssistantError("native inventory failure")
        return await original()

    manager.async_get_backups = fail_after_first_delete
    try:
        await adapter.async_apply_retention(**review_policy(["local"]))
    except BackupManagerActionsError as err:
        assert "expire" in str(err)
        assert "deleted before failure: oldest" in str(err)
    else:
        raise AssertionError("Native manager failure was not reported")
    assert "expire" in manager.backups


async def main() -> None:
    await test_apply_preserves_progress_on_native_manager_error()
    await test_retention_final_read_rechecks_metadata()
    await test_retention_agent_removed_during_listing_fails_closed()
    await test_retention_omitted_scope_is_frozen_during_apply()
    await test_delete_cannot_verify_an_unregistered_target()
    await test_create_rejects_partial_content_failure()

    await test_scenario_full_job_retention_isolated_from_other_sources()
    await test_scenario_ha_native_manual_and_automatic_share_one_policy()
    await test_scenario_app_update_per_app_is_independent_end_to_end()
    await test_apply_retention_is_serialized()
    await test_plan_and_apply_agree_when_inventory_is_unchanged()
    await test_apply_retention_recalculates_current_state()
    await test_apply_retention_preserves_out_of_scope_copies()
    await test_apply_retention_allows_late_encryption_flag()
    await test_apply_retention_handles_candidate_removed_by_other_actor()
    await test_apply_retention_aborts_on_late_classification_change()
    await test_apply_retention_aborts_on_late_scoped_agent_error()
    await test_apply_retention_counts_disappeared_scoped_copy_as_already_absent()
    await test_apply_retention_reports_copy_removed_after_revalidation()
    await test_apply_retention_revalidates_policy_between_candidates()
    await test_apply_retention_deletes_late_in_scope_copy()
    await test_apply_retention_failure_reports_prior_deletions()
    await test_plan_retention_is_read_only()
    await test_plan_retention_explicit_scope_ignores_unrelated_agent_error()
    await test_plan_retention_omitted_scope_fails_on_any_agent_error()
    await test_plan_retention_omitted_scope_uses_all_registered_agents()
    await test_plan_retention_rejects_missing_agent()
    await test_create_success()
    await test_create_with_full_job_id()
    await test_create_with_partial_job_id()
    await test_create_normalizes_job_id()
    await test_create_rejects_invalid_job_id_before_creation()
    await test_create_verifies_metadata_version_persistence()
    await test_create_rejects_noncanonical_metadata_version()
    await test_legacy_create_rejects_unexpected_invalid_stored_job_id()
    await test_create_verifies_job_id_persistence()
    await test_create_detects_missing_copy()
    await test_create_ignores_unrelated_agent_lookup_error()
    await test_create_rejects_reported_requested_agent_failure()
    await test_create_rejects_requested_agent_lookup_error()
    await test_create_rejects_unavailable_requested_agent()
    await test_delete_missing_backup_is_idempotent()
    await test_delete_global()
    await test_delete_selected_copy()
    await test_delete_selected_ignores_unrelated_lookup_error()
    await test_delete_explicit_rejects_missing_agent_before_delete()
    await test_delete_global_rejects_unverifiable_agent()
    await test_delete_reports_agent_error()
    await test_delete_post_verification_detects_remaining_copy()
    await test_snapshot_and_serialization()
    await test_snapshot_latest_uses_real_timestamp_across_offsets()
    await test_list_and_get_backup()
    print("adapter simulation: OK")


if __name__ == "__main__":
    asyncio.run(main())
