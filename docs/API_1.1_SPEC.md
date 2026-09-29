# Backup Manager Actions 1.1 Technical Specification

**Status:** Frozen design contract (encryption semantics corrected with Paolo on 2026-09-29)
**Target release:** 1.1.0  
**Branch:** `feature/bma-1.1`  
**Scope:** API contract, classification, inventory, retention, events, and diagnostic entities  
**Compatibility goal:** No breaking changes for existing 1.0.x callers

This document is the normative implementation contract for Backup Manager Actions 1.1. It turns the approved design into a testable technical specification. If implementation details conflict with this document, the implementation must be changed or this specification must be explicitly revised before merge.

## 1. Architectural boundaries

Backup Manager Actions remains an adapter and control layer over Home Assistant's native Backup Manager.

BMA 1.1 must not:

- become a persistent scheduler;
- store job schedules or retention policies;
- own provider credentials;
- implement storage providers or Backup Agents;
- replace Home Assistant restore handling;
- depend on private Supervisor APIs for routine backup inventory or retention.

The companion package remains responsible for:

- Full and Partial job schedules;
- manual job controls;
- persistent user policy;
- selected destinations;
- notifications;
- dashboard/UI state;
- App selection for Partial backups.

BMA is responsible for:

- invoking the native Backup Manager;
- validating Backup Agents;
- writing BMA metadata;
- normalizing/classifying inventory;
- emitting reliable new-backup events;
- planning retention;
- applying retention safely;
- exposing compact diagnostic entities and structured action responses.

## 2. Compatibility requirements

All existing 1.0.x actions remain available:

- `backup_manager_actions.create`
- `backup_manager_actions.delete`
- `backup_manager_actions.refresh`
- `backup_manager_actions.list_agents`
- `backup_manager_actions.list_backups`
- `backup_manager_actions.get_backup`

Existing input fields keep their current meaning.

Existing entity unique IDs must remain unchanged.

A 1.0.x `create` call that does not provide `job_id` must continue to succeed and create a BMA-managed backup.

New 1.1 fields are additive.

All actions remain admin-only.

## 3. Terminology

### Logical backup

A Home Assistant backup identified by one logical `backup_id`, potentially stored on multiple Backup Agents.

### Backup copy

One physical instance of a logical backup on one Backup Agent.

### Source type

Normalized BMA classification of a logical backup:

- `bma`
- `ha_native`
- `app_update`
- `unknown`

### Job ID

Persistent identifier written into BMA-created backup metadata. The companion package initially uses:

- `full`
- `partial`

Manual and scheduled executions of the same job use the same `job_id`.

### Retention scope

The set of logical backups and Backup Agent copies considered by one retention evaluation.

## 4. BMA metadata

BMA-created backups use the following metadata keys:

- `backup_manager_actions.managed`
- `backup_manager_actions.correlation_id`
- `backup_manager_actions.metadata_version`
- `backup_manager_actions.job_id` when supplied

For 1.1:

```text
backup_manager_actions.managed = true
backup_manager_actions.metadata_version = "1"
```

`metadata_version` is stored as a string because Home Assistant Backup Manager extra metadata values are limited to boolean or string values. Normalized BMA API output exposes a valid numeric metadata version as an integer.

`correlation_id` remains a generated UUID-style opaque string used to correlate the native Backup Manager job with the final logical backup.

`job_id` is optional for API compatibility.

When present, `job_id` must:

- be a string;
- be non-empty after trimming;
- use lowercase ASCII letters, digits, underscore, or hyphen;
- start with a lowercase letter or digit;
- be at most 64 characters.

Recommended validation pattern:

```text
^[a-z0-9][a-z0-9_-]{0,63}$
```

BMA 1.1 does **not** persist retention policy values or a retention profile.

## 5. Backup classification

Classification is automatic and configuration-free.

### 5.1 Output fields

Every normalized backup returned by inventory APIs must include:

- `source_type`
- `classification_reason`
- `job_id`
- `app_slug`
- `metadata_version`

Fields not applicable to a backup are `null`.

