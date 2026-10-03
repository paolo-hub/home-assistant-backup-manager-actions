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

**Backup Manager Actions (BMA)** is a Home Assistant custom integration that
extends the native Backup Manager with automation-oriented actions, normalized
inventory, reliable backup events, diagnostics, and safe custom retention.

BMA does **not** implement a backup engine or storage provider. Home Assistant
still performs backup creation, storage, encryption, restore, and provider
handling. BMA sits above that native layer and adds the control and inspection
capabilities needed for advanced backup workflows.

## Version and compatibility

- **Current version:** `1.1.0`
- **Minimum Home Assistant:** `2026.9.0`

BMA 1.1 completed the planned real-world validation on Home Assistant 2026.9.4.
The validated scope includes multi-agent backup creation, normalized inventory
and classification, backup events and restart deduplication, calendar-based GFS
retention, scoped deletion, device/entity migration, and verified backup-content
reporting.

## What BMA 1.1 adds

BMA 1.1 provides a provider-agnostic control layer over all Backup Agents already
registered in Home Assistant.

It can:

- create a logical backup on one or more selected Backup Agents;
- persist a stable optional `job_id` such as `full` or `partial`;
- correlate the native backup job with the final logical `backup_id`;
- verify that every requested destination actually stored the backup;
- reject creates where Home Assistant reports failed App or folder contents;
- list and normalize the complete backup inventory across providers;
- classify backups by source without relying on fragile backup names;
- expose physical and logical archive size with completeness information;
- emit a single event for each newly created/discovered logical backup;
- calculate calendar-based GFS retention plans without modifying data;
- apply those plans with current-state recalculation and destructive revalidation;
- restrict retention to an explicit Backup Agent scope while preserving copies
  outside that scope;
- expose compact diagnostic entities for dashboards and automations.

Provider credentials remain owned by their Home Assistant integrations. Restore
is deliberately not exposed as an automation action.

## Architecture

BMA is intentionally **stateless with respect to backup policy**.

The integration owns:

- native Backup Manager calls;
- Backup Agent validation;
- BMA metadata;
- normalized inventory and source classification;
- backup-created events;
- retention planning and verified execution;
- diagnostic entities and structured action responses.

The separately planned companion Home Assistant package will own:

- Full and Partial schedules;
- manual job controls;
- persistent GFS policy values;
- selected destinations;
- App selection for Partial backups;
- notifications;
- helper state;
- dashboard/UI configuration.

The companion package is not shipped by this integration. This separation keeps
BMA reusable while allowing a separate package or user automations to define
site-specific behavior.

## Backup classification

Every logical backup returned by the normalized inventory has a `source_type`:

| Source type | Meaning |
| --- | --- |
| `bma` | Created by Backup Manager Actions and marked with BMA metadata |
| `ha_native` | Native Home Assistant backup not carrying a more specific marker |
| `app_update` | Backup created for an App update and identified by Supervisor metadata |
| `unknown` | Conflicting or malformed source metadata |

BMA backups may additionally expose a `job_id`. The planned companion package
uses `full` and `partial` as job identifiers; BMA itself does not assign semantics
to those names.

`unknown` backups remain visible in inventory but are never automatically
selected by retention.

## BMA metadata

BMA-created backups store:

- `backup_manager_actions.managed = true`
- `backup_manager_actions.correlation_id`
- `backup_manager_actions.metadata_version = "1"`
- `backup_manager_actions.job_id` when supplied

A 1.0.x-style create call without `job_id` remains supported.

## Actions

### `backup_manager_actions.create`

Creates one logical backup and requests copies on every selected Backup Agent.

```yaml
action: backup_manager_actions.create
data:
  agent_ids:
    - hassio.local
    - hassio.Backup
  job_id: full
  include_homeassistant: true
  include_database: true
  include_all_addons: true
  include_addons: []
  include_folders: []
  name: "Full backup {{ now().strftime('%Y-%m-%d %H:%M') }}"
response_variable: backup_result
```

The result includes the final logical `backup_id`, native backup job ID,
requested and stored agents, BMA classification, `job_id`, metadata version,
per-agent sizes, and native encryption flags.

Since beta2, it also reports the verified archive contents:
`homeassistant_included`, `database_included`, `addons` (objects with `slug`,
`name`, `version`), and `folders`. These come from the completed backup inventory,
not from the request. `failed_addons` and `failed_folders` are empty on success;
content failures still raise an error.

On Home Assistant OS/Supervised, including Home Assistant also includes `ssl`
automatically, even with `include_folders: []`. The **Additional folders** selector
adds other folders. SSL remains selectable for a folders-only backup with
`include_homeassistant: false`. BMA preserves this native behavior.

