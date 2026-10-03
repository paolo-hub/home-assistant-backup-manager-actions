"""Actions exposed by Backup Manager Actions."""

from __future__ import annotations

import asyncio
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
    CONF_DAILY,
    CONF_GROUP_BY,
    CONF_INCLUDE_ADDONS,
    CONF_INCLUDE_ALL_ADDONS,
    CONF_INCLUDE_DATABASE,
    CONF_INCLUDE_FOLDERS,
    CONF_INCLUDE_HOMEASSISTANT,
    CONF_JOB_ID,
    CONF_KEEP_LAST,
    CONF_MONTHLY,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SOURCE_TYPE,
    CONF_WEEKLY,
    CONF_YEARLY,
    DATA_COORDINATORS,
    DOMAIN,
    EVENT_BACKUP_CREATED,
    SERVICE_APPLY_RETENTION,
    SERVICE_CREATE,
    SERVICE_DELETE,
    SERVICE_GET_BACKUP,
    SERVICE_LIST_AGENTS,
    SERVICE_LIST_BACKUPS,
    SERVICE_PLAN_RETENTION,
    SERVICE_REFRESH,
)
from .coordinator import BackupManagerActionsCoordinator
from .events import BackupCreatedEventTracker
from .inventory import (
    SOURCE_APP_UPDATE,
    SOURCE_BMA,
    SOURCE_HA_NATIVE,
    normalize_job_id,
)
from .retention import (
    APP_GROUP_BY_ALL,
    APP_GROUP_BY_APP,
    RetentionPolicyError,
    normalize_retention_counter,
)


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


def _retention_counter(value: object) -> int:
    """Normalize one public retention counter for the action schema."""
    try:
        return normalize_retention_counter(value)
    except RetentionPolicyError as err:
        raise vol.Invalid(str(err)) from err


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
        vol.Optional(CONF_JOB_ID): _job_id,
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


RETENTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOURCE_TYPE): vol.In(
            [SOURCE_BMA, SOURCE_HA_NATIVE, SOURCE_APP_UPDATE]
        ),
        vol.Optional(CONF_JOB_ID): _job_id,
        vol.Optional(CONF_GROUP_BY): vol.In(
            [APP_GROUP_BY_APP, APP_GROUP_BY_ALL]
        ),
        vol.Optional(CONF_AGENT_IDS): AGENT_IDS_SCHEMA,
        vol.Optional(CONF_KEEP_LAST, default=0): _retention_counter,
        vol.Optional(CONF_DAILY, default=0): _retention_counter,
        vol.Optional(CONF_WEEKLY, default=0): _retention_counter,
        vol.Optional(CONF_MONTHLY, default=0): _retention_counter,
        vol.Optional(CONF_YEARLY, default=0): _retention_counter,
    }
)


async def _async_refresh_coordinators(hass: HomeAssistant) -> None:
    """Wait for fresh diagnostics, bypassing the debounced request queue."""
    coordinators: set[BackupManagerActionsCoordinator] = hass.data[DOMAIN].get(
        DATA_COORDINATORS,
        set(),
    )
    if coordinators:
        await asyncio.gather(
            *(coordinator.async_refresh() for coordinator in tuple(coordinators)),
            return_exceptions=True,
        )


@callback
def async_setup_services(
    hass: HomeAssistant,
    adapter: BackupManagerActionsAdapter,
    event_tracker: BackupCreatedEventTracker,
) -> None:
    """Register admin-only actions at integration setup time."""

    async def _handle_create(call: ServiceCall) -> ServiceResponse | None:
        try:
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
        finally:
            await _async_refresh_coordinators(hass)

        coordinators: set[BackupManagerActionsCoordinator] = hass.data[DOMAIN].get(
            DATA_COORDINATORS,
            set(),
        )
        if coordinators:
            for coordinator in tuple(coordinators):
                coordinator.async_publish_verified_bma_create(result)
        else:
            event_data = event_tracker.record_verified_bma_create(result)
            if event_data is not None:
                hass.bus.async_fire(EVENT_BACKUP_CREATED, event_data)

        return result if call.return_response else None

    async def _handle_delete(call: ServiceCall) -> ServiceResponse | None:
        try:
            result = await adapter.async_delete(
                backup_id=call.data[CONF_BACKUP_ID],
                agent_ids=call.data.get(CONF_AGENT_IDS),
            )
        finally:
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

    async def _handle_plan_retention(call: ServiceCall) -> ServiceResponse:
        return await adapter.async_plan_retention(
            source_type=call.data[CONF_SOURCE_TYPE],
            job_id=call.data.get(CONF_JOB_ID),
            group_by=call.data.get(CONF_GROUP_BY),
            agent_ids=call.data.get(CONF_AGENT_IDS),
            keep_last=call.data[CONF_KEEP_LAST],
            daily=call.data[CONF_DAILY],
            weekly=call.data[CONF_WEEKLY],
            monthly=call.data[CONF_MONTHLY],
            yearly=call.data[CONF_YEARLY],
        )

    async def _handle_apply_retention(call: ServiceCall) -> ServiceResponse:
        try:
            result = await adapter.async_apply_retention(
                source_type=call.data[CONF_SOURCE_TYPE],
                job_id=call.data.get(CONF_JOB_ID),
                group_by=call.data.get(CONF_GROUP_BY),
                agent_ids=call.data.get(CONF_AGENT_IDS),
                keep_last=call.data[CONF_KEEP_LAST],
                daily=call.data[CONF_DAILY],
                weekly=call.data[CONF_WEEKLY],
                monthly=call.data[CONF_MONTHLY],
                yearly=call.data[CONF_YEARLY],
            )
        finally:
            await _async_refresh_coordinators(hass)
        return result

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
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_PLAN_RETENTION,
        _handle_plan_retention,
        schema=RETENTION_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_APPLY_RETENTION,
        _handle_apply_retention,
        schema=RETENTION_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