### 5.2 Classification rules

Classification must be deterministic.

1. Detect the BMA marker:
   - `backup_manager_actions.managed is true`

2. Detect the App Update marker:
   - `supervisor.addon_update` present in `extra_metadata`

3. If both BMA and App Update markers are present:
   - `source_type = unknown`
   - `classification_reason = conflicting_source_markers`

4. If only the BMA marker is present:
   - `source_type = bma`
   - valid `job_id`: `classification_reason = bma_managed` and expose the normalized `job_id`;
   - no `job_id`: `classification_reason = bma_legacy_no_job` and `job_id = null`;
   - invalid `job_id`: `classification_reason = bma_invalid_job_id` and `job_id = null`.
   - a valid decimal-string `metadata_version` is normalized to an integer; a missing or invalid value is exposed as `null`.

5. If only the App Update marker is present:
   - if the marker contains a valid non-empty App slug:
     - `source_type = app_update`
     - `classification_reason = app_update_metadata`
     - `app_slug = <slug>`
   - otherwise:
     - `source_type = unknown`
     - `classification_reason = invalid_app_update_metadata`

6. Otherwise:
   - `source_type = ha_native`
   - `classification_reason = ha_native_default`

`with_automatic_settings` remains exposed as native metadata but does not create another top-level source class.

Manual and automatic Home Assistant backups therefore remain grouped under `ha_native`.

### 5.3 Unknown backups

`unknown` backups are visible in inventory but must never be automatically selected by retention.

Retention actions do not accept `source_type: unknown`.

## 6. Extended create action

Action:

```text
backup_manager_actions.create
```

### 6.1 Inputs

Existing fields remain unchanged:

- `agent_ids` — required, non-empty unique list
- `include_homeassistant` — default `true`
- `include_database` — default `true`
- `include_all_addons` — default `false`
- `include_addons` — optional unique list
- `include_folders` — optional list of supported native Backup Manager folders
- `name` — optional
- `password` — optional

New field:

- `job_id` — optional, validated as defined in section 4

### 6.2 Metadata written

Every BMA-created backup writes:

```text
backup_manager_actions.managed = true
backup_manager_actions.correlation_id = <generated>
backup_manager_actions.metadata_version = "1"
```

If `job_id` is supplied:

```text
backup_manager_actions.job_id = <job_id>
```

### 6.3 Response

The existing response fields remain and the response is extended with:

- `source_type` = `bma`
- `job_id`
- `metadata_version`

Expected shape:

```yaml
backup_id: abc123
backup_job_id: job456
name: Backup name
date: "..."
source_type: bma
job_id: full
metadata_version: 1
failed_agent_ids: []
with_automatic_settings: false
requested_agent_ids:
  - hassio.local
stored_agent_ids:
  - hassio.local
protected_by_agent:
  hassio.local: false
size_by_agent:
  hassio.local: 123456789
```

A create must raise an explicit error if Home Assistant reports failed App or
folder contents, even when every requested agent has a copy. Such an operation
must not emit a verified BMA success event or allow an ordinary sequential
create-then-retention automation to continue as though creation succeeded.

### 6.4 Manual and scheduled jobs

BMA itself does not distinguish manual versus scheduled execution.

The companion package must use the same `job_id`, contents, destinations, and retention policy for both.

The intended package flow is:

```text
create(job_id=<job>)
    -> successful verified backup
    -> apply_retention(source_type=bma, job_id=<job>, ...)
```

Create and retention remain separate actions.

## 7. Normalized inventory

### 7.1 list_backups

`backup_manager_actions.list_backups` keeps the existing response structure and adds normalized classification fields to every backup.

Each backup keeps all existing native fields and adds:

- `source_type`
- `classification_reason`
- `job_id`
- `app_slug`
- `metadata_version`
- `physical_size_bytes`
- `physical_size_complete`
- `logical_size_bytes`
- `logical_size_complete`

### 7.2 get_backup

`backup_manager_actions.get_backup` returns the same normalized backup object used by `list_backups`.

