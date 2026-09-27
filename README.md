# Home Assistant Backup Manager Actions

> **Experimental / alpha** — this custom integration intentionally exposes advanced capabilities of Home Assistant's Backup Manager to automations. Test on non-critical backups first.

Backup Manager Actions is a small Home Assistant custom integration that acts as a bridge between automations and Home Assistant's native Backup Manager.

It does **not** implement a backup destination and it does **not** talk directly to S3, NAS, cloud providers, or the Supervisor. Instead it uses the Backup Agents already registered in Home Assistant and exposes operations that are available to the Backup frontend but are not all available as normal automation actions.

## Why

Home Assistant can store the same logical backup on multiple Backup Agents, including local storage and cloud integrations. The standard `backup.create_automatic` action uses the configuration saved in the Backup UI, but advanced automation use cases may need to select destinations and backup contents dynamically or delete one logical backup across all of its locations.

This integration fills that gap while leaving backup creation, encryption, storage and restore to Home Assistant itself.

### Retention behavior

Backups created by `backup_manager_actions.create` are **custom backups**, not backups created with Home Assistant's automatic settings. Home Assistant 2026.9 applies its built-in count/age retention only to backups marked as created with automatic settings. Therefore these custom backups are not pruned by Home Assistant's automatic retention and can be managed by an external/custom retention policy (for example GFS) using `backup_manager_actions.delete`.

## Current actions

### `backup_manager_actions.create`

Creates one backup and stores it on every selected Backup Agent. The action waits for completion and verifies that the new backup is readable from every requested agent. If an agent is unavailable or a copy is missing, the action fails instead of silently accepting a partial result.

```yaml
action: backup_manager_actions.create
data:
  agent_ids:
    - hassio.local
    - s3_compatible.example
  include_homeassistant: true
  include_database: true
  include_all_addons: true
  include_folders:
    - share
    - ssl
  name: "Backup {{ now().strftime('%Y-%m-%d') }}"
  password: !secret ha_backup_password
response_variable: backup_result
```

The response contains the `backup_id` plus requested/stored agents and per-agent size/protection information.

### `backup_manager_actions.delete`

Deletes one logical backup. When `agent_ids` is omitted, Home Assistant's Backup Manager is asked to delete that `backup_id` from all registered Backup Agents. The integration verifies that the requested copies disappeared.

```yaml
action: backup_manager_actions.delete
data:
  backup_id: "abc12345"
response_variable: delete_result
```

An optional `agent_ids` list can be supplied to remove only selected copies.

### `backup_manager_actions.refresh`

Refreshes the integration sensors from Backup Manager.

## Sensors

The integration intentionally avoids duplicating Home Assistant's native Backup sensors. It adds only information useful for advanced automation:

- **Backup agents** — number of currently registered agents, with IDs/names and agent errors as attributes.
- **Backups** — number of logical backups known across all agents.
- **Latest backup** — latest logical backup ID with full metadata as attributes, including the agents that hold it.

## Installation with HACS

Until this repository is added to the default HACS catalog:

1. HACS → Integrations → Custom repositories.
2. Add `https://github.com/paolo-hub/home-assistant-backup-manager-actions` as category **Integration**.
3. Install **Backup Manager Actions**.
4. Restart Home Assistant.
5. Settings → Devices & services → Add integration → **Backup Manager Actions**.
6. Confirm setup. There are no credentials or external settings.

## Compatibility

Minimum Home Assistant version: **2026.9.0**.

The integration deliberately keeps all Home Assistant Backup Manager calls in `adapter.py`. This limits the impact if Home Assistant changes its Python API in a future release.

## Safety model

- All actions are registered as **admin-only** services.
- `create` validates every requested Backup Agent before starting.
- `create` waits for completion and verifies every requested copy.
- `delete` first verifies the backup exists, performs the Home Assistant Backup Manager deletion, then verifies the requested copies are gone.
- Backup credentials for cloud agents remain owned by their respective Home Assistant integrations.
- No long-lived access token is required by this integration.

## Scope

This project intentionally does not expose restore as an automation action. Restore is disruptive and can restart Home Assistant, so the extra friction of the native Backup UI is retained by design.

## License

MIT
