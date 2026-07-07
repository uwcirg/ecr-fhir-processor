# Quickstart: Validate Component & Coded Columns on the Observation View

**Feature**: 007-observation-component-values | **Date**: 2026-07-07

A runnable guide to prove the edited `observation.ViewDefinition.json` surfaces the blood-pressure
panel readings and the coded-result label, with no regression and no extra rows. Implementation
details live in [data-model.md](./data-model.md) and
[contracts/observation-view-columns.md](./contracts/observation-view-columns.md).

> **Live/e2e steps run against Aidbox — the user runs these.** Claude stops at the local, offline
> steps (JSON parse, shape unit test, dry inspection).

## Prerequisites

- A working `config.json` (from `config.example.json`) pointing at the target Aidbox server.
- The server already holds the **processed fixtures** (run `python3 process.py` and load its output,
  per the main README), so `sof.observation_view` has rows to project — including the controllable-BP
  blood-pressure panels, the depression-screening coded results, and the Hemoglobin A1c scalar.
- Python 3 (stdlib only). No new dependency.

## Step 0 — (offline) capture the pre-edit baseline row count

Before editing, note the current `sof.observation_view` row count (used to prove no regression):

```sql
SELECT count(*) AS observation_rows FROM sof.observation_view;
```

## Step 1 — (offline) the edit parses and passes the shape suite

After editing `viewdefinitions/observation.ViewDefinition.json`:

```bash
# Valid JSON
python3 -c "import json; json.load(open('viewdefinitions/observation.ViewDefinition.json')); print('observation view parses')"

# Directory-driven shape suite still green (covers the edited file; no new test)
python3 -m unittest tests.test_viewdefinition -v
```

Expected: JSON parses; the shape suite passes (required fields, `getResourceKey()` key column,
provenance `where`, single `cms_measure` column all intact).

## Step 2 — (live) publish + materialize

```bash
python3 publish_views.py --config config.json
```

Expected: the Observation view `PUT` is accepted and its `$materialize` succeeds (per-view failure
isolation means other views are unaffected regardless). **If the Observation view is rejected on the
`component[0]`/`component[1]` indexer**, apply the fallback (`component.first()` / `component.last()`
— research R2, contract) and re-run; that rejection is the expected signal that resolves indexer
support, not a design defect.

## Step 3 — (live) blood-pressure panels now show two triads (SC-001, US1)

```sql
SELECT id,
       component1_display, component1_value, component1_unit,
       component2_display, component2_value, component2_unit
FROM sof.observation_view
WHERE code = '85354-9';        -- Blood pressure panel with all children optional
```

Expected: each panel row shows two populated triads, e.g.
`("Systolic blood pressure", 128, "mmHg")` and `("Diastolic blood pressure", 88, "mmHg")` for the
not-in-population controllable-BP example — **0 rows with all-empty measurement columns**.

## Step 4 — (live) coded results now carry a display label (US2, FR-006)

```sql
SELECT id, value_code, value_code_display
FROM sof.observation_view
WHERE code IN ('73831-0', '73832-8');   -- depression screening
```

Expected: `value_code` (existing) present **and** `value_code_display` (new) non-null.

## Step 5 — (live) scalar quantity unchanged; no regression (SC-004, FR-005)

```sql
SELECT id, value_quantity, value_unit,
       component1_value, component2_value
FROM sof.observation_view
WHERE code = '4548-4';         -- Hemoglobin A1c
```

Expected: `value_quantity` + `value_unit` unchanged from before the edit; all component columns
null (a scalar Observation has no components).

## Step 6 — (live) one row per Observation preserved (SC-002)

```sql
SELECT count(*) AS observation_rows FROM sof.observation_view;
```

Expected: **equal to the Step 0 baseline** — adding component columns did not multiply any panel
into multiple rows.

## Success criteria mapping

| Step | Proves |
|------|--------|
| 1 | Edited view is structurally conformant (shape suite) |
| 2 | Server acceptance gate (Principle III gate 2); resolves indexer vs fallback |
| 3 | SC-001 / US1 — BP panel Systolic + Diastolic readable, 0 all-empty rows |
| 4 | US2 / FR-006 — coded result label present |
| 5 | SC-004 / FR-005 — scalar case unchanged, no regression; empty triads expected |
| 6 | SC-002 — one row per Observation (row count invariant) |