### 7.3 Size semantics per logical backup

For one logical backup:

- `physical_size_bytes` = sum of known sizes of all copies;
- `physical_size_complete = true` only if every visible copy reports a size;
- `logical_size_bytes` = maximum known copy size;
- `logical_size_complete = true` if at least one copy reports a size.

The logical size intentionally counts the logical backup once.

If no copy reports a size:

- `logical_size_bytes = null`
- `logical_size_complete = false`

## 8. Retention actions

New actions:

- `backup_manager_actions.plan_retention`
- `backup_manager_actions.apply_retention`

Both use the same policy input schema.

### 8.1 Common inputs

Required:

- `source_type`

Allowed values:

- `bma`
- `ha_native`
- `app_update`

Optional/conditional:

- `job_id`
- `group_by`
- `agent_ids`

Policy counters:

- `keep_last`
- `daily`
- `weekly`
- `monthly`
- `yearly`

All counters are integers >= 0.

At least one retention counter must be > 0.

Default for counters not provided:

```text
0
```

### 8.2 source_type validation

#### source_type = bma

`job_id` is required.

The retention action only considers BMA backups with exactly that `job_id`.

Legacy BMA backups with `job_id = null` are intentionally excluded from automatic Full/Partial retention.

#### source_type = ha_native

`job_id` is not accepted.

`group_by` is not accepted.

Manual and automatic HA backups are treated together.

#### source_type = app_update

`job_id` is not accepted.

`group_by` is allowed:

- `app`
- `all`

Default:

```text
group_by: app
```

### 8.3 Agent scope

`agent_ids` is optional.

If supplied:

- it must be a non-empty unique list;
- every requested agent must currently be registered;
- only copies on those agents are in scope;
- inventory errors from any scoped agent abort the retention action before deletion.

If omitted:

- scope is all currently registered Backup Agents;
- inventory errors from any registered agent abort the retention action before deletion.

A logical backup is considered in scope only when it has at least one visible copy on a scoped agent.

A logical backup does not need to exist on every scoped agent.

## 9. GFS calendar semantics

Retention uses Home Assistant's configured timezone.

All GFS buckets are calendar buckets, not moving duration windows.

### 9.1 keep_last

`keep_last: N` keeps the N newest eligible logical backups (encrypted or unencrypted) in the retention group.

### 9.2 daily

`daily: N` evaluates:

- the current local calendar day;
- the previous N-1 calendar days.

For each non-empty day bucket, keep the newest eligible backup in that bucket.

### 9.3 weekly

`weekly: N` evaluates:

- the current ISO week;
- the previous N-1 ISO weeks.

Weeks are Monday through Sunday.

For each non-empty week bucket, keep the newest eligible backup in that bucket.

### 9.4 monthly

`monthly: N` evaluates:

- the current calendar month;
- the previous N-1 calendar months.

For each non-empty month bucket, keep the newest eligible backup in that bucket.

### 9.5 yearly

`yearly: N` evaluates:

- the current calendar year;
- the previous N-1 calendar years.

For each non-empty year bucket, keep the newest eligible backup in that bucket.

### 9.6 No backfill

Empty calendar buckets are not compensated by searching further into the past.

Example:

`daily: 7` means the seven calendar-day buckets ending today, not "the latest seven days that contain backups".

### 9.7 Union and deduplication

The final keep set is the union of:

- `keep_last`
- daily buckets
- weekly buckets
- monthly buckets
- yearly buckets

The same logical backup may satisfy multiple rules and appears only once in the keep set.

The plan must record every keep reason that applies.

### 9.8 Deterministic ordering and tie-breaker

Backups are ordered by:

1. backup date descending;
2. `backup_id` descending lexicographically when dates are equal.

This ordering is used consistently for `keep_last` and bucket selection.
Compare UTC instants, including within the repeated fall-back hour. Local time
is used only to assign calendar buckets. Planning must scale with inventory,
not allocate one object per requested calendar period.

## 10. Encryption is not retention protection

