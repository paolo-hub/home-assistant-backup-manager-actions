# Changelog

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
