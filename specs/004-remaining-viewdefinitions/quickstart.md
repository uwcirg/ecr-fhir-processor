# Quickstart: ViewDefinitions for the Remaining Resource Types

**Feature**: `004-remaining-viewdefinitions` | **Date**: 2026-06-16

Runnable validation that the eleven new views publish, materialize, and return one flat row per
first-class resource of their type — provenance-scoped and measure-filterable. Proves SC-001…SC-007.
Builds on the unchanged publish step (002 quickstart). Details: [contracts/](./contracts/),
[data-model.md](./data-model.md).

## Prerequisites

- Python 3 (stdlib only — no install step; Principle I).
- `config.json` with real `server.{base_url, token_endpoint, client_id, client_secret}` for an
  **Aidbox ≥ 2508** target (`$materialize` requires 2508+).
- The processed fixtures persisted on that server — run the processor first so first-class
  Condition/Encounter/Observation/Practitioner/Organization/Location/Procedure/MedicationRequest/
  ServiceRequest/Bundle resources exist, each carrying the `…/processed-by` and `…/cms-measure`
  tags:

  ```bash
  python process.py --config config.json --input test/input --output test/output
  ```

  Note the persisted count per type (e.g. from the processor's summary), call it **N_type**.
- The twelve checked-in files under `viewdefinitions/` (Patient + the eleven new ones).

## 1. Dry run (no network) — verify all twelve are discovered

```bash
python publish_views.py --dry-run --verbose
```

**Expect**: all twelve ViewDefinition files discovered, each reported as a planned
`PUT … /ViewDefinition/<id>` + `POST … /$materialize`; no server contact. A malformed/id-less file
would fail *that file* only (FR-010).

## 2. Publish + materialize all views (one invocation, no command change — SC-006)

```bash
python publish_views.py --config config.json --verbose
```

**Expect** (FR-004, FR-009/FR-010): a per-view block for each of the twelve, then a roll-up:

```
ViewDefinition: condition
  publish:     OK (200|201)
  materialize: OK  -> sof.condition_view (view)
... (encounter, observation, practitioner, organization, location, measure,
     bundle, procedure, medicationrequest, servicerequest, patient) ...
--- 12 views: 12 published, 12 materialized, 0 failed ---
```

Exit status `0`. A timestamped audit log is written under `log/`. **No change to the invocation**
versus the Patient-only run — the new views are picked up by directory discovery.

## 3. Query each new view — one row per resource, provenance-scoped (SC-001/SC-002/SC-004)

Against the Aidbox database / SQL endpoint:

```sql
SELECT count(*) FROM sof.condition_view;     -- expect N_Condition
SELECT count(*) FROM sof.encounter_view;     -- expect N_Encounter
SELECT count(*) FROM sof.observation_view;   -- expect N_Observation
-- ... one per type ...

SELECT id, code, code_display, clinical_status, subject, encounter, onset_date_time, cms_measure
FROM sof.condition_view
ORDER BY recorded_date;
```

**Expect**:
- Each `count(*) = N_type` — exactly one row per first-class resource the processor persisted, and
  **zero** rows for unrelated resources of that type on the same server (SC-002, via the provenance
  `where`).
- Columns reflect the source resource; absent fields are **NULL**, never fabricated (SC-004). E.g.
  a fixture Condition → `code=44054006`, `code_display=Diabetes mellitus type 2 (disorder)`,
  `clinical_status=active`, `subject=Patient/…`; a fixture Observation →
  `code=4548-4`, `value_quantity=9.2`, `value_unit=%`, `effective_date_time=2025-05-15T09:15:00Z`.

## 4. Measure-scoped filter across types (SC-005)

```sql
SELECT count(*) FROM sof.condition_view   WHERE cms_measure = 'CMS122';
SELECT count(*) FROM sof.observation_view WHERE cms_measure = 'CMS165';
SELECT DISTINCT cms_measure FROM sof.encounter_view;   -- e.g. {CMS2, CMS122, CMS165, unknown}
```

**Expect**: each view's `cms_measure` column filters to exactly the resources attributed to that
measure — the same measure-scoping the Patient view supports (003), now total across every type.

## 5. Cross-view join (the analytics payoff)

```sql
SELECT o.code, o.value_quantity, o.value_unit, c.code AS condition_code, e.period_start
FROM   sof.observation_view o
JOIN   sof.encounter_view  e ON o.encounter = e.id
JOIN   sof.condition_view  c ON c.subject   = o.subject
WHERE  o.cms_measure = 'CMS122';
```

**Expect**: views join on their reference columns (`subject`, `encounter`) within this project's
data — the flat, multi-resource analytics the feature delivers.

## 6. Measure view is empty-until-loaded (research.md R5)

```sql
SELECT count(*) FROM sof.measure_view;       -- expect 0 today
```

**Expect**: the Measure view **materialized successfully** in step 2 (counted in "12 materialized")
but returns **zero rows** — no `Measure` resource is persisted yet. This is success, not failure.

## 7. Bundle view is metadata-only (FR-011)

```sql
SELECT id, type, timestamp, identifier, entry_count, cms_measure FROM sof.bundle_view;
```

**Expect**: one row per persisted Bundle with container metadata only — no nested clinical columns.

## 8. Idempotent re-run (SC-006)

```bash
python publish_views.py --config config.json
```

**Expect**: success again; still **exactly one** of each `ViewDefinition/<id>` and `sof.<type>_view`
(no duplicates). Re-running re-persists/rolls back nothing (FR-009).

## 9. Failure surfacing (SC-007)

Point `--viewdefinitions-dir` at a copy where one view has a deliberately non-conformant column
(unknown FHIRPath), then run.

**Expect**: the server's rejection reason is logged, that one view is reported failed (publish or
materialize, distinguished), the run exits **non-zero**, and **all other views are still published
and materialized** (FR-010, per-view isolation).

## Automated checks

- `python -m unittest tests/test_viewdefinition.py` — now iterates over every
  `viewdefinitions/*.json`: required fields, `getResourceKey()` key column, provenance `where`,
  no row-multiplying `forEach`, single-valued `cms_measure` column (research.md R8) — plus the
  existing Patient-specific assertions and the publish-step logic tests.
- CI lint (`ruff`). No production code changed by this feature.
