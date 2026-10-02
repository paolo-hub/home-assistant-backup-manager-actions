"""Small device API boundary shared by standalone entity simulations."""

from enum import StrEnum
import sys
import types


class DeviceEntryType(StrEnum):
    SERVICE = "service"


def install() -> None:
    """Provide DeviceInfo and Platform without loading Home Assistant."""
    module = types.ModuleType("homeassistant.helpers.device_registry")
    module.DeviceInfo = dict
    module.DeviceEntryType = DeviceEntryType
    sys.modules[module.__name__] = module
    const = sys.modules.setdefault(
        "homeassistant.const", types.ModuleType("homeassistant.const")
    )
    const.Platform = types.SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor")
