# Contract: Publish/Materialize CLI + server operations

**Feature**: `002-patient-viewdefinition` | **Entry point**: `publish_views.py` (new script)

The operational mechanism (Story 2) that uploads every checked-in ViewDefinition and materializes
it. Resource-type-agnostic: it discovers files from `viewdefinitions/`, so adding a resource type
later needs no change here (FR-011, Story 3). Separate entry point from `process.py` (different
trigger — research.md R4); reuses config/client/logging/outcome machinery imported from the shared
`fhir_common.py` (research.md R1).

## CLI

```
python publish_views.py [--config config.json]
                        [--viewdefinitions-dir viewdefinitions]
                        [--materialize-type view|materialized-view|table]
                        [--dry-run] [--verbose] [--log-dir log]
```

- `--config` (default `config.json`): reuses `load_config` + `validate_config`.
- `--viewdefinitions-dir` (default `viewdefinitions`): directory scanned for `*.json`
  ViewDefinition files.
- `--materialize-type` (default from `server.materialize_type`, else `view`): the
  `$materialize` `type` (research.md R3).
- `--dry-run`: discover + validate files and report the planned PUT/`$materialize` calls **without
  contacting the server** (mirrors existing `--dry-run`, which skips credential checks).
- `--verbose`, `--log-dir`: as in the existing CLI.

**Exit status**: `0` iff every discovered view both published and materialized successfully;
non-zero if any publish or materialize failed (after all views attempted). Mirrors
`RunSummary.exit_code()`.

## Startup behavior (FR-006/FR-007)

1. Load config; run `validate_config` → if required `server.*` missing/placeholder (and not
   `--dry-run`), **fail loudly before any network call** with the existing clear messages.
2. Discover ViewDefinition files. Zero files found → report and exit non-zero (nothing to do is an
   operator error worth surfacing); `--dry-run` may treat empty as a warning.
3. Each file must parse as JSON and have `resourceType: "ViewDefinition"` + an `id`; a malformed
   or id-less file fails *that file* (recorded, reflected in exit), others still proceed.

## Server operations (per view, in order)

### 1. Publish (update-in-place)

```
PUT {base}/ViewDefinition/{id}
Content-Type: application/fhir+json
Authorization: Bearer <token>          # reuses FhirClient token cache + 401 refresh
[aidbox-validation-skip: ...]          # only if server.validation_skip configured
<the ViewDefinition JSON from the file>
```

- `{base}` = `server.base_url` (same convention as existing `submit_put`; research.md R2).
- Success: HTTP 200/201. Failure: surface server status + body (FR-008); record publish failure;
  **skip** this view's materialize; continue with remaining views.

### 2. Materialize

```
POST {base}/ViewDefinition/{id}/$materialize
Content-Type: application/fhir+json
Authorization: Bearer <token>
{ "resourceType": "Parameters",
  "parameter": [ { "name": "type", "valueCode": "<materialize-type>" } ] }
```

- Success (HTTP 200): body is a `Parameters` with `viewName` / `viewType` / `viewSchema`
  (e.g. `sof.patient_view`). Record materialize success with `viewName`.
- Failure: body is an `OperationOutcome`; surface its `diagnostics` (FR-008). Record materialize
  failure — the operator learns the view **exists but is not materialized** (spec edge case);
  reflected in exit status.

## Idempotency (FR-005, SC-003)

- `PUT`-by-id updates in place → re-running yields exactly **one** ViewDefinition per file, no
  duplicates.
- `$materialize` creates-or-updates the server object → re-running does not duplicate the view.
- Re-running touches only the views; it does not re-persist or roll back unrelated resources.

## Reporting (FR-009)

Per view, the summary distinguishes the two outcomes, e.g.:

```
ViewDefinition: patient
  publish:     OK (200)
  materialize: OK  -> sof.patient_view (view)
--- 1 view: 1 published, 1 materialized, 0 failed ---
```

On failure the server's reason is logged (console + timestamped `log/` audit file) and the run
exits non-zero.

## Edge cases (from spec)

| Situation | Behavior |
|-----------|----------|
| No Patient resources on server | materialize succeeds; view has 0 rows; report zero rows; exit 0 |
| Server rejects ViewDefinition (non-conformant) | surface server validation error; exit non-zero; do not silently skip |
| Materialize fails after successful publish | report publish=OK, materialize=FAILED separately; exit non-zero |
| Config missing/invalid | fail at startup before contacting server, clear message |
| Multiple ViewDefinition files | each processed independently; one failure does not block others |

## Test expectations

- Unit (`unittest`): file discovery from a temp dir; `$materialize` `Parameters` body builder;
  outcome aggregation → exit code (all-ok → 0, any-failure → non-zero); config-validation reuse;
  malformed/id-less file isolation.
- E2E (quickstart): real publish + materialize against Aidbox; re-run shows no duplicate; induced
  failure (bad ViewDefinition) surfaces server reason + non-zero exit.