**Design correction approved by Paolo on 2026-09-29:** native Home Assistant
`AgentBackupStatus.protected` means that the archive is encrypted with a password.
It is not an immutable flag, a retention hold, or a prohibition on deletion.

Encrypted and unencrypted copies participate in the same keep-last/GFS policy.
Encryption neither exempts a logical backup from deletion nor gives it an
additional quota. Native `protected` and `protected_by_agent` fields retain their
original encryption meaning in inventory, create responses, and events.

BMA 1.1 does not implement retention holds. For compatibility with the development
plan response shape, `protected` is always `[]` and `summary.protected` is always
`0`. These fields must not be populated from native encryption flags.

This correction supersedes the earlier specification's encrypted-copy exclusion.

## 11. App Update grouping

For:

```text
source_type = app_update
group_by = app
```

the complete policy is evaluated independently for each `app_slug`.

Example:

```yaml
source_type: app_update
group_by: app
keep_last: 2
daily: 7
weekly: 4
monthly: 12
yearly: 3
```

means each App receives its own independent keep-last and GFS calculation.

For:

```text
group_by = all
```

all App Update backups compete in one common retention group.

## 12. plan_retention

`plan_retention` is read-only and must not mutate backup state.

Before planning, BMA resolves the active agent scope and reads current Backup Manager inventory. Any inventory error from an in-scope agent aborts planning. Errors from agents outside an explicitly supplied scope do not block that scope.

When `agent_ids` is omitted, all currently registered Backup Agents form the scope and an error from any registered agent aborts planning.

It returns a complete structured plan.

Suggested normative response shape:

```yaml
evaluated_at: "2026-09-29T12:00:00+02:00"
timezone: Europe/Rome

scope:
  source_type: bma
  job_id: full
  group_by: null
  agent_ids:
    - hassio.local
    - hassio.Backup

policy:
  keep_last: 3
  daily: 7
  weekly: 4
  monthly: 12
  yearly: 3

summary:
  considered: 17
  protected: 0
  keep: 12
  delete: 5
  out_of_scope: 0
  reclaimable_size_bytes: 1234567890
  reclaimable_size_complete: true

keep:
  - backup_id: abc
    group: full
    reasons:
      - keep_last
      - daily:2026-09-29

protected: []

delete:
  - backup_id: ghi
    group: full
    target_agent_ids:
      - hassio.local
      - hassio.Backup
    reclaimable_size_bytes: 123456
    reclaimable_size_complete: true

skipped: []
```

### 12.1 Reclaimable size

For one delete candidate:

`reclaimable_size_bytes` is the sum of known sizes of copies that would be deleted inside the active agent scope.

`reclaimable_size_complete` is true only when every target copy reports a size.

The plan-level reclaimable size is the sum of known candidate values and is complete only when every delete candidate is complete.

Delete candidates are returned in deterministic oldest-first order using parsed timezone-aware timestamps, not lexical ISO timestamp text.

## 13. apply_retention

`apply_retention` must never execute a previously cached plan.

Execution sequence:

1. resolve and freeze agent scope for this invocation;
2. validate every scoped agent;
3. read current inventory;
4. abort if scoped inventory has errors;
5. recalculate the retention plan from current state;
6. freeze the policy evaluation timestamp for the complete apply operation;
7. before every destructive candidate, recalculate the complete policy against current inventory using that frozen timestamp;
8. delete the candidate only if it is still eligible in the recalculated plan;
9. verify each deletion;
10. return structured execution results.

`apply_retention` operations are serialized within the loaded BMA adapter so two concurrent retention applies cannot execute deletion loops at the same time.

The per-candidate policy recalculation is a fail-closed hardening rule. If concurrent changes promote a previously planned candidate into `keep_last` or a GFS keep bucket, the operation aborts before deleting that candidate. The frozen evaluation timestamp ensures that a long apply operation cannot change calendar buckets merely because execution crosses a clock or calendar boundary.

This guarantees that a newly created backup appearing between an earlier dry-run and apply cannot be deleted due to a stale plan and that policy drift during a multi-delete apply cannot silently invalidate later candidates.

