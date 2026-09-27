"""Base entities for Backup Manager Actions."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import BackupManagerActionsCoordinator


class BackupManagerActionsEntity(CoordinatorEntity[BackupManagerActionsCoordinator]):
    """Base entity for Backup Manager Actions."""

    _attr_has_entity_name = True
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, "backup_manager")},
        name=NAME,
        manufacturer="Home Assistant Community",
        model="Backup Manager bridge",
    )
