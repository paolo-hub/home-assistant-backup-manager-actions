"""Coordinator simulation for new-backup event lifecycle."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "custom_components" / "backup_manager_actions" / "coordinator.py"

custom_components_module = types.ModuleType("custom_components")
custom_components_module.__path__ = [str(ROOT / "custom_components")]
package_module = types.ModuleType("custom_components.backup_manager_actions")
package_module.__path__ = [
    str(ROOT / "custom_components" / "backup_manager_actions")
]
sys.modules.setdefault("custom_components", custom_components_module)
sys.modules.setdefault("custom_components.backup_manager_actions", package_module)

# Load the real pure event tracker used by the coordinator.
events_spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.events",
    ROOT / "custom_components" / "backup_manager_actions" / "events.py",
)
events_module = importlib.util.module_from_spec(events_spec)
assert events_spec and events_spec.loader
sys.modules[events_spec.name] = events_module
events_spec.loader.exec_module(events_module)

adapter_module = types.ModuleType("custom_components.backup_manager_actions.adapter")
adapter_module.BackupManagerActionsAdapter = object
sys.modules["custom_components.backup_manager_actions.adapter"] = adapter_module

const_module = types.ModuleType("custom_components.backup_manager_actions.const")
const_module.DOMAIN = "backup_manager_actions"
const_module.EVENT_BACKUP_CREATED = "backup_manager_actions_backup_created"
sys.modules["custom_components.backup_manager_actions.const"] = const_module


class BackupPlatformEvent:
    """Stub backup platform event."""


class IdleEvent:
    """Stub Backup Manager idle event."""


backup_module = types.ModuleType("homeassistant.components.backup")
backup_module.BackupPlatformEvent = BackupPlatformEvent
backup_module.IdleEvent = IdleEvent
components_module = types.ModuleType("homeassistant.components")
config_entries_module = types.ModuleType("homeassistant.config_entries")
config_entries_module.ConfigEntry = object
core_module = types.ModuleType("homeassistant.core")
core_module.HomeAssistant = object
core_module.callback = lambda func: func
homeassistant_module = types.ModuleType("homeassistant")


class UpdateFailed(Exception):
    """Stub coordinator update failure."""


class DataUpdateCoordinator:
    """Small async-compatible DataUpdateCoordinator stub."""

    @classmethod
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, hass, _logger, **_kwargs):
        self.hass = hass
        self.data = None

    async def async_request_refresh(self):
        self.data = await self._async_update_data()
        self._async_refresh_finished()
        return self.data


update_module = types.ModuleType("homeassistant.helpers.update_coordinator")
update_module.DataUpdateCoordinator = DataUpdateCoordinator
update_module.UpdateFailed = UpdateFailed
helpers_module = types.ModuleType("homeassistant.helpers")

sys.modules.setdefault("homeassistant", homeassistant_module)
sys.modules.setdefault("homeassistant.components", components_module)
sys.modules["homeassistant.components.backup"] = backup_module
sys.modules["homeassistant.config_entries"] = config_entries_module
sys.modules["homeassistant.core"] = core_module
sys.modules.setdefault("homeassistant.helpers", helpers_module)
sys.modules["homeassistant.helpers.update_coordinator"] = update_module

spec = importlib.util.spec_from_file_location(
    "custom_components.backup_manager_actions.coordinator",
    MODULE,
)
coordinator_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = coordinator_module
spec.loader.exec_module(coordinator_module)

BackupManagerActionsCoordinator = coordinator_module.BackupManagerActionsCoordinator
BackupCreatedEventTracker = events_module.BackupCreatedEventTracker


class Bus:
    """Capture fired Home Assistant events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, event_data: dict) -> None:
        self.events.append((event_type, event_data))