The create action succeeds only after the requested copies and BMA metadata have
been verified. If Home Assistant reports failed App or folder content, BMA
returns an error even when archive copies are physically present.

### `backup_manager_actions.plan_retention`

Calculates retention from the current inventory without deleting anything.

```yaml
action: backup_manager_actions.plan_retention
data:
  source_type: bma
  job_id: full
  agent_ids:
    - hassio.local
    - hassio.Backup
  keep_last: 3
  daily: 7
  weekly: 4
  monthly: 12
  yearly: 3
response_variable: retention_plan
```

The response contains the resolved scope, policy, keep/delete decisions,
retention reasons, skipped items, counts, and potentially reclaimable space.

### `backup_manager_actions.apply_retention`

Applies the same policy schema as `plan_retention`, but does **not** execute a
cached dry-run plan.

```yaml
action: backup_manager_actions.apply_retention
data:
  source_type: bma
  job_id: full
  agent_ids:
    - hassio.local
    - hassio.Backup
  keep_last: 3
  daily: 7
  weekly: 4
  monthly: 12
  yearly: 3
response_variable: retention_result
```

For every invocation BMA:

1. resolves and freezes the Backup Agent scope;
2. reads current inventory and fails closed on scoped provider errors;
3. calculates the current retention plan;
4. freezes the policy evaluation timestamp;
5. recalculates policy before each destructive candidate;
6. re-reads and revalidates the candidate at the delete boundary;
7. deletes only in-scope copies;
8. verifies the requested copies are gone.

A copy on an agent outside an explicit scope is preserved.

### App Update retention

App Update backups can be evaluated globally or independently per App.

```yaml
action: backup_manager_actions.plan_retention
data:
  source_type: app_update
  group_by: app
  keep_last: 2
  daily: 7
  weekly: 4
  monthly: 12
  yearly: 3
```

With `group_by: app`, every App slug receives its own independent GFS
calculation.

### `backup_manager_actions.delete`

Deletes one logical backup globally or only from explicit Backup Agents, then
verifies the result.

```yaml
action: backup_manager_actions.delete
data:
  backup_id: "abc12345"
  agent_ids:
    - hassio.local
    - hassio.Backup
response_variable: delete_result
```

Deletion is idempotent when the requested target state is already satisfied.

### Inventory and diagnostics actions

The following 1.0.x actions remain available and backward compatible:

- `backup_manager_actions.refresh`
- `backup_manager_actions.list_agents`
- `backup_manager_actions.list_backups`
- `backup_manager_actions.get_backup`

`list_backups` and `get_backup` now add normalized source/job/App
classification and physical/logical size information.

All BMA actions are registered as **admin-only** services.

## GFS retention semantics

Retention is calculated in the Home Assistant configured timezone and uses
calendar buckets rather than moving-duration windows.

Supported counters:

- `keep_last` — newest N eligible logical backups;
- `daily` — newest backup in each selected local calendar day;
- `weekly` — newest backup in each selected ISO week;
- `monthly` — newest backup in each selected calendar month;
- `yearly` — newest backup in each selected calendar year.

The current calendar period is included. Empty historical buckets are not
backfilled from older periods. A backup kept by multiple rules is retained once
with all applicable reasons.

For BMA retention, an exact `job_id` is required. Legacy BMA backups without a
job ID are therefore visible but excluded from automatic Full/Partial retention.

HA Native manual and automatic backups share the `ha_native` retention class.
App Update backups can use `group_by: app` or `group_by: all`.

## Encryption is not a retention hold

Home Assistant's native `protected` field indicates backup encryption/password
protection. It does **not** mean "do not delete".

BMA therefore applies the same GFS policy to encrypted and unencrypted backups.
The native encryption state remains exposed in inventory and event data, but BMA
1.1 does not implement a separate retention-hold feature.

## Backup-created event

BMA emits:

```text
backup_manager_actions_backup_created
```

For BMA-created backups the event is emitted only after create verification
succeeds.

For externally created HA Native and App Update backups, the first complete
inventory after startup establishes a silent baseline. Historical backups are
not replayed as new. Later new logical backup IDs emit one event each, and a copy
appearing later on another provider does not create a duplicate event.

Typical payload fields include:

- `backup_id`
- `name`
- `date`
- `source_type`
- `job_id`
- `app_slug`
- `agent_ids`
- `size_by_agent`
- `protected_by_agent` (native encryption flags)
- `failed_agent_ids`
- `with_automatic_settings`

## Diagnostic entities

Existing 1.0.x entity identities are preserved.

All eight entities share one **Backup Manager Actions** service device. Existing
unique IDs and registered entity IDs (including user-renamed IDs) are preserved
on upgrade; no dashboard, automation, or history migration is needed.

