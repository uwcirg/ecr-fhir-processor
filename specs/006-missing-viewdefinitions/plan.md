# Implementation Plan: ViewDefinitions for the Missing Persisted Resource Types

**Branch**: `006-missing-viewdefinitions` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-missing-viewdefinitions/spec.md`; constitution
`.specify/memory/constitution.md` **v1.3.0** (Principle VII — Analytics View Definitions &
Materialization; Principle VI — first-class granularity; Principle V — never fabricate).

## Summary

Close the gap between the resource types this project persists as first-class resources and the
checked-in SQL-on-FHIR `ViewDefinition` set. Three moves:

1. **Add `measurereport.ViewDefinition.json`** — one row per persisted first-class `MeasureReport`,
   with the measure canonical, status/type, subject/reporter reference keys, reporting period,
   named population-count columns, measure score, improvement notation, and the `cms_measure`
   attribution column. This is the resource that ties each processed eCR to its CMS-measure
   outcome, and today it has no view.
2. **Add `composition.ViewDefinition.json`** — one row per promoted first-class `Composition`,
   **metadata only** (status, type, category, subject/encounter/author/custodian reference keys,
   date, title) — no flattening of nested `section` content, which is already promoted to its own
   first-class resources and covered by the other views (Principle VI).
3. **Remove `measure.ViewDefinition.json`** — it targets `Measure`, a resource type this pipeline
   never produces or persists (the fixtures only *reference* APHL Measure canonicals from
   MeasureReports). 004 shipped it knowingly "empty-until-loaded"; this feature retires it so the
   checked-in view set contains no view that can never return a row.

**No production code change.** `publish_views.py::discover_viewdefinitions()` globs
`viewdefinitions/*.json` and PUTs + `$materialize`s each file with per-view failure isolation
(002 FR-011, 004 R1 — verified in this codebase). Delivering this feature is **adding two files and
deleting one**; `publish_views.py`, `fhir_common.py`, `process.py`, and config are untouched. The
targeted `tests/test_viewdefinition.py` shape suite is already directory-driven (004 R8), so the two
new files are covered and the removed file drops out with **no test edit required** — verified: no
test references the `measure` view by name, and `tests/test_discovery.py`'s `len(files) == 18`
counts eCR **input** fixtures, not view files, so it is unaffected.

**Reviewable defaults, not finalized contracts.** As with Patient (002 FR-002) and the 004 views,
each new view ships an informed default column set grounded in the actual fixture shapes
(`test/input/`), flagged for analytics-team confirmation — not a finalized column contract.
Refining a column set later is an edit to one file plus a re-run.

**Closure invariant.** After this feature the set of ViewDefinition target resource types equals
the set of resource types the processor persists first-class (US3 / SC-004): no persisted type
without a view, no view without a persisted type.

## Technical Context

**Language/Version**: Python 3 (standard library only) for the unchanged publish step. The
deliverables are **JSON `ViewDefinition` resource files** (no language runtime); FHIRPath column
expressions are evaluated server-side by Aidbox.

**Primary Dependencies**: None new. `publish_views.py` + `fhir_common.py` exist and are reused
**unchanged**. Dev/CI only: `ruff`, stdlib `unittest`. The HL7 `validator_cli.jar` does **not**
apply — a `ViewDefinition` is a SQL-on-FHIR logical-model resource outside the eCR/US-Core IG set;
its conformance gate is **Aidbox acceptance on `PUT` + `$materialize` success** (Principle III gate
2), not the reference validator (004 R5, mirrors 002).

**Storage**: Target Aidbox FHIR server (remote, OAuth2 client-credentials). The two new
ViewDefinition files live in `viewdefinitions/`; materialized views live server-side in Aidbox's
`sof` schema (`sof.measurereport_view`, `sof.composition_view`).

**Testing**: (1) **End-to-end against Aidbox** (quickstart) — publish + materialize the full view
set against a server holding the processed fixtures, then query the two new views and assert one
row per persisted resource of that type with expected columns, provenance-scoped and
measure-filterable; confirm the `Measure` view is gone. (2) **Targeted stdlib `unittest`** — the
existing directory-driven suite in `tests/test_viewdefinition.py` already asserts, for every
checked-in ViewDefinition: valid JSON; required fields
(`resourceType`/`id`/`name`/`status`/`resource`/non-empty `select`); a `getResourceKey()` key
column; the provenance `where`; and a single-valued `cms_measure` column — so the two new files are
covered with no new test.

**Target Platform**: Linux (developer + GitHub Actions CI); anywhere Python 3 + network to Aidbox.

**Project Type**: Single-project CLI utility — **no structural change**. Adds data files
(ViewDefinitions) only; entry points (`process.py`, `publish_views.py`) over shared
`fhir_common.py` are unchanged.

**Performance Goals**: Not latency-critical. The bounded view set ⇒ a handful of server
round-trips (PUT + `$materialize` per view); completes in seconds excluding network.

**Constraints**: Zero runtime dependencies; secrets never in VCS; base URL/creds from config only
(unchanged); per-view failure isolation (already implemented); idempotent re-run (PUT-by-id +
`$materialize` update-in-place); select only first-class resources (Principle VI); never fabricate
column values (absent field → null, FR-010); one row per resource (deterministic `.first()` /
named-`.where()` reducers, no row-multiplying `forEach`, FR-011).

**Scale/Scope**: **Two new ViewDefinitions, one removed.** MeasureReport carries multi-valued
population data reduced to named single-valued columns (research R3); Composition is metadata-only
(FR-005).

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase, the `test/input/`
fixtures, and the 002/004 precedent; decisions are in [research.md](./research.md) (R1–R6). No
`NEEDS CLARIFICATION` remains. The two scope decisions (retire the `Measure` view + add
MeasureReport; metadata-only Composition) were settled in the spec's 2026-07-06 clarification
session. Default column sets (FR-004/FR-005) are informed, reviewable defaults grounded in the
fixtures — captured in [data-model.md](./data-model.md) and the contract, flagged for confirmation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | No code added; `publish_views.py`/`fhir_common.py` reused unchanged (stdlib only). Deliverables are JSON files | ✅ PASS |
| II. FHIR Profile Conformance | A `ViewDefinition` is a SQL-on-FHIR logical-model resource, not an eCR/US-Core profiled resource, so `meta.profile` + the HL7 validator don't apply. IG-version config untouched (004 R5). No change to `test/conformance-baseline.sigs` — no processed resource changes | ✅ PASS |
| III. Dual-Gate Validation Testing | Authoritative gate for each view is **server acceptance** (gate 2): `PUT` accepted + `$materialize` succeeds. Gate 1 (`validator_cli.jar`) N/A for ViewDefinitions. Pure shape covered by the existing directory-driven `unittest`; e2e by quickstart | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | N/A — defines views over already-persisted resources, not measure/population input shapes. Both new views carry the `cms_measure` column so measure-scoped querying works for them too (003) | ✅ PASS (N/A) |
| V. Data Integrity & Defensive Processing | Per-view failure isolation already implemented and unchanged; idempotent re-run via PUT-by-id; never fabricate (absent field → null, FR-010); empty view is success; rejection surfaced not swallowed. **Removing the `Measure` view drops nothing analyzable — it never returned a row** (004 R5) | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | Both views select only from first-class `Type/<id>` resources (FR-006); neither reaches into an un-promoted Bundle. The Composition view reads the promoted first-class Composition's document metadata, not its nested `section` content (FR-005) | ✅ PASS |
| VII. Analytics View Definitions & Materialization | **Directly satisfied**: two new conformant, checked-in ViewDefinitions published/materialized by the existing idempotent, config-driven, per-view-isolated script. **Demand-driven, corrective trigger**: the project owner identified persisted types (MeasureReport, Composition) that lack a view — the demand signal Principle VII requires — and a view (`Measure`) targeting a never-persisted type. Columns are reviewable defaults (see note) | ✅ PASS (see note) |
| VIII. Input Pre-Processing for Aidbox Storability | N/A — this feature adds views over already-persisted, already-storable resources; it changes no input pre-processing and introduces no new HL7 or Aidbox validation surface | ✅ PASS (N/A) |
| Deployment & Security | base URL/creds from `config.json` only (unchanged); no new config field, no new secret | ✅ PASS |
| Development Workflow | Additive/deletive data files; existing directory-driven `unittest` covers them; `process.py`/`publish_views.py`/`fhir_common.py` unchanged; README updated to note the view set now covers MeasureReport + Composition and no longer ships an empty Measure view; CI lint + unit + e2e quickstart | ✅ PASS |

**Note on Principle VII (demand-driven, corrective scope).** Principle VII forbids adding
ViewDefinitions *speculatively*. This feature is **not** speculative: it is triggered by concrete
persisted resource types (MeasureReport, Composition) that the processor already writes as
first-class resources but that have no view, and it retires a view (`Measure`) whose target type is
never persisted — a demand-driven correction, not a speculative addition. The *exact columns* were
not finalized, so — exactly as Patient (FR-002) and the 004 views — each new view ships an informed,
reviewable default flagged for analytics-team confirmation. Recorded as a reviewable assumption, not
a violation.

**Removing a checked-in ViewDefinition — is that a regression?** No. The `Measure` view materializes
zero rows for this data (004 R5 documented it as empty-until-loaded because no `Measure` resource is
ever persisted). Removing it drops nothing an analyst could have queried and eliminates a view that
misleadingly implies Measure data exists. Principle V's "never silently drop content" concerns
**clinical content on the path to the server**, not retiring an empty analytics view; the removal is
explicit, documented (FR-003, this plan, README), and reflected in the view set — not silent.

**Result**: No violations. No Complexity Tracking entries required. This plan stays within
constitution v1.3.0 and completes the persisted-type ↔ view correspondence Principle VII implies.

## Project Structure

### Documentation (this feature)

```text
specs/006-missing-viewdefinitions/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R6 decisions (reuse, MeasureReport columns, Composition-metadata, Measure-removal, refs, tests)
├── data-model.md        # Phase 1 — the 2 new ViewDefinitions + column→FHIRPath tables; reused outcome model; the removal
├── quickstart.md        # Phase 1 — runnable publish→materialize→query validation guide for the new views + removal check
├── contracts/           # Phase 1
│   └── viewdefinitions-missing.md   # Conformance contract for the 2 new ViewDefinition resources + the removal
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
├── patient.ViewDefinition.json           #   existing — unchanged
├── condition.ViewDefinition.json         #   existing (004) — unchanged
├── encounter.ViewDefinition.json         #   existing (004) — unchanged
├── observation.ViewDefinition.json       #   existing (004) — unchanged
├── practitioner.ViewDefinition.json      #   existing (004) — unchanged
├── organization.ViewDefinition.json      #   existing (004) — unchanged
├── location.ViewDefinition.json          #   existing (004) — unchanged
├── bundle.ViewDefinition.json            #   existing (004) — unchanged
├── procedure.ViewDefinition.json         #   existing (004) — unchanged
├── medicationrequest.ViewDefinition.json #   existing (004) — unchanged
├── servicerequest.ViewDefinition.json    #   existing (004) — unchanged
├── measure.ViewDefinition.json           # REMOVE — targets never-persisted Measure (004 R5, empty)
├── measurereport.ViewDefinition.json     # NEW — one row per persisted MeasureReport
└── composition.ViewDefinition.json       # NEW — one row per promoted Composition (metadata-only)

publish_views.py                          # UNCHANGED — already discovers every *.json view
fhir_common.py                            # UNCHANGED
process.py                                # UNCHANGED
config.example.json / config.json         # UNCHANGED — no new field

tests/
└── test_viewdefinition.py                # UNCHANGED — directory-driven shape suite already covers
                                          #   the two new files; no reference to the removed one

README.md                                 # UPDATE — view set now covers MeasureReport + Composition;
                                          #   no longer ships an empty Measure view
known-validation-issues.md                # UPDATE (if it mentions the Measure/empty view) — record
                                          #   the MeasureReport/Composition addition + Measure removal
```

**Structure Decision**: Single-project CLI, unchanged from features 001–004. This feature is
**data files only**: two JSON ViewDefinition files added to the auto-discovered `viewdefinitions/`
directory and one removed. No new module, entry point, config field, dependency, or test file. The
mechanism that publishes and materializes them already exists and is proven (002/003/004).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty. (The Principle VII demand-driven
> nuance and the empty-view removal are documented as reviewable notes in the Constitution Check,
> not violations.)