class Hass:
    """Minimal Home Assistant stub."""

    def __init__(self) -> None:
        self.bus = Bus()
        self.tasks = []

    def async_create_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class Manager:
    """Capture Backup Manager subscriptions."""

    def __init__(self) -> None:
        self.backup_callback = None
        self.platform_callback = None

    def async_subscribe_events(self, callback):
        self.backup_callback = callback
        return lambda: None

    def async_subscribe_platform_events(self, callback):
        self.platform_callback = callback
        return lambda: None


class Adapter:
    """Queue coherent snapshot/inventory responses."""

    def __init__(self) -> None:
        self.manager = Manager()
        self.responses: list[tuple[dict, list[dict]]] = []

    async def async_snapshot_with_backups(self):
        if not self.responses:
            raise AssertionError("No queued snapshot")
        return self.responses.pop(0)


async def settle_tasks(hass: Hass) -> None:
    """Wait for tasks spawned while processing a coordinator refresh."""
    while pending := [task for task in hass.tasks if not task.done()]:
        await asyncio.gather(*pending)


async def refresh(coordinator, hass: Hass) -> None:
    """Run one coordinator refresh and settle deferred event publication."""
    await coordinator.async_request_refresh()
    await settle_tasks(hass)


def normalized_backup(
    backup_id: str,
    source_type: str,
    *,
    date: str,
    job_id: str | None = None,
    app_slug: str | None = None,
    agents: dict | None = None,
) -> dict:
    """Build one normalized inventory item."""
    return {
        "backup_id": backup_id,
        "name": f"Backup {backup_id}",
        "date": date,
        "source_type": source_type,
        "job_id": job_id,
        "app_slug": app_slug,
        "agents": agents
        if agents is not None
        else {"local": {"size": 100, "protected": False}},
        "failed_agent_ids": [],
        "with_automatic_settings": False,
    }


def snapshot(*, complete: bool) -> dict:
    """Build the coordinator fields relevant to event processing."""
    return {
        "inventory_complete": complete,
        "agent_errors": {} if complete else {"cloud": "offline"},
    }


def verified_result(backup_id: str = "bma-new") -> dict:
    """Build a verified create response."""
    return {
        "backup_id": backup_id,
        "name": "BMA Full",
        "date": "2026-09-29T11:00:00+02:00",
        "source_type": "bma",
        "job_id": "full",
        "metadata_version": 1,
        "failed_agent_ids": [],
        "with_automatic_settings": False,
        "stored_agent_ids": ["local", "cloud"],
        "protected_by_agent": {"local": False, "cloud": False},
        "size_by_agent": {"local": 100, "cloud": 120},
    }


async def test_incomplete_inventory_cannot_establish_baseline() -> None:
    """A partial provider view must never create a false startup delta."""
    hass = Hass()
    adapter = Adapter()
    tracker = BackupCreatedEventTracker()
    coordinator = BackupManagerActionsCoordinator(hass, object(), adapter, tracker)

    historical = normalized_backup(
        "historical",
        "ha_native",
        date="2026-09-28T10:00:00+02:00",
    )

    adapter.responses.append((snapshot(complete=False), [historical]))
    await refresh(coordinator, hass)
    assert tracker.baseline_ready is False
    assert hass.bus.events == []

    adapter.responses.append((snapshot(complete=True), [historical]))
    await refresh(coordinator, hass)
    assert tracker.baseline_ready is True
    assert hass.bus.events == []

    new_backup = normalized_backup(
        "native-new",
        "ha_native",
        date="2026-09-29T10:00:00+02:00",
    )
    adapter.responses.append(
        (snapshot(complete=True), [historical, new_backup])
    )
    await refresh(coordinator, hass)

    assert len(hass.bus.events) == 1
    event_type, event_data = hass.bus.events[0]
    assert event_type == "backup_manager_actions_backup_created"
    assert event_data["backup_id"] == "native-new"


