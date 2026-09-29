"""Constants for Backup Manager Actions."""

from homeassistant.const import Platform

DOMAIN = "backup_manager_actions"
NAME = "Backup Manager Actions"

DATA_ADAPTER = "adapter"
DATA_COORDINATORS = "coordinators"
DATA_EVENT_TRACKER = "event_tracker"

EVENT_BACKUP_CREATED = "backup_manager_actions_backup_created"

SERVICE_CREATE = "create"
SERVICE_DELETE = "delete"
SERVICE_REFRESH = "refresh"
SERVICE_LIST_AGENTS = "list_agents"
SERVICE_LIST_BACKUPS = "list_backups"
SERVICE_GET_BACKUP = "get_backup"
SERVICE_PLAN_RETENTION = "plan_retention"
SERVICE_APPLY_RETENTION = "apply_retention"

CONF_AGENT_IDS = "agent_ids"
CONF_BACKUP_ID = "backup_id"
CONF_INCLUDE_HOMEASSISTANT = "include_homeassistant"
CONF_INCLUDE_DATABASE = "include_database"
CONF_INCLUDE_ALL_ADDONS = "include_all_addons"
CONF_INCLUDE_ADDONS = "include_addons"
CONF_INCLUDE_FOLDERS = "include_folders"
CONF_JOB_ID = "job_id"
CONF_NAME = "name"
CONF_PASSWORD = "password"
CONF_SOURCE_TYPE = "source_type"
CONF_GROUP_BY = "group_by"
CONF_KEEP_LAST = "keep_last"
CONF_DAILY = "daily"
CONF_WEEKLY = "weekly"
CONF_MONTHLY = "monthly"
CONF_YEARLY = "yearly"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