### 13.1 Preflight safety

No deletion may begin if:

- any scoped agent is unavailable;
- any scoped agent reports an inventory error;
- classification required by the requested policy is invalid;
- policy validation fails.

### 13.2 Deletion execution

Delete candidates are processed deterministically in oldest-first order.

For each logical backup:

- recalculate the complete current retention plan before the candidate;
- re-read the logical backup immediately before deletion;
- abort if the candidate is no longer eligible under the current policy;
- abort if its retention classification no longer matches the current plan;
- abort if the candidate date changed since policy evaluation;
- repeat classification/date/scope checks on the final delete pre-read;
- include a copy that appeared on another in-scope agent after planning;
- delete only in-scope copies;
- verify target copies are gone;
- preserve any copies outside the scope.

Agent registration is checked again after awaited inventory reads and after deletion.
An unregistered target cannot be treated as verified absent. A provider registered
after the initial plan is outside this invocation's frozen scope. Copies added to
an already scoped provider remain in scope.

If the target backup or all in-scope target copies were already removed by another actor, deletion remains idempotent and is reported as already absent rather than treated as a destructive failure. A logical backup may still remain on out-of-scope agents in this case.

If a deletion fails after earlier deletions have already succeeded, BMA must raise `BackupManagerActionsError` with the failing backup and agent context.

Multi-backup deletion is not transactional across independent providers. If a later candidate fails after earlier candidates were deleted successfully, BMA raises `BackupManagerActionsError` including the failing backup and the IDs already deleted before the failure.

### 13.3 Success response

On full success:

```yaml
plan:
  # same structure as plan_retention

execution:
  deleted:
    - backup_id: ghi
      target_agent_ids:
        - hassio.local
        - hassio.Backup
      previous_agent_ids:
        - hassio.local
        - hassio.Backup
      remaining_agent_ids: []
      target_copies_found_before_delete: true
  deleted_count: 5
  already_absent_count: 0
```

## 14. New-backup event

Event type:

```text
backup_manager_actions_backup_created
```

### 14.1 BMA-created backups

For backups created through `backup_manager_actions.create`:

- emit the event only after create verification has succeeded on every requested destination and BMA metadata verification has succeeded;
- when a coordinator is loaded, await an immediate refresh (not just a debounced request) before publishing the verified BMA event; a refresh failure does not undo a verified backup;
- a Backup Manager refresh may observe the logical backup before create verification finishes, but discovery alone must not emit a BMA-created event;
- emit exactly once for the logical backup.

### 14.2 Externally created backups

For `ha_native` and `app_update` backups:

- the coordinator compares only complete inventory snapshots (`inventory_complete = true`);
- incomplete snapshots do not establish or advance the event baseline;
- the first complete snapshot after startup establishes the baseline;
- historical backups in the baseline do not emit events;
- a new logical `backup_id` seen later in a complete snapshot emits one event;
- discovery-driven events are deferred with non-eager task scheduling until the coordinator has committed the refreshed snapshot and updated entity listeners;
- if multiple new logical backups are discovered together, events are emitted deterministically by ascending real timestamp and then `backup_id`; ISO offsets are parsed and must not be compared lexically;
- a later additional copy of the same logical backup on another agent does not emit another backup-created event;
- discovered `bma` and `unknown` backups do not use this external-discovery event path.

### 14.3 Event payload

```yaml
backup_id: abc123
name: Backup name
date: "..."
source_type: bma
job_id: full
app_slug: null
agent_ids:
  - hassio.local
size_by_agent:
  hassio.local: 123456789
protected_by_agent:
  hassio.local: false
failed_agent_ids: []
with_automatic_settings: false
```

Fields that do not apply are `null` or empty lists/maps as appropriate.

No `backup_updated` event is introduced in 1.1.

Event deduplication is by logical `backup_id` for the lifetime of the loaded integration. Deleted and later re-observed logical IDs do not generate a second event during the same runtime.

## 15. Diagnostic entities

Existing entities and unique IDs remain unchanged.

### 15.1 Existing entities

Keep:

