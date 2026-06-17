# Implementation Plan: ViewDefinitions for the Remaining Resource Types

**Branch**: `004-remaining-viewdefinitions` | **Date**: 2026-06-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-remaining-viewdefinitions/spec.md`; constitution
`.specify/memory/constitution.md` **v1.2.0** (Principle VII — Analytics View Definitions &
Materialization; Principle VI — first-class granularity).

## Summary

Author **eleven new checked-in, version-controlled SQL-on-FHIR `ViewDefinition` files** — one
each for **Condition, Encounter, Observation, Practitioner, Organization, Location, Measure,
Bundle, Procedure, MedicationRequest, ServiceRequest** — alongside the existing
`patient.ViewDefinition.json`. Each flattens first-class resources of its type into **one row
per resource** with an informed, reviewable default column set, and — exactly like the Patient
view — carries a top-level `where` that scopes rows to resources this project's processor
persisted (the `…/processed-by = ecr-fhir-processor` provenance tag) plus a `cms_measure` column
read from the `…/cms-measure` tag (003-cms-measure-filter).

**No production code change.** `publish_views.py` already discovers and processes every `*.json`
in `viewdefinitions/` (002 FR-011, verified in this codebase: `discover_viewdefinitions()` globs
the directory). Delivering these eleven views is therefore **adding eleven files** plus extending
the targeted `unittest` to assert each file's shape — the publish/materialize mechanism, the
shared `fhir_common.py`, config, and `process.py` are untouched. This is the demand-driven
expansion Principle VII's `TODO(VIEWDEF_RESOURCE_TYPES)` anticipated: the project owner has now
named the resource types, which is the trigger the principle requires.

**Reviewable defaults, not finalized contracts.** No finalized analytics-team column list was
supplied, so each view ships the same way Patient did under FR-002 — an informed default column
set drawn from the analytically-relevant fields actually present on the fixtures, flagged for
analytics-team confirmation. Adjusting a column set later is an edit to one file + a re-run, no
mechanism change.

**Grounded in the fixtures.** Default columns were derived from the resource shapes actually
present in `test/input/` (Condition/Encounter/Observation/Practitioner/Organization/Location
appear in every collection Bundle; Procedure/MedicationRequest/ServiceRequest appear sparsely;
Bundle is persisted for provenance). **Measure is the one exception: no `Measure` resource is
persisted by this project** — MeasureReports only *reference* APHL Measure canonicals. The Measure
view is still authored as requested, but it is expected to return **zero rows until/unless Measure
resources are loaded** (an empty view is not a failure — spec edge case; research.md R5).

## Technical Context

**Language/Version**: Python 3 (standard library only) for the unchanged publish step. The
deliverables themselves are **JSON `ViewDefinition` resource files** (no language runtime). FHIRPath
column expressions are evaluated server-side by Aidbox.

**Primary Dependencies**: None new. `publish_views.py` + `fhir_common.py` already exist and are
reused **unchanged**. Dev/CI only: `ruff`, stdlib `unittest`. The HL7 `validator_cli.jar` does
**not** apply — a `ViewDefinition` is a SQL-on-FHIR logical-model resource outside the eCR/US-Core
IG set; its conformance gate is **Aidbox acceptance on `PUT` + `$materialize` success** (Principle
III gate 2), not the reference validator (research.md R5, mirrors 002).

**Storage**: Target Aidbox FHIR server (remote, OAuth2 client-credentials). The eleven new
ViewDefinition files live in `viewdefinitions/`; the materialized views live server-side in
Aidbox's `sof` schema (`sof.<name>_view`).

**Testing**: (1) **End-to-end against Aidbox** (quickstart) — publish + materialize all twelve
views against a server holding the processed fixtures, then query each new view and assert one row
per persisted resource of that type with expected columns, provenance-scoped and
measure-filterable. (2) **Targeted stdlib `unittest`** — extend `tests/test_viewdefinition.py` to
assert, for every checked-in ViewDefinition file: valid JSON; required fields
(`resourceType`/`id`/`name`/`status`/`resource`/non-empty `select`); a `getResourceKey()` key
column; the provenance `where` filter; and a single-valued `cms_measure` column on the
clinical/reference types — driven generically over the directory so a new file is covered with no
new test.

**Target Platform**: Linux (developer + GitHub Actions CI); anywhere Python 3 + network to Aidbox.

**Project Type**: Single-project CLI utility — **no structural change**. This feature adds data
files (ViewDefinitions) and test assertions only; the two entry points (`process.py`,
`publish_views.py`) over shared `fhir_common.py` are unchanged.

**Performance Goals**: Not latency-critical. Twelve views ⇒ a bounded handful of server
round-trips (PUT + `$materialize` per view); completes in seconds excluding network.

**Constraints**: Zero runtime dependencies; secrets never in VCS; base URL/credentials from config
only (unchanged); per-view failure isolation (one view's failure never blocks another — already
implemented); idempotent re-run (PUT-by-id + `$materialize` update-in-place); select only
first-class resources (Principle VI); never fabricate column values (absent field → null, FR-007);
one row per resource (deterministic `.first()` reducers, no row-multiplying `forEach`).

**Scale/Scope**: **Eleven new ViewDefinitions** (twelve total with Patient). Bundle view is
metadata-only (FR-011); Measure view is authored but empty-until-loaded (research.md R5).

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase + the `test/input/`
fixtures + Aidbox/SQL-on-FHIR docs; decisions are in [research.md](./research.md) (R1–R8). No
`NEEDS CLARIFICATION` remains. The per-type default column sets (FR-002) are informed, reviewable
defaults, not finalized analytics-team contracts — captured in [data-model.md](./data-model.md)
and the contract, flagged for confirmation, not treated as a blocker.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | No code added; `publish_views.py`/`fhir_common.py` reused unchanged (stdlib only). Deliverables are JSON files | ✅ PASS |
| II. FHIR Profile Conformance | A `ViewDefinition` is a SQL-on-FHIR logical-model resource, not an eCR/US-Core profiled resource, so `meta.profile` + the HL7 validator don't apply. IG-version config untouched (research.md R5) | ✅ PASS |
| III. Dual-Gate Validation Testing | Authoritative gate for each view is **server acceptance** (gate 2): `PUT` accepted + `$materialize` succeeds. Gate 1 (`validator_cli.jar`) N/A for ViewDefinitions. Pure shape covered by `unittest`; e2e by quickstart | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | N/A — defines views over already-persisted resources, not measure/population input shapes. Every view carries the `cms_measure` column so measure-scoped querying works across all types (003) | ✅ PASS (N/A) |
| V. Data Integrity & Defensive Processing | Per-view failure isolation already implemented and unchanged; idempotent re-run via PUT-by-id; never fabricate (absent field → null, FR-007); empty view (incl. Measure) is success, not failure; rejection surfaced not swallowed | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | Every view selects only from first-class `Type/<id>` resources (FR-003); none reaches into an un-promoted Bundle. The Bundle view reads first-class Bundle resources' own metadata, not their nested content (FR-011) | ✅ PASS |
| VII. Analytics View Definitions & Materialization | **Directly satisfied & extended**: eleven new conformant, checked-in ViewDefinitions published/materialized by the existing idempotent, config-driven, per-type-isolated script. **Demand-driven trigger**: the project owner explicitly named these resource types — the signal Principle VII requires; columns are reviewable defaults (see note) | ✅ PASS (see note) |
| Deployment & Security | base URL/creds from `config.json` only (unchanged); no new config field, no new secret | ✅ PASS |
| Development Workflow | Additive files + extended `unittest`; `process.py`/`publish_views.py`/`fhir_common.py` unchanged; README updated to note views now span twelve resource types; CI lint + unit + e2e quickstart | ✅ PASS |

**Note on Principle VII (demand-driven scope).** Principle VII forbids adding ViewDefinitions
*speculatively* — only "once the analytics team specifies the fields/columns it wants." This
feature is triggered by the **project owner explicitly naming the eleven resource types**, which is
the demand signal the principle requires; the work is not speculative. The *exact columns* were not
finalized, so — exactly as the Patient view did under FR-002 — each view ships an informed,
reviewable default flagged for analytics-team confirmation. This honors the principle's intent (no
purely speculative views; conformant, checked-in, idempotently materialized) while not blocking on
a column list the request did not include. Recorded as an explicit, reviewable assumption rather
than a violation.

**Result**: No violations. No Complexity Tracking entries required. This plan stays within
constitution v1.2.0 and operationalizes Principle VII beyond Patient for the first time.

## Project Structure

### Documentation (this feature)

```text
specs/004-remaining-viewdefinitions/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R8 decisions (reuse, per-type columns, Measure-empty, Bundle-thin, etc.)
├── data-model.md        # Phase 1 — the 11 ViewDefinitions + per-type column→FHIRPath tables; reused outcome model
├── quickstart.md        # Phase 1 — runnable publish→materialize→query validation guide for the new views
├── contracts/           # Phase 1
│   └── viewdefinitions-remaining.md   # Conformance contract for the 11 new ViewDefinition resources
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

