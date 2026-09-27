"""Constants for Backup Manager Actions."""

from homeassistant.const import Platform

DOMAIN = "backup_manager_actions"
NAME = "Backup Manager Actions"

DATA_ADAPTER = "adapter"
DATA_COORDINATORS = "coordinators"

SERVICE_CREATE = "create"
SERVICE_DELETE = "delete"
SERVICE_REFRESH = "refresh"

CONF_AGENT_IDS = "agent_ids"
CONF_BACKUP_ID = "backup_id"
CONF_INCLUDE_HOMEASSISTANT = "include_homeassistant"
CONF_INCLUDE_DATABASE = "include_database"
CONF_INCLUDE_ALL_ADDONS = "include_all_addons"
CONF_INCLUDE_ADDONS = "include_addons"
CONF_INCLUDE_FOLDERS = "include_folders"
CONF_NAME = "name"
CONF_PASSWORD = "password"

PLATFORMS = [Platform.SENSOR]
