# Changelog

## 1.1.0b1 — 2026-09-30

First public beta of the 1.1 line. This build is intended for controlled end-to-end
validation on Home Assistant before the final 1.1.0 release. The 1.0.1 release
remains the stable production version.

### Added

- Normalized backup classification: `bma`, `ha_native`, `app_update`, and
  `unknown`.
- Persistent optional `job_id` metadata for BMA-created backups, preserving
  compatibility with 1.0.x callers.
- Normalized inventory fields for source, job/App classification, metadata
  version, physical size, logical size, and completeness.
- `backup_manager_actions_backup_created` event for verified BMA creates and
  newly discovered HA Native/App Update logical backups.
- New diagnostic sensors for BMA, HA Native, and App Update backup counts.
- Archive-size sensor with physical/logical totals, per-agent and per-source
  breakdowns, and explicit completeness state.
- `plan_retention` action for read-only calendar-based GFS planning.
- `apply_retention` action for verified, fail-closed GFS execution with
  optional explicit Backup Agent scope.
- Per-App retention grouping for App Update backups.

### Retention and safety

- GFS supports `keep_last`, daily, ISO-weekly, monthly, and yearly calendar
  buckets in the Home Assistant timezone.
- Retention policies remain stateless inside BMA: the companion package owns
  schedules, policy values, destinations, notifications, and UI state.
- `apply_retention` recalculates policy from current inventory and revalidates
  before every destructive candidate.
- Agent scope is frozen for each apply invocation; copies outside an explicit
  scope are preserved.
- Unknown or ambiguously classified backups are never selected automatically
  for retention.
- Native Home Assistant `protected` means encryption/password protection, not
  retention hold. Encrypted backups participate in the same GFS policy as
  unencrypted backups.
- Partial create results reported by Home Assistant through failed App/folder
  content are rejected as unsuccessful.
- Mutation actions refresh diagnostics even on failure while preserving the
  original operational error.

### Hardening

- Fixed real-time ordering across differing UTC offsets and the repeated DST
  hour.
- Prevented oversized calendar counters from causing work proportional to the
  requested window.
- Revalidated classification, date, and registered agents at the final delete
  boundary.
- Prevented newly registered providers from expanding destructive scope during
  an active retention apply.
- Fixed event ordering under Home Assistant's eager task scheduling.
- Enforced string-only `job_id` input and preserved partial-delete progress in
  error reporting.

### Validation status

- 112 behavioral simulation tests pass across inventory, event tracking,
  coordinator behavior, sensors, binary sensor, retention planning,
  adapter/executor, and service schema/handler coverage.
- Python compilation, hassfest, and HACS validation passed on the pre-beta
  implementation.
- Real 1.1 E2E validation with Local, SMB, Google Drive, combined multi-agent
  creation, metadata/event ordering, and retention execution is still pending
  and is the acceptance gate for 1.1.0.

## 1.0.1

### Fixed

- Fixed license badge rendering in HACS by replacing the dynamic GitHub license shield with a static MIT badge.

## 1.0.0

First stable release.

### Added

- Provider-agnostic actions over Home Assistant's native Backup Manager.
- Multi-agent backup creation with explicit destination selection.
- Reliable correlation between Supervisor job IDs and final logical backup IDs.
- Verification that every requested destination stored the created backup.
- Logical backup and Backup Agent inspection actions.
- Fail-closed explicit multi-agent deletion with post-delete verification.
- Diagnostic entities for Backup Agents, logical backups, latest backup, and agent health.
- HACS packaging, local brand assets, Italian and English translations.

### Validated

End-to-end testing on Home Assistant 2026.9.4 with:

- local backup storage;
- network/SMB backup storage;
- Google Drive as a cloud Backup Agent;
- multi-agent create, read-back, delete, and post-delete verification.
