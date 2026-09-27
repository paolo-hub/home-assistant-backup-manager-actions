"""Service actions for Backup Manager Actions."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.components.backup import BackupManagerError, Folder, ManagerBackup
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .adapter import BackupManagerAdapter
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
    DOMAIN,
    SERVICE_CREATE,
    SERVICE_DELETE,
    SERVICE_GET_BACKUP,
    SERVICE_LIST_AGENTS,
    SERVICE_LIST_BACKUPS,
)
from .coordinator import BackupManagerActionsCoordinator


def _unique_string_list(value: list[str]) -> list[str]:
    """Normalize a list of strings and reject duplicates."""
    normalized = [item.strip() for item in value if item.strip()]
    if not normalized:
        raise vol.Invalid("At least one value is required")
    if len(normalized) != len(set(normalized)):
        raise vol.Invalid("Duplicate values are not allowed")
    return normalized


STRING_LIST = vol.All(cv.ensure_list, [cv.string], _unique_string_list)
OPTIONAL_STRING_LIST = vol.All(
    cv.ensure_list,
    [cv.string],
    lambda value: [item.strip() for item in value if item.strip()],
)

CREATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AGENT_IDS): STRING_LIST,
        vol.Optional(CONF_INCLUDE_ADDONS): OPTIONAL_STRING_LIST,
        vol.Optional(CONF_INCLUDE_ALL_ADDONS, default=False): cv.boolean,
        vol.Optional(CONF_INCLUDE_DATABASE, default=True): cv.boolean,
        vol.Optional(CONF_INCLUDE_FOLDERS): vol.All(
            cv.ensure_list,
            [vol.In([folder.value for folder in Folder])],
        ),
        vol.Optional(CONF_INCLUDE_HOMEASSISTANT, default=True): cv.boolean,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_PASSWORD): cv.string,
    }
)

DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BACKUP_ID): vol.All(cv.string, str.strip, vol.Length(min=1)),
        vol.Optional(CONF_AGENT_IDS): STRING_LIST,
    }
)

GET_BACKUP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BACKUP_ID): vol.All(cv.string, str.strip, vol.Length(min=1)),
    }
)


def _adapter(hass: HomeAssistant) -> BackupManagerAdapter:
    """Return the Backup Manager adapter."""
    return BackupManagerAdapter(hass)


def _serialize_backup(backup: ManagerBackup) -> dict[str, Any]:
    """Convert a ManagerBackup into JSON-serializable data."""
    return {
        "backup_id": backup.backup_id,
        "name": backup.name,
        "date": backup.date,
        "homeassistant_version": backup.homeassistant_version,
        "homeassistant_included": backup.homeassistant_included,
        "database_included": backup.database_included,
        "addons": [
            {
                "slug": addon.slug,
                "name": addon.name,
                "version": addon.version,
            }
            for addon in backup.addons
        ],
        "folders": [folder.value for folder in backup.folders],
        "agents": {
            agent_id: {
                "protected": status.protected,
                "size": status.size,
            }
            for agent_id, status in backup.agents.items()
        },
        "failed_addons": [
            {
                "slug": addon.slug,
                "name": addon.name,
                "version": addon.version,
            }
            for addon in backup.failed_addons
        ],
        "failed_agent_ids": backup.failed_agent_ids,
        "failed_folders": [folder.value for folder in backup.failed_folders],
        "with_automatic_settings": backup.with_automatic_settings,
    }


def _serialize_errors(errors: dict[str, Exception]) -> dict[str, str]:
    """Convert per-agent errors to strings."""
    return {agent_id: str(error) for agent_id, error in errors.items()}


def _validate_agent_ids(adapter: BackupManagerAdapter, agent_ids: list[str]) -> None:
    """Fail before an operation if any requested agent is not registered."""
    missing = [agent_id for agent_id in agent_ids if agent_id not in adapter.backup_agents]
    if missing:
        raise ServiceValidationError(
            "The following backup agents are not currently registered: "
            + ", ".join(missing)
        )


async def _refresh_entities(hass: HomeAssistant) -> None:
    """Refresh integration entities after an operation."""
    coordinators = [
        value
        for value in hass.data.get(DOMAIN, {}).values()
        if isinstance(value, BackupManagerActionsCoordinator)
    ]
    if coordinators:
        await asyncio.gather(
            *(coordinator.async_request_refresh() for coordinator in coordinators),
            return_exceptions=True,
        )


async def _handle_create(call: ServiceCall) -> ServiceResponse | None:
    """Create a backup using selected Backup Manager agents."""
    adapter = _adapter(call.hass)
    agent_ids = list(call.data[CONF_AGENT_IDS])
    _validate_agent_ids(adapter, agent_ids)

    include_addons = call.data.get(CONF_INCLUDE_ADDONS) or None
    include_all_addons = call.data[CONF_INCLUDE_ALL_ADDONS]
    if include_all_addons and include_addons:
        raise ServiceValidationError(
            "include_all_addons cannot be used together with include_addons"
        )

    folder_values = call.data.get(CONF_INCLUDE_FOLDERS)
    include_folders = (
        [Folder(folder) for folder in folder_values] if folder_values is not None else None
    )

    name = call.data.get(CONF_NAME)
    if name is not None:
        name = name.strip() or None

    try:
        new_backup = await adapter.async_create_backup(
            agent_ids=agent_ids,
            include_addons=include_addons,
            include_all_addons=include_all_addons,
            include_database=call.data[CONF_INCLUDE_DATABASE],
            include_folders=include_folders,
            include_homeassistant=call.data[CONF_INCLUDE_HOMEASSISTANT],
            name=name,
            password=call.data.get(CONF_PASSWORD),
        )
    except BackupManagerError as err:
        raise HomeAssistantError(f"Backup creation failed: {err}") from err

    backup, agent_errors = await adapter.async_get_backup(new_backup.backup_job_id)
    await _refresh_entities(call.hass)

    if backup is None:
        raise HomeAssistantError(
            f"Backup {new_backup.backup_job_id} completed but could not be found"
        )

    stored_agents = set(backup.agents)
    missing_agents = [agent_id for agent_id in agent_ids if agent_id not in stored_agents]
    if missing_agents:
        error_details = _serialize_errors(agent_errors)
        detail = f"; agent errors: {error_details}" if error_details else ""
        raise HomeAssistantError(
            "Backup was not stored on all requested agents. Missing: "
            + ", ".join(missing_agents)
            + detail
        )

    response = {
        "backup_id": backup.backup_id,
        "name": backup.name,
        "requested_agents": agent_ids,
        "stored_agents": list(backup.agents),
        "agent_errors": _serialize_errors(agent_errors),
    }
    return response if call.return_response else None


async def _handle_delete(call: ServiceCall) -> ServiceResponse | None:
    """Delete a backup from all or selected registered agents."""
    adapter = _adapter(call.hass)
    backup_id = call.data[CONF_BACKUP_ID]
    requested_agent_ids = call.data.get(CONF_AGENT_IDS)

    if requested_agent_ids is not None:
        agent_ids = list(requested_agent_ids)
        _validate_agent_ids(adapter, agent_ids)
    else:
        agent_ids = None

    backup_before, lookup_errors = await adapter.async_get_backup(backup_id)

    delete_errors = await adapter.async_delete_backup(
        backup_id,
        agent_ids=agent_ids,
    )
    await _refresh_entities(call.hass)

    if delete_errors:
        raise HomeAssistantError(
            f"Backup {backup_id} was only partially deleted; agent errors: "
            f"{_serialize_errors(delete_errors)}"
        )

    response = {
        "backup_id": backup_id,
        "found_before_delete": backup_before is not None,
        "agents_before_delete": list(backup_before.agents) if backup_before else [],
        "requested_agents": agent_ids or list(adapter.backup_agents),
        "lookup_agent_errors": _serialize_errors(lookup_errors),
    }
    return response if call.return_response else None


async def _handle_list_backups(call: ServiceCall) -> ServiceResponse:
    """List logical backups known to Backup Manager."""
    adapter = _adapter(call.hass)
    backups, agent_errors = await adapter.async_get_backups()
    ordered = sorted(backups.values(), key=lambda backup: backup.date, reverse=True)

    return {
        "backups": [_serialize_backup(backup) for backup in ordered],
        "agent_errors": _serialize_errors(agent_errors),
    }


async def _handle_get_backup(call: ServiceCall) -> ServiceResponse:
    """Get a logical backup by id."""
    adapter = _adapter(call.hass)
    backup, agent_errors = await adapter.async_get_backup(call.data[CONF_BACKUP_ID])

    return {
        "backup": _serialize_backup(backup) if backup is not None else None,
        "agent_errors": _serialize_errors(agent_errors),
    }


async def _handle_list_agents(call: ServiceCall) -> ServiceResponse:
    """List currently registered Backup Manager agents."""
    adapter = _adapter(call.hass)
    return {
        "agents": [
            {
                "agent_id": agent_id,
                "name": agent.name,
                "domain": agent.domain,
            }
            for agent_id, agent in adapter.backup_agents.items()
        ]
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register Backup Manager Actions services."""
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
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_LIST_AGENTS,
        _handle_list_agents,
        supports_response=SupportsResponse.ONLY,
    )
