# BMA 1.1 independent pre-E2E review — 2026-09-29

Historical review at the pre-beta baseline. Subsequent extended beta1 E2E passed
on 2026-10-02 and focused beta2 E2E passed on 2026-10-03. See
[BETA2_VALIDATION.md](BETA2_VALIDATION.md) and the README for current acceptance
status. Provider failure was not induced live; simulated coverage remains.

Reviewed baseline: `a8db47074a96f048e4fb30e8da820a58f12019d0` on
`feature/bma-1.1`. Review covered all integration modules, service declarations,
translations, specification, existing simulations, and the relevant native HA
2026.9.4 source contracts. This report accompanies the corrective commit.

## Findings and corrections

| Area | Finding | Correction |
| --- | --- | --- |
| Encryption semantics | Native `protected` means encryption. The earlier specification and tests incorrectly made encrypted archives immune to retention. | Paolo explicitly selected normal retention for encrypted backups on 2026-09-29. Encrypted and plain copies now share quota and expiry; specification and translations corrected. `protected: []` and `summary.protected: 0` remain in plan output for development-shape compatibility. No retention-hold capability is implied. |
| Repeated DST hour | Comparing datetimes converted to the same `ZoneInfo` can compare wall time, ignoring the repeated-hour fold. The newer real backup could be deleted. | UTC ordering for keep-last, bucket representatives and delete order; local dates remain the basis of calendar buckets. |
| Calendar resource use | Accepted large daily/weekly/monthly/yearly values allocated one bucket per period, with overflow or excessive CPU/memory use. | Compare calendar ages only for inventory entries; memory and iteration do not grow with policy counters. |
| Final delete boundary | The extra read inside `async_delete` could observe changed classification/date after retention validation without checking it. | Reapply scope/classification/date checks to the final read; include newly observed in-scope copies and skip already-absent target copies. |
| Provider scope | Omitted scope could expand on a later replan, and a removed provider could be mistaken for verified absence. | Freeze resolved agent IDs per apply; validate registration after awaited reads and deletion. |
| Create result | Copies could be present while native HA reported failed App/folder contents. | Raise an explicit incomplete-content error; no verified BMA event or normal sequential continuation to retention. |
| Event ordering | HA starts tasks eagerly by default. A supposedly deferred discovery event could fire before entity listeners ran. | Explicit `eager_start=False`; coordinator stub now models HA's eager default. |
| Service refresh | `async_request_refresh` can just queue a refresh. Failed mutations also bypassed diagnostic refresh. | Await `async_refresh`; mutation handlers refresh in `finally` while preserving action failures. |
| Public input | HA's string coercion could turn numeric job IDs into accepted strings. | Validate the original job-ID value against the string-only contract. |
| Failure reporting | Native HA exceptions during a multi-delete apply could escape without prior-deletion context. | Wrap native Home Assistant errors with the failed candidate and already deleted IDs. |

The original protection-race checks were reviewed before discovering the native
field's encryption meaning. The final code intentionally does **not** treat a
change in native encryption status as a retention veto.

## Verification

All 112 behavioral test functions pass locally, each module executed in a separate
process using its declared main runner. Python compilation and JSON validation
also pass. Local Python is 3.12; CI runs the same suite on Python 3.13.

| Suite | Test functions |
| --- | ---: |
| Inventory | 6 |
| Event tracker | 9 |
| Coordinator | 7 |
| Sensors | 8 |
| Binary sensor | 4 |
| Retention planner | 21 |
| Adapter/executor | 52 |
| Service handlers/schemas | 5 |
| **Total** | **112** |

Regressions were also run against the unmodified baseline to confirm that they
expose the old defects: repeated-hour ordering, oversized calendar windows,
encryption exclusion, final-read classification/date changes, agent disappearance,
scope expansion, partial content failures, eager event scheduling, deferred service
refresh, numeric job IDs, and lost partial-progress error context.

Service tests use the real Voluptuous schema engine (0.16.0). Home Assistant,
provider I/O and authorization enforcement are stubbed; these tests do not claim
full native HA integration coverage. CI now explicitly installs the schema test
dependency and runs the service suite.

## Native sources checked

- [Backup Manager 2026.9.4](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/backup/manager.py): create completion, partial content reports, encryption during upload, list/get aggregation, delete behavior.
- [HA core 2026.9.4](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/core.py): eager task default.
- [DataUpdateCoordinator 2026.9.4](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/update_coordinator.py): refresh locking/debounce and listener ordering.

## Original real E2E checklist (historical)

1. Load this development branch on HA and check startup, reload, entity identities,
   action schemas, and no replay of historical external backups.
2. Test Local, then SMB, then Google Drive, then a combined multi-agent create.
   Verify native metadata persistence, one logical ID, copy visibility, sizes,
   classification, and event/sensor ordering.
3. Use a unique test `job_id` such as `bma_e2e_20260929` and explicit agent IDs for
   disposable BMA backups. Compare plan/apply and repeat an already satisfied apply.
4. Explicitly include encrypted backups: they must now consume quota and be
   removed when expired. Verify non-target copies survive scoped deletion.
5. Observe real provider failure/recovery and partial errors. Do not treat
   simulations as evidence of cloud timing or network behavior.
6. Native/App Update destructive tests require an isolated test destination or a
   fully inspected inventory: those classes cannot be isolated by BMA `job_id`.
7. Coordinate native HA and Supervisor retention with the package before routine
   operation; another retention owner may remove backups independently of BMA.

BMA cannot make independent providers transactional, and the native APIs do not
provide atomic compare-and-delete. Checks narrow concurrency windows but cannot
exclude every external mutation after the last read. A failed create may leave
usable partial archives visible in inventory; it must not be reported as success.

No real-provider E2E, restore test, release, merge, or production deletion was
performed during this historical review. The beta live E2E gates were subsequently
completed as recorded above; the PR remains Draft for manual stable finalization.