- Backup agents count
- Backups logical count
- Latest backup
- Backup agents healthy

### 15.2 New count sensors

Add:

- BMA backups count
- HA Native backups count
- App Update backups count

The total logical backup count remains the existing Backups sensor.

The existing total Backups sensor keeps its unique ID and state semantics and adds:

- `inventory_complete`
- `source_counts`, including the `unknown` class

Breakdowns use attributes rather than creating one entity per job/App/agent.

Every new class-count sensor also exposes `inventory_complete` so a partial multi-agent inventory is explicit.

### 15.3 Count sensor attributes

BMA count exposes:

```yaml
inventory_complete: true
by_job:
  full: 10
  partial: 24
  unassigned: 2
```

App Update count exposes:

```yaml
inventory_complete: true
by_app:
  core_mosquitto: 3
  other_slug: 2
```

HA Native exposes:

```yaml
inventory_complete: true
automatic: 2
manual_or_other: 4
```

The automatic/manual split is informational only and does not change the top-level source class.

## 16. Latest Backup sensor

The existing unique ID is preserved.

Its state remains the latest logical `backup_id`. "Latest" is determined from the real timezone-aware timestamp, not lexical ISO date text, so different UTC offsets cannot invert chronology.

Attributes are extended with normalized fields:

- `source_type`
- `classification_reason`
- `job_id`
- `app_slug`
- `metadata_version`
- normalized size fields
- existing native backup metadata
- agent copy data

## 17. Archive size sensor

Add one aggregate numeric sensor whose native value is:

```text
physical_total_bytes
```

Recommended sensor semantics:

- device class: data size
- native unit: bytes
- state class: measurement

### 17.1 Aggregate attributes

Expose at minimum:

```yaml
physical_total_bytes: 12000000000
physical_size_complete: true
logical_size_bytes: 4300000000
logical_size_complete: true

per_agent:
  hassio.local:
    name: local
    domain: hassio
    backup_count: 18
    size_bytes: 4000000000
    size_complete: true

  hassio.Backup:
    name: Backup
    domain: hassio
    backup_count: 18
    size_bytes: 5000000000
    size_complete: true

per_source_type:
  bma:
    backup_count: 20
    physical_size_bytes: 7000000000
    logical_size_bytes: 2600000000

  ha_native:
    backup_count: 4
    physical_size_bytes: 3000000000
    logical_size_bytes: 1100000000

  app_update:
    backup_count: 8
    physical_size_bytes: 2000000000
    logical_size_bytes: 600000000
```

`unknown` may also appear in `per_source_type` when present.

### 17.2 Dashboard use

The aggregate state provides the overall physical archive size.

Per-agent values are deliberately exposed as nested attributes so the package/dashboard can derive or graph each destination separately without creating one BMA entity per discovered agent.

The Archive Size sensor also exposes:

- `inventory_complete`
- `agent_errors`

The numeric state remains the sum of currently known physical copy sizes even when an agent is unavailable; completeness attributes must then be false so that partial data is never presented as complete.

Dedicated per-agent sensors are not part of the 1.1 contract.

## 18. Snapshot / refresh response

The internal normalized snapshot and the optional response of `backup_manager_actions.refresh` are extended to include:

- existing manager state;
- agents;
- agent errors;
- `inventory_complete`, true only when the snapshot has no per-agent inventory errors;
- total backup count;
- latest normalized backup;
- `source_counts` keyed by `bma`, `ha_native`, `app_update`, and `unknown`;
- `bma_by_job` with an `unassigned` bucket;
- `app_update_by_app`;
- `ha_native_breakdown` with `automatic` and `manual_or_other`;
- `archive_size` with physical/logical totals, completeness flags, per-agent breakdown, and per-source breakdown.

A snapshot with agent errors must preserve those errors explicitly, set `inventory_complete = false`, and mark aggregate size completeness false rather than silently presenting partial provider data as complete.

Mutation service handlers refresh diagnostics in `finally`, including after
partial create/delete/apply failures. The original action failure is preserved;
refreshing diagnostics does not convert failure into success.

