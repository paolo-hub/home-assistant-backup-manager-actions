"""Constants for Backup Manager Actions."""

DOMAIN = "backup_manager_actions"
NAME = "Backup Manager Actions"

SERVICE_CREATE = "create"
SERVICE_DELETE = "delete"
SERVICE_LIST_BACKUPS = "list_backups"
SERVICE_GET_BACKUP = "get_backup"
SERVICE_LIST_AGENTS = "list_agents"

CONF_AGENT_IDS = "agent_ids"
CONF_BACKUP_ID = "backup_id"
CONF_INCLUDE_ADDONS = "include_addons"
CONF_INCLUDE_ALL_ADDONS = "include_all_addons"
CONF_INCLUDE_DATABASE = "include_database"
CONF_INCLUDE_FOLDERS = "include_folders"
CONF_INCLUDE_HOMEASSISTANT = "include_homeassistant"
CONF_NAME = "name"
CONF_PASSWORD = "password"

ATTR_AGENTS = "agents"
ATTR_AGENT_ERRORS = "agent_errors"
