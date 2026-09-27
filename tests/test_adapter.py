"""Lightweight behavioral tests for the adapter using local stubs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "adapter.py"


class Folder(StrEnum):
    SHARE = "share"
    ADDONS = "addons/local"
    SSL = "ssl"
    MEDIA = "media"


class HomeAssistantError(Exception):
    pass


backup_module = types.ModuleType("homeassistant.components.backup")
backup_module.Folder = Folder
backup_module.BackupManager = object
backup_module.async_get_manager = lambda hass: hass.manager
core_module = types.ModuleType("homeassistant.core")
core_module.HomeAssistant = object
exceptions_module = types.ModuleType("homeassistant.exceptions")
exceptions_module.HomeAssistantError = HomeAssistantError
components_module = types.ModuleType("homeassistant.components")
homeassistant_module = types.ModuleType("homeassistant")

sys.modules.setdefault("homeassistant", homeassistant_module)
sys.modules.setdefault("homeassistant.components", components_module)
sys.modules["homeassistant.components.backup"] = backup_module
sys.modules["homeassistant.core"] = core_module
sys.modules["homeassistant.exceptions"] = exceptions_module

spec = importlib.util.spec_from_file_location("backup_manager_actions_adapter", MODULE)
adapter_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = adapter_module
spec.loader.exec_module(adapter_module)

BackupManagerActionsAdapter = adapter_module.BackupManagerActionsAdapter
BackupManagerActionsError = adapter_module.BackupManagerActionsError


@dataclass
class Status:
    protected: bool = True
    size: int = 123


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
    def __init__(self, name: str) -> None:
        self.name = name


class NewBackup:
    def __init__(self, backup_job_id: str) -> None:
        self.backup_job_id = backup_job_id


class Manager:
    def __init__(self) -> None:
        self.state = "idle"
        self.backup_agents = {
            "local": Agent("Local"),
            "cloud": Agent("Cloud"),
            "third": Agent("Third"),
        }
        self.backups: dict[str, Backup] = {}
        self.create_agents = ["local", "cloud"]
        self.lookup_errors: dict[str, Exception] = {}
        self.delete_errors: dict[str, Exception] = {}

    async def async_create_backup(self, **kwargs):
        backup_id = "abc12345"
        self.backups[backup_id] = Backup(
            addons=[],
            backup_id=backup_id,
            date="2026-09-27T20:00:00+02:00",
            database_included=kwargs["include_database"],
            extra_metadata={},
            failed_addons=[],
            failed_agent_ids=[],
            failed_folders=[],
            folders=kwargs["include_folders"] or [],
            homeassistant_included=kwargs["include_homeassistant"],
            homeassistant_version="2026.9.3",
            name=kwargs["name"] or "Custom backup",
            with_automatic_settings=False,
            agents={agent_id: Status() for agent_id in self.create_agents},
        )
        return NewBackup(backup_id)

    async def async_get_backup(self, backup_id):
        return self.backups.get(backup_id), dict(self.lookup_errors)

    async def async_get_backups(self):
        return self.backups, dict(self.lookup_errors)

    async def async_delete_backup(self, backup_id, *, agent_ids=None):
        backup = self.backups.get(backup_id)
        if backup is None:
            return {}
        if agent_ids is None:
            self.backups.pop(backup_id, None)
        else:
            for agent_id in agent_ids:
                backup.agents.pop(agent_id, None)
            if not backup.agents:
                self.backups.pop(backup_id, None)
        return dict(self.delete_errors)


class Hass:
    def __init__(self, manager):
        self.manager = manager


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
    assert result["stored_agent_ids"] == ["cloud", "local"]


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


async def test_delete_global() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
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
    result = await adapter.async_delete(backup_id="abc12345")
    assert result["remaining_agent_ids"] == []
    assert "abc12345" not in manager.backups


async def test_delete_selected_copy() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
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
    result = await adapter.async_delete(
        backup_id="abc12345", agent_ids=["cloud"]
    )
    assert result["remaining_agent_ids"] == ["local"]


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


async def test_delete_selected_ignores_unrelated_lookup_error() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
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
    manager.lookup_errors = {"third": RuntimeError("offline")}
    result = await adapter.async_delete(
        backup_id="abc12345", agent_ids=["cloud"]
    )
    assert result["remaining_agent_ids"] == ["local"]


async def test_delete_global_rejects_unverifiable_agent() -> None:
    manager = Manager()
    adapter = BackupManagerActionsAdapter(Hass(manager))
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
    manager.delete_errors = {"cloud": RuntimeError("delete failed")}
    try:
        await adapter.async_delete(backup_id="abc12345")
    except BackupManagerActionsError as err:
        assert "was not deleted cleanly" in str(err)
    else:
        raise AssertionError("Agent deletion error should fail")


async def main() -> None:
    await test_create_success()
    await test_create_detects_missing_copy()
    await test_create_ignores_unrelated_agent_lookup_error()
    await test_create_rejects_unavailable_requested_agent()
    await test_delete_global()
    await test_delete_selected_copy()
    await test_delete_selected_ignores_unrelated_lookup_error()
    await test_delete_global_rejects_unverifiable_agent()
    await test_delete_reports_agent_error()
    print("adapter simulation: OK")


if __name__ == "__main__":
    asyncio.run(main())