## 19. Error model

BMA continues to use `BackupManagerActionsError` for operational failures.

Errors must be explicit and contain useful context.

Examples:

- unavailable requested agent;
- invalid job_id;
- contradictory create content selection;
- scoped inventory failure;
- invalid retention policy;
- unsupported source/group combination;
- deletion verification failure.

Retention must prefer no deletion over uncertain deletion.

Unknown classification must never be silently mapped into a deletable class.

## 20. Test contract

At minimum, automated tests must cover:

### Classification

- BMA 1.1 with job_id;
- legacy BMA without job_id;
- HA native manual;
- HA native automatic;
- valid App Update;
- malformed App Update metadata;
- conflicting BMA/App markers.

### Create

- backward-compatible create without job_id;
- create with full;
- create with partial;
- invalid job_id;
- metadata persistence;
- correlation and multi-agent verification.

### Retention calendar logic

- keep_last;
- daily buckets;
- ISO weekly buckets across year boundary;
- monthly buckets across year boundary;
- yearly buckets;
- current partial period;
- no backfill;
- union/dedup reasons;
- equal-date tie-break;
- encrypted backups count towards normal keep-last/GFS quota;
- App grouping per App;
- App grouping all;
- BMA job filtering;
- legacy BMA without job_id excluded;
- HA Native mixed manual/automatic.

### Agent scope and safety

- explicit agent_ids;
- omitted agent_ids = all registered;
- unknown requested agent;
- scoped agent listing error;
- backup present only on subset of scoped agents;
- out-of-scope copies preserved;
- encrypted copy in scope remains eligible for retention;
- provider registration changes during listing and deletion;
- classification/date changes on the final pre-delete read;
- target copies disappearing after planning while out-of-scope copies remain;
- policy drift between destructive candidates;
- delete verification failure.

### Event

- no startup replay;
- external new backup emits once;
- new copy on second agent does not duplicate;
- BMA create emits only after successful verification.

### Size aggregation

- physical sum;
- logical maximum-per-backup;
- missing copy size;
- per-agent totals;
- per-source totals.

### Diagnostic entities

- existing 1.0.x sensor unique IDs unchanged;
- total logical backup sensor keeps its state and exposes source breakdown;
- BMA count and by-job attributes;
- HA Native count and automatic/manual informational attributes;
- App Update count and per-App attributes;
- Latest Backup keeps backup_id as state and exposes normalized metadata;
- Archive Size uses bytes/data-size/measurement semantics;
- Archive Size exposes per-agent and per-source attributes;
- incomplete inventory remains numerically observable but explicitly marked incomplete.

## 21. Implementation sequence

Implementation should proceed in these blocks:

1. constants and normalized classification helpers;
2. normalized backup serializer and inventory aggregation;
3. create metadata/job_id extension;
4. event baseline and emission;
5. new count/archive sensors;
6. pure calendar retention planner;
7. apply-retention executor and verification;
8. service schemas and `services.yaml`;
9. translations/icons where required;
10. automated tests;
11. README/CHANGELOG updates and pending absolute LICENSE badge fix;
12. end-to-end testing on Home Assistant with Local, SMB, and Google Drive.

S3-Compatible remains a separate provider incident and must not block BMA 1.1 while native S3 backup creation itself still fails.

## 22. Acceptance criteria

BMA 1.1 is ready for release only when:

- all 1.0.x actions remain functional;
- existing entity unique IDs are preserved;
- Full and Partial manual/scheduled backups classify identically by job_id;
- source classification is deterministic;
- unknown backups are never automatically deleted;
- retention uses calendar buckets exactly as specified;
- plan and apply agree when state is unchanged;
- apply recalculates when state changes;
- per-App retention never mixes App slugs;
- scoped agent errors block deletion;
- encrypted backups obey the same retention policy as unencrypted backups;
- external new-backup events do not replay at startup or duplicate on additional copies;
- archive totals expose completeness and per-agent breakdowns;
- Local, SMB, and Google Drive end-to-end tests pass.