async def test_incomplete_refresh_does_not_consume_future_new_id() -> None:
    """A new id first seen in a failed inventory emits after recovery."""
    hass = Hass()
    adapter = Adapter()
    tracker = BackupCreatedEventTracker()
    coordinator = BackupManagerActionsCoordinator(hass, object(), adapter, tracker)

    adapter.responses.append((snapshot(complete=True), []))
    await refresh(coordinator, hass)

    new_backup = normalized_backup(
        "app-new",
        "app_update",
        app_slug="core_mosquitto",
        date="2026-09-29T10:00:00+02:00",
    )
    adapter.responses.append((snapshot(complete=False), [new_backup]))
    await refresh(coordinator, hass)
    assert hass.bus.events == []

    adapter.responses.append((snapshot(complete=True), [new_backup]))
    await refresh(coordinator, hass)
    assert [event[1]["backup_id"] for event in hass.bus.events] == ["app-new"]


async def test_bma_event_waits_for_verified_create() -> None:
    """An IdleEvent refresh may see BMA early, but verification gates the event."""
    hass = Hass()
    adapter = Adapter()
    tracker = BackupCreatedEventTracker()
    coordinator = BackupManagerActionsCoordinator(hass, object(), adapter, tracker)

    adapter.responses.append((snapshot(complete=True), []))
    await refresh(coordinator, hass)

    bma = normalized_backup(
        "bma-new",
        "bma",
        job_id="full",
        date="2026-09-29T11:00:00+02:00",
    )
    adapter.responses.append((snapshot(complete=True), [bma]))
    await refresh(coordinator, hass)
    assert hass.bus.events == []

    coordinator.async_publish_verified_bma_create(verified_result())
    assert [event[1]["backup_id"] for event in hass.bus.events] == ["bma-new"]

    coordinator.async_publish_verified_bma_create(verified_result())
    assert len(hass.bus.events) == 1

    adapter.responses.append((snapshot(complete=True), [bma]))
    await refresh(coordinator, hass)
    assert len(hass.bus.events) == 1


async def test_late_agent_copy_does_not_duplicate_event() -> None:
    """Changing copies of one logical id must not create another event."""
    hass = Hass()
    adapter = Adapter()
    tracker = BackupCreatedEventTracker()
    coordinator = BackupManagerActionsCoordinator(hass, object(), adapter, tracker)

    adapter.responses.append((snapshot(complete=True), []))
    await refresh(coordinator, hass)

    first = normalized_backup(
        "native-new",
        "ha_native",
        date="2026-09-29T10:00:00+02:00",
        agents={"local": {"size": 100, "protected": False}},
    )
    adapter.responses.append((snapshot(complete=True), [first]))
    await refresh(coordinator, hass)
    assert len(hass.bus.events) == 1

    with_copy = normalized_backup(
        "native-new",
        "ha_native",
        date="2026-09-29T10:00:00+02:00",
        agents={
            "local": {"size": 100, "protected": False},
            "cloud": {"size": 120, "protected": False},
        },
    )
    adapter.responses.append((snapshot(complete=True), [with_copy]))
    await refresh(coordinator, hass)
    assert len(hass.bus.events) == 1


async def test_backup_manager_idle_event_requests_refresh() -> None:
    """Existing Backup Manager subscriptions still request coordinator refresh."""
    hass = Hass()
    adapter = Adapter()
    tracker = BackupCreatedEventTracker()
    coordinator = BackupManagerActionsCoordinator(hass, object(), adapter, tracker)

    adapter.responses.append((snapshot(complete=True), []))
    coordinator.async_subscribe()
    assert adapter.manager.backup_callback is not None

    adapter.manager.backup_callback(IdleEvent())
    await settle_tasks(hass)
    assert tracker.baseline_ready is True


async def main() -> None:
    await test_incomplete_inventory_cannot_establish_baseline()
    await test_incomplete_refresh_does_not_consume_future_new_id()
    await test_bma_event_waits_for_verified_create()
    await test_late_agent_copy_does_not_duplicate_event()
    await test_backup_manager_idle_event_requests_refresh()
    print("coordinator event simulation: OK")


if __name__ == "__main__":
    asyncio.run(main())
