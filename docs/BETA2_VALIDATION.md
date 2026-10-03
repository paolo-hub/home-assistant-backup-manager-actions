# Beta2 scope and validation

Baseline: tag `1.1.0b1`, commit `46f98afb17683fbf2941f45b78d736e25b749d75`.
Beta1's real HA 2026.9.4 E2E completed on 2026-10-02; detailed evidence is in the
project Evernote diary. Published beta2: `1.1.0b2` at
`53dca63e9facb5e594ebb2f991434a30b124d3f5`. Its focused live E2E completed PASS on
2026-10-03, including Local-only cleanup.

## Design and regression boundary

- Sensors and binary sensor only gain `DeviceInfo`, sharing `(DOMAIN, entry_id)`
  and `DeviceEntryType.SERVICE`. Native entity-platform registration updates the
  association on existing unique IDs. No registry rewrite, entity rename, new
  entity, entity category change, or new polling is introduced.
- The action UI only gets EN/IT descriptions. Home Assistant's service control
  updates the selected field and supports static defaults, not conditional
  cross-field selection. `services.yaml` and backend schemas remain unchanged;
  SSL remains in the selectable options. The explanation appears on both fields.
- The only adapter change adds six fields to the successful create return value,
  sourced from `normalized_backup` after existing copy/content/metadata checks.
  No new provider reads, request mutation, or additional await is introduced.
  Failed content continues to raise; successful failure lists are empty.
- Retention, classification, events, deduplication, startup baseline, deletion,
  scope, metadata, concurrency and fail-closed algorithms are unchanged.

The device association can affect displayed friendly names (HA prefixes device
names), but existing registered entity IDs remain stable. New installations may
receive device-prefixed default entity IDs through normal HA naming.

## Automated checks

All eight beta1 standalone behavioral suites are rerun, plus device and action
UI suites: 118 test functions total (112 existing, six new).

- Two device tests: all eight share one service descriptor; simulated registry
  reload twice preserves every beta1 unique ID, custom entity IDs/names and a
  disabled entity, without duplicate devices/entities. This is a boundary
  simulation of HA's documented registry contract, not a full HA runtime test.
- Two create tests: readback values differ deliberately from input to detect
  request echoes; native SSL cases cover HA=true with omitted/empty/additional
  folders, HA=false with share only, and HA=false with explicit SSL.
- Two UI tests: folder options/defaults remain intact and both translations
  explain implicit SSL and explicit selection without Home Assistant.
- CI runs these suites, Python compilation, hassfest and HACS validation.

## Primary sources inspected

- [HA device registry](https://developers.home-assistant.io/docs/device_registry_index/)
- [HA service action descriptions](https://developers.home-assistant.io/docs/dev_101_services/)
- [HA 2026.9.4 entity platform registration](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/helpers/entity_platform.py)
- [HA 2026.9.4 native SSL rule](https://github.com/home-assistant/core/blob/2026.9.4/homeassistant/components/hassio/backup.py)
- [HA frontend service editor](https://github.com/home-assistant/frontend/blob/dev/src/components/ha-service-control.ts)

## Completed reduced beta2 live E2E

Verified on Home Assistant 2026.9.4 after upgrading beta1 to beta2:

- One service device and all eight original entity IDs preserved; no duplicates
  after upgrade/restart or a second complete restart.
- Italian action UI shows Additional folders and both SSL explanations; SSL
  remains explicitly selectable.
- Verified create fields match get_backup for HA included with no requested
  folders (`ssl` present), and HA excluded with `share` (`ssl` absent).
- HA included with `share` yields `share` + `ssl`; explicit `ssl` without HA works.
- One coherent backup-created event per observed create.
- All five disposable backups deleted from Local only, with no remaining copies.

No functional BMA blocker was identified. Provider failure was not induced on
live providers; fail-closed remains covered by simulations and review. S3/iDrive
is a separate native-provider incident outside scope.

### Procedure retained for reproducibility (completed)

1. Before updating, record the eight entity IDs. Install beta2 via HACS and
   restart HA. Confirm version, clean startup and one service device with all
   eight entities; IDs, history, existing cards and automations still work.
2. Open create in Actions. Check Additional folders / Cartelle aggiuntive and
   both SSL explanations. Confirm SSL is still selectable with HA disabled.
3. Local-only disposable create with HA=true, database=false, folders=[]:
   response reports HA=true, database=false and folders including ssl; compare
   all six new fields with get_backup. Confirm existing response keys and one
   success event remain available.
4. Local-only disposable create with HA=false, database=false, folders=[share]:
   response/get_backup report share without implicit ssl. Also try explicit
   folders=[ssl] with HA=false to verify standalone SSL selection.
5. Restart once more: one device, eight original entity IDs, no duplicates.

Use a dedicated beta2 test job and clean up only its known disposable backups.
No repeat of destructive GFS or provider-failure E2E is required by this change.
S3/iDrive remains outside scope. Real registry migration and visual UX passed
as recorded above; this historical procedure is not an outstanding release gate.
