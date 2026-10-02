"""Simulate HA's registry matching contract for a beta1 -> beta2 reload.

This is a boundary simulation, not a full Home Assistant registry integration
test. HA entity_platform looks up (platform, integration, unique_id), registers
device_info, and updates device_id on that existing entity registry entry.
"""

import asyncio
import importlib
from types import SimpleNamespace

import test_sensor as fixture
from device_registry_stub import DeviceEntryType

binary_module = SimpleNamespace(BinarySensorEntity=type("BinarySensorEntity", (), {}))
fixture.sys.modules["homeassistant.components.binary_sensor"] = binary_module
binary = importlib.import_module("custom_components.backup_manager_actions.binary_sensor")

EXPECTED = [
    ("sensor", "backup_agent_count"),
    ("sensor", "backup_count"),
    ("sensor", "latest_backup"),
    ("sensor", "bma_backup_count"),
    ("sensor", "ha_native_backup_count"),
    ("sensor", "app_update_backup_count"),
    ("sensor", "archive_size"),
    ("binary_sensor", "backup_agents_healthy"),
]


async def entities(entry_id="entry123"):
    coordinator = fixture.BackupManagerActionsCoordinator(fixture.sample_data())
    entry = fixture.ConfigEntry(entry_id, coordinator)
    added = []
    await fixture.sensor.async_setup_entry(None, entry, added.extend)
    await binary.async_setup_entry(None, entry, added.extend)
    return added


async def test_all_eight_entities_share_service_device():
    added = await entities()
    assert len(added) == 8
    for entity in added:
        assert entity._attr_device_info == {
            "identifiers": {("backup_manager_actions", "entry123")},
            "name": "Backup Manager Actions",
            "entry_type": DeviceEntryType.SERVICE,
        }
    assert len({e._attr_unique_id for e in added}) == 8


async def test_registry_reload_preserves_beta1_identities():
    # Include user-renamed IDs/names and a disabled entity in the old registry.
    registry = {
        (platform, "backup_manager_actions", f"entry123_{suffix}"): {
            "entity_id": f"{platform}.custom_{suffix}",
            "name": f"Custom {suffix}",
            "disabled_by": "user" if suffix == "archive_size" else None,
            "device_id": None,
        }
        for platform, suffix in EXPECTED
    }
    before = {key: dict(value) for key, value in registry.items()}
    devices = {}
    for _ in range(2):
        for (platform, suffix), entity in zip(EXPECTED, await entities(), strict=True):
            assert entity._attr_unique_id == f"entry123_{suffix}"
            key = (platform, "backup_manager_actions", entity._attr_unique_id)
            assert key in registry  # A new identity would create a duplicate.
            info = entity._attr_device_info
            device_key = ("entry123", frozenset(info["identifiers"]))
            device_id = devices.setdefault(device_key, "service-device")
            registry[key]["device_id"] = device_id
    assert len(devices) == 1
    assert len(registry) == 8
    for key, entry in registry.items():
        assert entry == {**before[key], "device_id": "service-device"}


async def main():
    await test_all_eight_entities_share_service_device()
    await test_registry_reload_preserves_beta1_identities()
    print("device registry boundary simulation: OK (2 tests)")


if __name__ == "__main__":
    asyncio.run(main())
