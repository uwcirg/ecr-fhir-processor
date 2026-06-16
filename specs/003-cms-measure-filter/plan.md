# Implementation Plan: Filter Analytics by CMS Measure

**Branch**: `003-cms-measure-filter` | **Date**: 2026-06-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-cms-measure-filter/spec.md`; constitution
`.specify/memory/constitution.md` **v1.2.0**.

## Summary

Persist each processed resource's **CMS quality measure** as a dedicated, queryable
`meta.tag` (system `…/CodeSystem/cms-measure`, code `CMS165` / `CMS122` / `CMS2`, or the
sentinel `unknown`), derived purely from the input **filename** prefix; and surface that
measure as a `cms_measure` **column** on the existing Patient `ViewDefinition` so a DoH analyst
can filter the flattened analytics to one measure with a single predicate (and any resource
type by `_tag`). The CMS code is derived once from the filename the processor already carries,
so the change is small and additive.

**Reuse, not rebuild.** A new pure helper `cms_measure_from_filename()` is called **inside the
existing `stamp()`** (`process.py:164`), which already receives `source_filename` — no new
argument is threaded through the pipeline. A new tag-system constant `SYSTEM_CMS_MEASURE` is
appended to the existing `OWN_TAG_SYSTEMS` frozenset, so the established idempotent re-stamp
("drop only our own prior tags") replaces the cms-measure tag in place automatically — which is
exactly what makes the production "rename an `unknown` file and re-run to re-attribute" workflow
(US3) safe and duplicate-free. The CMS↔slug crosswalk becomes one authoritative constant
(`MEASURE_SLUG_BY_CMS`) the disagreement check and docs defer to (research R1, R4, R5).

**One tag system, positive `unknown`.** Rather than parse the CMS code out of the `source-file`
filename downstream (brittle), a first-class `(system, code)` tag is directly filterable — the
same mechanism the Patient view already uses for the `processed-by` provenance filter (002
FR-013). `unknown` is a positive sentinel in the *same* project-owned system (no published
`CodeSystem` resource — consistent with the existing provisional tag systems), so analysts can
positively list/count un-attributed resources (research R6).

**View: a column, not a filter.** The Patient view gains one `cms_measure` column reading the
tag; it adds **no** measure `where` clause and spawns **no** per-measure views — one view stays
DRY and the analyst filters to any measure with `WHERE cms_measure = 'CMS165'` (research R7,
constitution Principle VII).

## Technical Context

**Language/Version**: Python 3, standard library only — adds `re` (CMS-prefix match) to the
modules `process.py` already uses (`json`, `uuid`, `pathlib`, `logging`, `argparse`). No runtime
dependency added (Principle I).

**Primary Dependencies**: None at runtime. Dev/CI only: `ruff`, stdlib `unittest`, and the HL7
`validator_cli.jar` for the conformance gate (Principle III) — the added `meta.tag` is additive
and must introduce zero new validator errors.

**Storage**: Target Aidbox FHIR server (unchanged). The cms-measure tag rides on the resources
the processor already persists; the `cms_measure` column lives in the server-side materialized
Patient view. The ViewDefinition file lives in the repo.

**Testing**: (1) **Stdlib `unittest`** — new `tests/test_cms_measure.py` (derivation cases;
`stamp()` adds exactly one cms-measure tag; idempotent re-stamp keeps one; disagreement warns
only concrete-vs-different-concrete) plus an extension to `tests/test_viewdefinition.py` (the
`cms_measure` column is present and well-formed). (2) **FHIR conformance gate** — re-run the
feature-001 pipeline over `test/input/`; zero new errors. (3) **E2E against Aidbox** (quickstart)
— re-process, re-publish, query `cms_measure = 'CMS165'` returns only CMS165 patients.

**Target Platform**: Linux (developer + GitHub Actions CI).

**Project Type**: Single-project CLI utility. Changes are localized to `process.py` (stamping +
derivation + crosswalk + disagreement warning), one data column in
`viewdefinitions/patient.ViewDefinition.json`, and tests. **No new module** — the helper is
small and belongs beside `stamp()`; `fhir_common.py` is not involved (it has no stamping).

**Performance Goals**: Negligible — one regex match per file. No measurable processing impact.

**Constraints**: Zero runtime dependencies; tag is additive (preserves `meta.profile`/other
tags/clinical content → no new validator errors); idempotent re-stamp (exactly one cms-measure
tag, re-attribute-on-rename without duplication); filename is the single source of truth (parent
directory never consulted for the value); disagreements logged at WARNING, never silently
reconciled (Principle V); the view never fabricates (absent tag → null column).

**Scale/Scope**: Three constitution-named measures (`CMS2`/`CMS122`/`CMS165`) plus an open-ended
well-formed `CMS<n>` form and the `unknown` sentinel. Patient is the only view that gains the
column (demand-driven, Principle VII); all persisted resource types carry the tag for `_tag`
filtering.

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase + constitution; the
decisions are in [research.md](./research.md) (R1–R7). No `NEEDS CLARIFICATION` remains. The
three design questions the user raised in `/speckit-specify` are answered in the spec's
Clarifications and locked here: dedicated tag (yes), filename as source of truth (yes), and a
positive `unknown` sentinel in the project system (HL7 DataAbsentReason noted as the alternative).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | Adds only stdlib `re`; no package; helper lives in `process.py` beside `stamp()` | ✅ PASS |
| II. FHIR Profile Conformance | The cms-measure `meta.tag` is **additive** — preserves `meta.profile`, other tags, all clinical content; an unknown-CodeSystem tag yields at most validator **warnings**, never errors. Conformance gate (validator pipeline) MUST be re-run (Principle III) | ✅ PASS |
| III. Dual-Gate Validation Testing | Pure logic covered by new `tests/test_cms_measure.py` + `test_viewdefinition.py` extension; gate 1 (`validator_cli.jar`) re-run over fixtures for zero new errors; gate 2 = Aidbox accepts the updated ViewDefinition `PUT` + `$materialize` (quickstart) | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | **Directly on-point**: the tag/crosswalk use exactly the Principle-IV measures (`CMS2`/`CMS122`/`CMS165` ↔ slugs). CMS2 has no fixtures yet but is in scope; its `CMS2_*` files attribute correctly when they arrive | ✅ PASS |
| V. Data Integrity & Defensive Processing | `unknown` is an explicit sentinel, not fabrication (we don't invent a measure); directory/filename disagreement logged at WARNING, never silently reconciled (FR-007/SC-006); idempotent re-stamp keeps exactly one tag | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | Unchanged — the tag rides on the first-class resources already persisted; no granularity or promotion change | ✅ PASS |
| VII. Analytics View Definitions & Materialization | Patient view gains one column; **no** new views, **no** per-measure views (demand-driven); the publish/materialize mechanism is reused as-is | ✅ PASS |
| Deployment & Security | No config/secret change; base URL/creds untouched; `config.example.json` unchanged | ✅ PASS |
| Development Workflow | Change stays in `process.py` + one ViewDefinition file + tests — no new module (Single-File Simplicity respected); **README MUST be updated** (new tag system + `cms_measure` column + the filename CMS convention) | ✅ PASS (README update required) |

**Result**: No violations. No Complexity Tracking entries required. The plan stays within
constitution v1.2.0 and advances Principle IV's measure-awareness into persisted, queryable
metadata.

## Project Structure

### Documentation (this feature)

```text
specs/003-cms-measure-filter/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R7 decisions (derivation, idempotent tag, unknown, view column)
├── data-model.md        # Phase 1 — CMS code, cms-measure tag, slug crosswalk, view column
├── quickstart.md        # Phase 1 — unit → conformance → e2e measure-filter validation guide
├── contracts/           # Phase 1
│   ├── cms-measure-tag.md            # The persisted meta.tag contract (system/code/breadth/idempotency)
│   └── viewdefinition-cms-column.md  # The cms_measure column addendum to the 002 Patient view
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
process.py                       # MODIFY — add:
                                 #   • SYSTEM_CMS_MEASURE constant; add it to OWN_TAG_SYSTEMS
                                 #   • cms_measure_from_filename() pure helper (stdlib re)
                                 #   • MEASURE_SLUG_BY_CMS crosswalk (single source of truth, FR-010)
                                 #   • stamp(): append the cms-measure tag (derived from source_filename)
                                 #   • discover_inputs(): directory/filename disagreement WARNING (FR-007)
viewdefinitions/
└── patient.ViewDefinition.json # MODIFY — append the cms_measure column (read the tag's code.first())

tests/
├── test_cms_measure.py         # NEW — derivation cases, stamp adds/idempotency, disagreement warning
└── test_viewdefinition.py      # MODIFY — assert the cms_measure column is present & well-formed

README.md                        # MODIFY — document the cms-measure tag, the CMS filename convention,
                                 #   the unknown sentinel, and the patient_view cms_measure column
```

**Structure Decision**: Single-project CLI, consistent with features 001/002. All processing
logic stays in `process.py` (no new module — the helper is a few lines beside `stamp()`, well
under the Single-File Simplicity threshold the constitution names). `fhir_common.py` is
untouched (it holds the shared FHIR client/config/outcome primitives, not stamping). The view
change is data-only (one column). No new directories.

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
