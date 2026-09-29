# Home Assistant Backup Manager Actions

[![Release](https://img.shields.io/github/v/release/paolo-hub/home-assistant-backup-manager-actions?style=flat-square&label=release)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/releases)
[![Maintainer](https://img.shields.io/badge/maintainer-paolo--hub-555?style=flat-square&logo=github)](https://github.com/paolo-hub)
[![Stars](https://img.shields.io/github/stars/paolo-hub/home-assistant-backup-manager-actions?style=flat-square)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/stargazers)
[![Issues](https://img.shields.io/github/issues/paolo-hub/home-assistant-backup-manager-actions?style=flat-square)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/issues)
[![Validate](https://github.com/paolo-hub/home-assistant-backup-manager-actions/actions/workflows/validate.yml/badge.svg)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/actions/workflows/validate.yml)

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5?style=flat-square&logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat-square)](https://www.hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/blob/main/LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/paolo-hub/home-assistant-backup-manager-actions?style=flat-square)](https://github.com/paolo-hub/home-assistant-backup-manager-actions/commits/main)

**Backup Manager Actions** is a Home Assistant custom integration that exposes the native Backup Manager to automations. It lets automations create, inspect, verify, and delete logical backups across multiple Backup Agents while leaving storage, encryption, credentials, and restore handling to Home Assistant and the selected providers.

The integration is provider-agnostic: it works with Backup Agents already registered in Home Assistant, such as local storage, network backup locations, and cloud backup integrations.

## Why

Home Assistant can store one logical backup on multiple Backup Agents. The standard backup UI and automatic backup configuration cover the common case, but advanced automation workflows may need to:

- choose backup destinations dynamically;
- choose backup contents dynamically;
- verify that every requested destination actually received the backup;
- inspect logical backups across all registered agents;
- delete one logical backup from an explicit set of destinations;
- apply a custom retention policy such as GFS.

Backup Manager Actions provides those operations without implementing a storage backend of its own.

## Safety model

Backup operations are intentionally fail-closed where possible:

- all actions are registered as **admin-only** services;
- `create` validates every requested Backup Agent before starting;
- `create` waits for completion and verifies every requested copy;
- newly created backups receive internal correlation metadata so the final logical `backup_id` can be identified reliably after the Supervisor job completes;
- `delete` validates explicitly requested agents, performs a pre-flight read, deletes the requested copies, and reads the backup back to verify they disappeared;
- deletion is idempotent when the requested state is already satisfied;
- provider credentials remain owned by their Home Assistant integrations;
- restore is deliberately **not** exposed as an automation action.

Multi-agent deletion cannot be transactional across independent providers. If one provider fails after another has already deleted its copy, the action reports failure and can be safely retried.

## 1.1 development branch

`feature/bma-1.1` is under pre-release validation; the stable release remains 1.0.x.
The normative [1.1 specification](docs/API_1.1_SPEC.md) describes `job_id`,
classification, new-backup events, archive diagnostics, and the new
`plan_retention` / `apply_retention` actions.

**Encryption semantics:** Home Assistant's `protected` field means password
encryption. Encrypted backups participate in normal GFS retention and may be
deleted when they expire. BMA does not currently implement retention holds.

`plan_retention` is read-only. `apply_retention` recalculates the policy, fixes
its evaluation time and resolved agent scope for the invocation, and revalidates
before each delete. Supply explicit `agent_ids` when all expected destinations
must be registered. The package owns policy/scheduling; BMA does not persist them.

See the [independent pre-E2E review](docs/PRE_E2E_REVIEW.md) for corrected defects,
simulation coverage, and the remaining real-provider acceptance checks.

## Actions

### `backup_manager_actions.create`

Creates one backup and stores it on every selected Backup Agent.

```yaml
action: backup_manager_actions.create
data:
  agent_ids:
    - hassio.local
    - hassio.Backup
  include_homeassistant: true
  include_database: true
  include_all_addons: false
  include_addons: []
  include_folders: []
  name: "Backup {{ now().strftime('%Y-%m-%d') }}"
response_variable: backup_result
```

The response includes the final logical `backup_id`, the Supervisor `backup_job_id`, requested/stored agents, and per-agent size/encryption information.

Backups created by this action are custom backups (`with_automatic_settings: false`). They are therefore suitable for an external/custom retention policy rather than Home Assistant's automatic-backup retention.

### `backup_manager_actions.delete`

Deletes one logical backup from all registered agents or from an explicit list.

```yaml
action: backup_manager_actions.delete
data:
  backup_id: "abc12345"
  agent_ids:
    - hassio.local
    - hassio.Backup
response_variable: delete_result
```

For retention jobs, explicitly supply every expected destination. This makes the action fail closed if an expected provider is temporarily not registered.

### `backup_manager_actions.get_backup`

Returns one logical backup and the agents that currently contain it.

```yaml
action: backup_manager_actions.get_backup
data:
  backup_id: "abc12345"
```

### `backup_manager_actions.list_backups`

Returns all logical backups visible to Home Assistant's Backup Manager, merged by backup ID across storage agents.

### `backup_manager_actions.list_agents`

Returns the Backup Agents currently registered in Home Assistant. Use this action to discover the exact IDs required by `create` and `delete`.

### `backup_manager_actions.refresh`

Refreshes the integration diagnostics and can return the current Backup Manager snapshot.

## Entities

The integration intentionally avoids duplicating Home Assistant's native Backup sensors. It adds only information useful for advanced automation:

- **Backup agents** — number of registered agents, with IDs, names, domains, and agent errors as attributes.
- **Backups** — number of logical backups visible across all agents.
- **Latest backup** — latest logical backup ID with metadata and storage locations.
- **Backup agents healthy** — on when at least one Backup Agent is registered and the last Backup Manager listing returned no per-agent errors.

## Installation with HACS

Until this repository is included in the default HACS catalog:

1. Open HACS.
2. Add `https://github.com/paolo-hub/home-assistant-backup-manager-actions` as a custom repository with category **Integration**.
3. Install **Backup Manager Actions**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Add **Backup Manager Actions**.

There are no credentials or external settings to configure.

## Updates

HACS tracks this repository through an update entity. Stable versions are published as GitHub Releases and use the release tag as the remote version.

After installing an update, restart Home Assistant so the updated Python integration is loaded.

## Compatibility

- Minimum Home Assistant version: **2026.9.0**
- Stable release line: **1.x**

The integration deliberately keeps all Home Assistant Backup Manager API calls isolated in `adapter.py` so future Home Assistant API changes remain localized.

## Validation

Version 1.0.0 has been validated on Home Assistant 2026.9.4 with real end-to-end tests covering:

- creation on local and network Backup Agents;
- creation on local, network, and Google Drive Backup Agents in the same logical backup;
- read-back and per-agent copy verification;
- explicit multi-agent deletion;
- post-delete verification that no requested copy remains.

The repository CI also runs HACS validation, hassfest, Python compilation, and adapter behavioral tests.

## License

MIT
