# Changelog

## 1.1.0 — Unreleased

- Add normalized source/job inventory, create metadata, new-backup events, and diagnostic sensors.
- Add calendar GFS planning and verified execution with explicit agent scope.
- Correct native `protected` semantics: encryption does not exclude backups from retention (approved 2026-09-29).
- Fix repeated-hour chronology, eager event scheduling, and service refresh ordering.
- Revalidate classification/date and registered agents at the final destructive boundary; freeze apply scope.
- Reject reported partial backup contents; refresh diagnostics after failed mutations.
- Bound calendar planning by inventory size and enforce string job IDs.
- Extend behavioral simulations to include service handlers and schemas. Real 1.1 E2E validation is pending.

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
