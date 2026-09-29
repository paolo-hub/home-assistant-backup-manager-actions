"""Actions exposed by Backup Manager Actions."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components.backup import Folder
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .adapter import BackupManagerActionsAdapter
from .const import (
    CONF_AGENT_IDS,
    CONF_BACKUP_ID,
    CONF_INCLUDE_ADDONS,
    CONF_INCLUDE_ALL_ADDONS,
    CONF_INCLUDE_DATABASE,
    CONF_INCLUDE_FOLDERS,
    CONF_INCLUDE_HOMEASSISTANT,
    CONF_JOB_ID,
    CONF_NAME,
    CONF_PASSWORD,
    DATA_COORDINATORS,
    DOMAIN,
    SERVICE_CREATE,
    SERVICE_DELETE,
    SERVICE_GET_BACKUP,
    SERVICE_LIST_AGENTS,
    SERVICE_LIST_BACKUPS,
    SERVICE_REFRESH,
)
from .coordinator import BackupManagerActionsCoordinator
from .inventory import normalize_job_id


def _non_empty_unique_strings(value: list[str]) -> list[str]:
    """Normalize a list of strings and reject empty or duplicate values."""
    normalized = [item.strip() for item in value]
    if any(not item for item in normalized):
        raise vol.Invalid("Empty values are not allowed")
    if len(normalized) != len(set(normalized)):
        raise vol.Invalid("Duplicate values are not allowed")
    return normalized


def _optional_unique_strings(value: list[str]) -> list[str]:
    """Normalize an optional string list and reject duplicates."""
    normalized = [item.strip() for item in value if item.strip()]
    if len(normalized) != len(set(normalized)):
        raise vol.Invalid("Duplicate values are not allowed")
    return normalized


def _job_id(value: str) -> str:
    """Normalize and validate a BMA job id."""
    normalized = normalize_job_id(value)
    if normalized is None:
        raise vol.Invalid(
            "job_id must match ^[a-z0-9][a-z0-9_-]{0,63}$"
        )
    return normalized


AGENT_IDS_SCHEMA = vol.All(
    cv.ensure_list,
    [cv.string],
    vol.Length(min=1),
    _non_empty_unique_strings,
)
OPTIONAL_STRING_LIST_SCHEMA = vol.All(
    cv.ensure_list,
    [cv.string],
    _optional_unique_strings,
)

CREATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AGENT_IDS): AGENT_IDS_SCHEMA,
        vol.Optional(CONF_INCLUDE_HOMEASSISTANT, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE_DATABASE, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE_ALL_ADDONS, default=False): cv.boolean,
        vol.Optional(CONF_INCLUDE_ADDONS): OPTIONAL_STRING_LIST_SCHEMA,
        vol.Optional(CONF_INCLUDE_FOLDERS): vol.All(
            cv.ensure_list,
            [vol.In([folder.value for folder in Folder])],
        ),
        vol.Optional(CONF_JOB_ID): vol.All(cv.string, _job_id),
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BACKUP_ID): vol.All(
            cv.string,
            str.strip,
            vol.Length(min=1),
        ),
        vol.Optional(CONF_AGENT_IDS): AGENT_IDS_SCHEMA,
    }
)

GET_BACKUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BACKUP_ID): vol.All(
            cv.string,
            str.strip,
            vol.Length(min=1),
        ),
    }
)


async def _async_refresh_coordinators(hass: HomeAssistant) -> None:
    """Refresh every loaded sensor coordinator."""
    coordinators: set[BackupManagerActionsCoordinator] = hass.data[DOMAIN].get(
        DATA_COORDINATORS,
        set(),
    )
    if coordinators:
        await asyncio.gather(
            *(coordinator.async_request_refresh() for coordinator in coordinators),
            return_exceptions=True,
        )


@callback
def async_setup_services(
    hass: HomeAssistant,
    adapter: BackupManagerActionsAdapter,
) -> None:
    """Register admin-only actions at integration setup time."""

    async def _handle_create(call: ServiceCall) -> ServiceResponse | None:
        result = await adapter.async_create(
            agent_ids=call.data[CONF_AGENT_IDS],
            include_homeassistant=call.data[CONF_INCLUDE_HOMEASSISTANT],
            include_database=call.data[CONF_INCLUDE_DATABASE],
            include_all_addons=call.data[CONF_INCLUDE_ALL_ADDONS],
            include_addons=call.data.get(CONF_INCLUDE_ADDONS) or None,
            include_folders=call.data.get(CONF_INCLUDE_FOLDERS),
            job_id=call.data.get(CONF_JOB_ID),
            name=(call.data.get(CONF_NAME) or "").strip() or None,
            password=call.data.get(CONF_PASSWORD) or None,
        )
        await _async_refresh_coordinators(hass)
        return result if call.return_response else None

    async def _handle_delete(call: ServiceCall) -> ServiceResponse | None:
        result = await adapter.async_delete(
            backup_id=call.data[CONF_BACKUP_ID],
            agent_ids=call.data.get(CONF_AGENT_IDS),
        )
        await _async_refresh_coordinators(hass)
        return result if call.return_response else None

    async def _handle_refresh(call: ServiceCall) -> ServiceResponse | None:
        snapshot = await adapter.async_snapshot()
        await _async_refresh_coordinators(hass)
        return snapshot if call.return_response else None

    async def _handle_list_agents(_call: ServiceCall) -> ServiceResponse:
        return {
            "agents": [
                {
                    "agent_id": agent_id,
                    **details,
                }
                for agent_id, details in adapter.list_agents().items()
            ]
        }

    async def _handle_list_backups(_call: ServiceCall) -> ServiceResponse:
        return await adapter.async_list_backups()

    async def _handle_get_backup(call: ServiceCall) -> ServiceResponse:
        return await adapter.async_get_backup(call.data[CONF_BACKUP_ID])

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE,
        _handle_create,
        schema=CREATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DELETE,
        _handle_delete,
        schema=DELETE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_REFRESH,
        _handle_refresh,
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LIST_AGENTS,
        _handle_list_agents,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LIST_BACKUPS,
        _handle_list_backups,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_GET_BACKUP,
        _handle_get_backup,
        schema=GET_BACKUP_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