BMA exposes:

- **Backup agents** — registered Backup Agent count with IDs, names, domains,
  and listing errors;
- **Backups** — total logical backup count, source breakdown, and inventory
  completeness;
- **Latest backup** — latest logical backup ID with normalized metadata and copy
  information;
- **Backup agents healthy** — health summary for registered agents and inventory;
- **BMA backups** — BMA count with `by_job` breakdown;
- **HA Native backups** — native count with informational automatic/manual
  breakdown;
- **App Update backups** — App-update count with per-App breakdown;
- **Backup archive size** — known physical archive size with logical totals,
  completeness flags, per-agent values, per-source values, and provider errors.

When an agent cannot be inventoried, numeric values remain useful for the copies
currently visible, while completeness attributes explicitly mark the data as
partial.

## Safety model

BMA prefers an explicit failure over an uncertain destructive operation.

Important rules include:

- requested Backup Agents are validated before create/delete operations;
- creates verify every requested copy and persisted BMA metadata;
- retention refuses unknown source classification;
- scoped provider inventory errors block retention;
- retention apply operations are serialized inside the loaded adapter;
- apply recalculates from current state rather than trusting an old dry-run;
- classification and backup date are checked again at the final delete boundary;
- agent registration is rechecked around awaited destructive operations;
- independent providers are not treated as transactionally atomic;
- if a later delete fails after earlier candidates succeeded, the error preserves
  the already-deleted IDs;
- restore is intentionally outside the automation API.

## Installation with HACS

Until this repository is included in the default HACS catalog:

1. Open HACS.
2. Add `https://github.com/paolo-hub/home-assistant-backup-manager-actions` as a
   custom repository with category **Integration**.
3. Install **Backup Manager Actions**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration**.
6. Add **Backup Manager Actions**.

There are no BMA credentials or provider settings to configure.

### Release channels and upgrade

HACS should normally follow the latest stable GitHub release. Prerelease builds
may also be available when prerelease versions are explicitly selected.

After a release update, restart Home Assistant. Existing registered entity IDs
are preserved.

### Languages

The integration includes English, Italian, German, French, Spanish, Dutch, and
Brazilian Portuguese (`pt-BR`). Translations cover configuration, entity names,
and action labels/help. Technical API keys and stored entity identities are
unchanged.

## Validation

### Stable 1.0.x

Version 1.0.0 was validated end-to-end on Home Assistant 2026.9.4 with:

- local storage;
- network/SMB storage;
- Google Drive;
- combined multi-agent create;
- read-back and per-agent copy verification;
- explicit multi-agent deletion;
- post-delete verification.

### Beta 1.1.0b1

Before beta publication, the 1.1 implementation passed 112 behavioral simulation
tests covering:

- inventory and classification;
- event tracking and coordinator ordering;
- diagnostic sensors and binary sensor compatibility;
- GFS calendar retention;
- scoped and concurrent retention execution;
- create/delete failure handling;
- service handlers and Voluptuous schemas.

Repository validation also covers Python compilation, hassfest, and HACS
validation.

Beta1 completed real E2E on Home Assistant 2026.9.4 with Local, SMB, Google Drive,
and combined multi-agent operation on 2026-10-02. This covered creation,
metadata, events/discovery/deduplication/startup baseline, diagnostics, GFS plans,
scoped retention deletion, idempotence, and deletion of an encrypted backup.
Provider failure was not induced on the live system; simulated coverage remains.

### Beta 1.1.0b2

Only device grouping, action descriptions, and additional verified create response
fields changed. All 112 beta1 tests plus six beta2 tests pass (118 total).
The focused live E2E completed on 2026-10-03: one device/eight entities, preserved
entity IDs through upgrade and two restarts, folder UI, verified create/readback
contents, native SSL cases, and single success events all passed. Disposable
Local-only backups were cleaned up. See the [beta2 validation record](docs/BETA2_VALIDATION.md).

### Stable 1.1.0

Functional code is unchanged from the validated beta2. The full 118-test
behavioral suite remains the regression baseline. Six additional localization
checks cover all seven locales, structure, nonempty strings, placeholders,
technical terms, and shared retention wording. The final 1.1.0 preparation
passed the complete 124-test suite together with compilation, hassfest, and HACS
validation.

S3-Compatible remains a separate provider issue while native Home Assistant S3
backup creation itself is not reliable in the test environment; it does not
block BMA 1.1 acceptance.

## Documentation

- [BMA 1.1 technical specification](docs/API_1.1_SPEC.md)
- [Independent pre-E2E review](docs/PRE_E2E_REVIEW.md)
- [Changelog](CHANGELOG.md)

## License

MIT
