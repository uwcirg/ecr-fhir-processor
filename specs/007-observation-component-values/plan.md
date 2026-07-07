# Implementation Plan: Surface Component & Coded Measurements in the Observation View

**Branch**: `007-observation-component-values` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-observation-component-values/spec.md`; constitution
`.specify/memory/constitution.md` **v1.3.0** (Principle VII — Analytics View Definitions &
Materialization; Principle VI — first-class granularity; Principle V — never fabricate).

## Summary

The analytics team asked to see measurements that are currently invisible in the Observation view.
The reported case: **"Blood pressure panel with all children optional"** Observations show a row but
every measurement column is empty, because their Systolic/Diastolic readings live in the
Observation's nested `component[]` parts — which the current view never reads. This is a
**demand-driven Principle VII change**: the team specified the columns it wants.

One move, one file: **edit `viewdefinitions/observation.ViewDefinition.json`** to add columns that
surface the nested component measurements and enrich the coded-value case, per the 2026-07-07
clarification:

1. **Two generic component triads** — `component1_display` / `component1_value` / `component1_unit`
   and `component2_display` / `component2_value` / `component2_unit` — sourced **positionally** from
   `component[0]` and `component[1]`. Generic, self-describing via the display label (e.g. "Systolic
   blood pressure"), **not** type-specific-named. Empty for the many Observations with no components.
2. **`value_code_display`** — add the coded value's human-readable label
   (`value.ofType(CodeableConcept).coding.first().display`) alongside the existing `value_code`.
3. **Scalar quantity unchanged** — the existing `value_quantity` / `value_unit` columns already
   cover Hemoglobin A1c; no change (FR-005).

**No production code change.** `publish_views.py::discover_viewdefinitions()` globs
`viewdefinitions/*.json` and PUTs + `$materialize`s each file (002 FR-011, 004 R1). Delivering this
feature is **editing one existing view file**; `publish_views.py`, `fhir_common.py`, `process.py`,
and config are untouched. The directory-driven `tests/test_viewdefinition.py` shape suite (004 R8)
already covers `observation.ViewDefinition.json` — the added columns are covered with **no test
edit required** (verified: the suite asserts JSON validity, required fields, a `getResourceKey()`
key column, the provenance `where`, and a single-valued `cms_measure` column — none of which the new
columns disturb).

**One implementation risk, isolated and gated.** The **second** component triad requires a
positional index (`component[1]`). Every existing checked-in view uses only `.first()` / `.where()`
/ `.ofType()` — **no indexer anywhere** — so indexer support in Aidbox's SQL-on-FHIR FHIRPath is
**not yet demonstrated in this repo**. The authoritative gate (Principle III gate 2) is **server
acceptance on `PUT` + `$materialize`** and the quickstart query; the primary expression is the
indexer, with a documented one-line fallback (`.first()` / `.last()`) if Aidbox rejects or nulls it
(research R2). The user runs all live/e2e steps.

**Reviewable default, not a finalized contract.** As with Patient (002 FR-002) and the 004 views,
the column set ships as an informed default grounded in the actual fixture shapes (`test/input/`),
flagged for analytics-team confirmation. Refining it later is an edit to this one file plus a re-run.

## Technical Context

**Language/Version**: Python 3 (standard library only) for the unchanged publish step. The
deliverable is a **JSON `ViewDefinition` resource file** (no language runtime); FHIRPath column
expressions are evaluated server-side by Aidbox.

**Primary Dependencies**: None new. `publish_views.py` + `fhir_common.py` exist and are reused
**unchanged**. Dev/CI only: `ruff`, stdlib `unittest`. The HL7 `validator_cli.jar` does **not**
apply — a `ViewDefinition` is a SQL-on-FHIR logical-model resource outside the eCR/US-Core IG set;
its conformance gate is **Aidbox acceptance on `PUT` + `$materialize` success** (Principle III gate
2), not the reference validator (004 R5, mirrors 002).

**Storage**: Target Aidbox FHIR server (remote, OAuth2 client-credentials). The edited
ViewDefinition lives in `viewdefinitions/`; the materialized view lives server-side in Aidbox's
`sof` schema (`sof.observation_view`).

**Testing**: (1) **End-to-end against Aidbox** (quickstart) — publish + materialize the view against
a server holding the processed fixtures, then query `sof.observation_view` and assert the
blood-pressure panel rows now carry two populated triads (e.g. Systolic 128 mmHg / Diastolic
88 mmHg), the depression-screening rows carry a `value_code_display`, the Hemoglobin A1c row is
unchanged, and the row count is unchanged. (2) **Targeted stdlib `unittest`** — the existing
directory-driven suite in `tests/test_viewdefinition.py` already covers the edited file; no new test.

**Target Platform**: Linux (developer + GitHub Actions CI); anywhere Python 3 + network to Aidbox.

**Project Type**: Single-project CLI utility — **no structural change**. Edits one data file
(ViewDefinition); entry points (`process.py`, `publish_views.py`) over shared `fhir_common.py` are
unchanged.

**Performance Goals**: Not latency-critical. One view → one PUT + one `$materialize`; seconds
excluding network.

**Constraints**: Zero runtime dependencies; secrets never in VCS; base URL/creds from config only
(unchanged); per-view failure isolation (already implemented); idempotent re-run (PUT-by-id +
`$materialize` update-in-place); select only first-class resources (Principle VI — components are
intrinsic to the first-class Observation, not a separate un-promoted resource); never fabricate
column values (absent field / absent component → null, FR-004); one row per Observation (no
row-multiplying `forEach`; positional column reducers only, FR-003).

**Scale/Scope**: **One ViewDefinition edited**: +7 columns (2 component triads + `value_code_display`).
The blood-pressure panel (exactly two components) is the only component-bearing Observation in the
fixtures; two triads is a reviewable default sized to it (spec Assumptions).

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase, the `test/input/`
fixtures, and the 002/004 precedent; decisions are in [research.md](./research.md) (R1–R6). The one
real risk — indexer support for the positional second component — is resolved to a **primary
expression + documented fallback**, verified by the server-acceptance gate (research R2). The
representation decision (two generic positional triads; coded display added; scalar unchanged) was
settled in the spec's 2026-07-07 clarification session; no `NEEDS CLARIFICATION` remains.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | No code added; `publish_views.py`/`fhir_common.py` reused unchanged (stdlib only). Deliverable is a JSON file | ✅ PASS |
| II. FHIR Profile Conformance | A `ViewDefinition` is a SQL-on-FHIR logical-model resource, not an eCR/US-Core profiled resource, so `meta.profile` + the HL7 validator don't apply. IG-version config untouched. No processed-resource change ⇒ no `test/conformance-baseline.sigs` change | ✅ PASS |
| III. Dual-Gate Validation Testing | Authoritative gate is **server acceptance** (gate 2): `PUT` accepted + `$materialize` succeeds + quickstart query. Gate 1 (`validator_cli.jar`) N/A for ViewDefinitions. Pure shape covered by the existing directory-driven `unittest`; e2e by quickstart | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | N/A — edits a view over already-persisted resources, not measure/population input shapes. The view retains its `cms_measure` column so measure-scoped querying still works (003) | ✅ PASS (N/A) |
| V. Data Integrity & Defensive Processing | Never fabricate: an absent component or absent value → null (FR-004); empty triads are expected, not errors. Per-view failure isolation + idempotent re-run unchanged. No content dropped on the path to the server (this is a read-only analytics view) | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | The view selects from the first-class `Observation/<id>` resource only; **`component[]` is intrinsic to that Observation**, not content hidden in an un-promoted Bundle, so reading it honors the "first-class, individually-addressable" rule. One row per Observation preserved (FR-003) | ✅ PASS |
| VII. Analytics View Definitions & Materialization | **Directly satisfied and demand-driven**: the analytics team specified the columns it needs (the reported empty-BP-columns request) — exactly the demand signal Principle VII requires before touching a view. The edited view stays SQL-on-FHIR-conformant and is published/materialized by the existing idempotent, config-driven, per-view-isolated script. Columns are a reviewable default (see note) | ✅ PASS |
| VIII. Input Pre-Processing for Aidbox Storability | N/A — edits a view over already-persisted, already-storable resources; changes no input pre-processing and introduces no new HL7 or Aidbox validation surface | ✅ PASS (N/A) |
| Deployment & Security | base URL/creds from `config.json` only (unchanged); no new config field, no new secret | ✅ PASS |
| Development Workflow | Edits one data file; existing directory-driven `unittest` covers it; `process.py`/`publish_views.py`/`fhir_common.py` unchanged; README/known-issues updated to note the Observation view now surfaces component measurements + coded display; CI lint + unit + e2e quickstart | ✅ PASS |

**Note on Principle VII (demand-driven, reviewable columns).** Principle VII forbids adding views
*speculatively* and states the analytics team specifies which columns it wants. This feature is the
canonical in-bounds case: the team **explicitly requested** the missing measurement fields. As with
Patient (FR-002) and the 004 views, the *exact* column names/set ship as an informed, reviewable
default grounded in the fixtures, flagged for confirmation — recorded as a reviewable assumption,
not a violation.

**Result**: No violations. No Complexity Tracking entries required. This plan stays within
constitution v1.3.0.

## Project Structure

### Documentation (this feature)

```text
specs/007-observation-component-values/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R6 decisions (reuse, positional-component FHIRPath + fallback, triad paths, coded display, tests, conformance)
├── data-model.md        # Phase 1 — full observation_view column → FHIRPath table (existing + 7 new), before/after per fixture
├── quickstart.md        # Phase 1 — runnable publish→materialize→query validation for the new columns
├── contracts/           # Phase 1
│   └── observation-view-columns.md   # Conformance contract for the edited Observation ViewDefinition
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

> The publish/materialize CLI + `PUT`/`$materialize` server-operation contract is **unchanged** from
> 002 (`specs/002-patient-viewdefinition/contracts/publish-materialize-cli.md`); this feature adds no
> CLI surface, so it is referenced, not duplicated.

### Source Code (repository root)

```text
viewdefinitions/
└── observation.ViewDefinition.json      # EDIT — add 2 component triads + value_code_display

publish_views.py                          # UNCHANGED — already discovers & materializes every *.json view
fhir_common.py                            # UNCHANGED
process.py                                # UNCHANGED
config.example.json / config.json         # UNCHANGED — no new field

tests/
└── test_viewdefinition.py                # UNCHANGED — directory-driven shape suite already covers the edited file

README.md                                 # UPDATE — Observation view now surfaces component (BP) measurements + coded display
known-validation-issues.md                # UPDATE (if relevant) — note the indexer-support verification for component[1]
```

**Structure Decision**: Single-project CLI, unchanged from features 001–006. This feature edits one
existing data file (the Observation ViewDefinition). No new module, entry point, config field,
dependency, or test file. The publish/materialize mechanism already exists and is proven (002–006).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty. (The Principle VII demand-driven
> nuance is documented as a reviewable note in the Constitution Check, not a violation. The indexer
> risk is a data-file expression choice with a documented fallback, not a structural complexity.)
