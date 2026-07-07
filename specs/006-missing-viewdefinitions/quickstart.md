# Quickstart: Validate the MeasureReport & Composition Views (and the Measure removal)

**Feature**: `006-missing-viewdefinitions` | **Date**: 2026-07-06

Runnable end-to-end validation that the two new views materialize correctly, that measure-scoping
works, and that the retired `Measure` view is gone. Prerequisites and the publish/materialize
mechanics are unchanged from 002/004; this guide adds only the new checks.

## Prerequisites

- A working `config.json` (from `config.example.json`) pointing at the target Aidbox server with
  valid OAuth2 client-credentials (unchanged from 002).
- The processed test resources already persisted to that server — i.e. `process.py` has been run
  over `test/input/` so the first-class `MeasureReport` and promoted `Composition` resources exist,
  each stamped with the `processed-by` and `cms-measure` tags. (Run `python3 process.py` per the
  README if not.)
- Python 3 (stdlib only). No new dependency.

## Step 0 — Confirm the file changes are in place

```bash
ls viewdefinitions/measurereport.ViewDefinition.json   # present (NEW)
ls viewdefinitions/composition.ViewDefinition.json     # present (NEW)
! ls viewdefinitions/measure.ViewDefinition.json       # absent (REMOVED) — this line should error
python3 -c "import json,glob,sys; [json.load(open(f)) for f in glob.glob('viewdefinitions/*.json')]; print('all views parse')"
```

Expected: both new files present, `measure.ViewDefinition.json` gone, all views parse.

## Step 1 — Structural unit gate (no server needed)

```bash
python3 -m unittest tests.test_viewdefinition -v
```

Expected: green. The directory-driven shape suite now iterates the two new files (required fields,
`getResourceKey()` key column, provenance `where`, single-valued `cms_measure`) and no longer sees
the removed one — with no test edit.

## Step 2 — Publish & materialize the full view set

```bash
python3 publish_views.py --config config.json
```

Expected: per-view outcome lines for every checked-in view, including `measurereport` and
`composition` PUT + `$materialize` = success; **no** `measure` view line; exit 0. A single view's
failure is logged with the server's reason and reflected in exit status without blocking the others
(FR-013).

## Step 3 — MeasureReport view: one row per persisted MeasureReport, populations populated

Query `sof.measurereport_view` (via Aidbox SQL-on-FHIR / the server's query surface):

```sql
SELECT id, measure, status, subject, period_start, period_end,
       initial_population, denominator, numerator, denominator_exclusion, cms_measure
FROM measurereport_view
ORDER BY cms_measure;
```

Expected:
- One row per persisted first-class MeasureReport (one per scenario), zero rows for unrelated
  MeasureReports on the same server (provenance scoping, SC-001).
- `measure` shows the APHL canonical (e.g. `…/ControllingHighBloodPressureFHIR|0.0.002`);
  `subject` equals the matching `patient_view.id`.
- Population columns reflect `group.population.count`; a population absent on a report is null, not
  fabricated (FR-010). `measure_score` is null on the proportion-measure fixtures (no score) — also
  not fabricated.

## Step 4 — Composition view: one row per promoted Composition, metadata-only

```sql
SELECT id, status, type_code, type_display, subject, encounter, date, title, author, custodian, cms_measure
FROM composition_view;
```

Expected:
- One row per promoted Composition (in-population scenarios only), provenance-scoped (SC-002).
- `type_code` = `55751-2` (Public Health Case Report); `subject`/`encounter`/`author`/`custodian`
  are populated reference keys that join to `patient_view`/`encounter_view`/`practitioner_view`/
  `organization_view` (research R4) — not null, not `Type/`-prefixed strings.
- No `section`/clinical-content column exists (FR-005).

## Step 5 — Measure-scoped filtering (both new views)

```sql
SELECT count(*) FROM measurereport_view WHERE cms_measure = 'CMS165';
SELECT count(*) FROM composition_view   WHERE cms_measure = 'CMS165';
```

Expected: only rows attributed to that measure are returned; un-attributed rows would carry the
`unknown` sentinel (SC-005), consistent with every other view.

## Step 6 — Closure check (persisted types ↔ view targets)

```bash
# Target resource type of every checked-in view:
python3 -c "import json,glob; print(sorted(json.load(open(f))['resource'] for f in glob.glob('viewdefinitions/*.json')))"
```

Expected: the printed set equals the set of resource types the processor persists first-class
(Patient, Condition, Encounter, Observation, Practitioner, Organization, Location, Procedure,
MedicationRequest, ServiceRequest, Bundle, MeasureReport, Composition) — `Measure` absent,
`MeasureReport` and `Composition` present (SC-003/SC-004).

## Step 7 — Idempotent re-run

```bash
python3 publish_views.py --config config.json   # run again
```

Expected: each view updated in place (no duplicates), reported success, exit 0 (C6).

## Optional — orphaned server-side Measure view

Removing `measure.ViewDefinition.json` stops this project from re-publishing the Measure view but
does not delete a `sof.measure_view` already on the server. If a stale empty `measure_view` exists,
an operator MAY drop it server-side; it is outside this file-only feature (contract C5).

## Success = all of

- [ ] Step 1 unit suite green; both new files parse; Measure file gone (Step 0).
- [ ] Step 2 publishes + materializes both new views, no Measure view, exit 0.
- [ ] Step 3 MeasureReport view: one row per persisted MeasureReport, populations correct, nulls not fabricated.
- [ ] Step 4 Composition view: one row per promoted Composition, metadata-only, reference keys join.
- [ ] Step 5 measure-scoped filtering returns only the measure's rows on both views.
- [ ] Step 6 closure check: view targets == persisted first-class types.
- [ ] Step 7 re-run is idempotent (no duplicates).