> The publish/materialize CLI + `PUT`/`$materialize` server-operation contract is **unchanged**
> from 002 (`specs/002-patient-viewdefinition/contracts/publish-materialize-cli.md`); this feature
> adds no CLI surface, so it is referenced, not duplicated.

### Source Code (repository root)

```text
viewdefinitions/                          # Existing dir — auto-discovered by publish_views.py
├── patient.ViewDefinition.json           #   existing (002/003) — unchanged
├── condition.ViewDefinition.json         # NEW
├── encounter.ViewDefinition.json         # NEW
├── observation.ViewDefinition.json       # NEW
├── practitioner.ViewDefinition.json      # NEW
├── organization.ViewDefinition.json      # NEW
├── location.ViewDefinition.json          # NEW
├── measure.ViewDefinition.json           # NEW (empty-until-loaded; research.md R5)
├── bundle.ViewDefinition.json            # NEW (metadata-only; FR-011)
├── procedure.ViewDefinition.json         # NEW
├── medicationrequest.ViewDefinition.json # NEW
└── servicerequest.ViewDefinition.json    # NEW

publish_views.py                          # UNCHANGED — already discovers every *.json view
fhir_common.py                            # UNCHANGED
process.py                                # UNCHANGED
config.example.json / config.json         # UNCHANGED — no new field

tests/
└── test_viewdefinition.py                # EXTENDED — generic per-file shape assertions over the
                                          #   whole viewdefinitions/ dir (every view: required fields,
                                          #   resource-key column, provenance where, cms_measure column)

README.md                                 # UPDATE — "What it does" now lists views across 12 resource types
```

**Structure Decision**: Single-project CLI, unchanged from features 001–003. This feature is
**purely additive data + tests**: eleven JSON ViewDefinition files dropped into the existing
auto-discovered `viewdefinitions/` directory, and a generalization of `tests/test_viewdefinition.py`
so the shape checks run over every file rather than just Patient. No new module, entry point,
config field, or dependency. The mechanism that publishes and materializes them already exists and
is proven (002/003).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty. (The Principle VII demand-driven
> nuance is documented as a reviewable assumption in the Constitution Check note, not a violation.)
