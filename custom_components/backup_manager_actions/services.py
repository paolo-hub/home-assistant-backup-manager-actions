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
    CONF_NAME,
    CONF_PASSWORD,
    DATA_COORDINATORS,
    DOMAIN,
    SERVICE_CREATE,
    SERVICE_DELETE,
    SERVICE_REFRESH,
)
from .coordinator import BackupManagerActionsCoordinator

AGENT_IDS_SCHEMA = vol.All(cv.ensure_list, [cv.string], vol.Length(min=1))

CREATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AGENT_IDS): AGENT_IDS_SCHEMA,
        vol.Optional(CONF_INCLUDE_HOMEASSISTANT, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE_DATABASE, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE_ALL_ADDONS, default=False): cv.boolean,
        vol.Optional(CONF_INCLUDE_ADDONS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(CONF_INCLUDE_FOLDERS): vol.All(
            cv.ensure_list, [vol.In([folder.value for folder in Folder])]
        ),
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BACKUP_ID): cv.string,
        vol.Optional(CONF_AGENT_IDS): AGENT_IDS_SCHEMA,
    }
)


async def _async_refresh_coordinators(hass: HomeAssistant) -> None:
    """Refresh every loaded sensor coordinator."""
    coordinators: set[BackupManagerActionsCoordinator] = hass.data[DOMAIN].get(
        DATA_COORDINATORS, set()
    )
    if coordinators:
        await asyncio.gather(
            *(coordinator.async_request_refresh() for coordinator in coordinators)
        )


@callback
def async_setup_services(
    hass: HomeAssistant, adapter: BackupManagerActionsAdapter
) -> None:
    """Register admin-only actions at integration setup time."""

    async def _handle_create(call: ServiceCall) -> ServiceResponse:
        result = await adapter.async_create(
            agent_ids=call.data[CONF_AGENT_IDS],
            include_homeassistant=call.data[CONF_INCLUDE_HOMEASSISTANT],
            include_database=call.data[CONF_INCLUDE_DATABASE],
            include_all_addons=call.data[CONF_INCLUDE_ALL_ADDONS],
            include_addons=call.data.get(CONF_INCLUDE_ADDONS),
            include_folders=call.data.get(CONF_INCLUDE_FOLDERS),
            name=call.data.get(CONF_NAME),
            password=call.data.get(CONF_PASSWORD) or None,
        )
        await _async_refresh_coordinators(hass)
        return result if call.return_response else None

    async def _handle_delete(call: ServiceCall) -> ServiceResponse:
        result = await adapter.async_delete(
            backup_id=call.data[CONF_BACKUP_ID],
            agent_ids=call.data.get(CONF_AGENT_IDS),
        )
        await _async_refresh_coordinators(hass)
        return result if call.return_response else None

    async def _handle_refresh(call: ServiceCall) -> ServiceResponse:
        snapshot = await adapter.async_snapshot()
        await _async_refresh_coordinators(hass)
        return snapshot if call.return_response else None

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
