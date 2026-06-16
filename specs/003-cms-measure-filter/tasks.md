---
description: "Task list for Filter Analytics by CMS Measure"
---

# Tasks: Filter Analytics by CMS Measure

**Input**: Design documents from `specs/003-cms-measure-filter/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — required by constitution Principle III (dual-gate validation + targeted
stdlib `unittest`) and the plan's Testing section. Unit tests are written before the
implementation they cover and must FAIL first.

**Organization**: Tasks are grouped by user story. This is a small, additive change localized
to `process.py` (stamping + derivation + crosswalk + disagreement warning), one column in
`viewdefinitions/patient.ViewDefinition.json`, and tests — so several tasks touch the same
`process.py` file and are therefore **sequential** (not `[P]`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (maps to spec.md user stories)
- Exact file paths are included in each task

## Path Conventions

Single-project CLI at repo root: `process.py`, `viewdefinitions/`, `tests/`, `README.md`
(per plan.md Structure Decision). No `src/` layout.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm a clean, green baseline before additive changes.

- [X] T001 Establish baseline: run `python -m unittest discover -s tests -v` and `ruff check .` from repo root; confirm all existing tests pass and lint is clean before modifying `process.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the shared constants the stamping (US2/US3) and the view column (US1) both
depend on. Pure additions — no behavior change yet.

**⚠️ CRITICAL**: The `cms-measure` tag-system URL defined here is the single contract the US1
view column, the US2 stamp, and the US3 re-attribution all reference; complete before story work.

- [X] T002 Add `SYSTEM_CMS_MEASURE = f"{PROVENANCE_BASE}/cms-measure"` beside the other `SYSTEM_*` constants (process.py ~line 49) and add `SYSTEM_CMS_MEASURE` to the `OWN_TAG_SYSTEMS` frozenset (process.py ~line 52) so idempotent re-stamp replaces it in place (research R5, contract C-5).
- [X] T003 Add the `MEASURE_SLUG_BY_CMS = {"CMS2": "depression-screening", "CMS122": "poor-diabetic-control", "CMS165": "controllable-bp"}` crosswalk constant (and a derived inverse map) beside the canonical constants in process.py — the single source of truth for CMS↔slug (FR-010, data-model §3).

**Checkpoint**: Constants exist and import cleanly (`python -c "import process"`); no behavior change yet.

---

## Phase 3: User Story 1 - Analyst filters analytics to a single CMS measure (Priority: P1) 🎯 MVP

**Goal**: Surface the CMS measure as a `cms_measure` column on the Patient `ViewDefinition` so an
analyst can filter the flattened view to one measure with a single predicate.

**Independent Test**: `python -m unittest tests.test_viewdefinition -v` confirms the column is
present and well-formed; publishing the view to Aidbox succeeds (valid FHIRPath, yields null
where no tag) even before any resource carries the tag.

### Tests for User Story 1 ⚠️ (write first, must FAIL before T006)

- [X] T004 [P] [US1] Extend `tests/test_viewdefinition.py`: assert `select[0].column[]` contains a `cms_measure` column whose `path` references the `…/CodeSystem/cms-measure` system and ends in `.code.first()`, with `type` `code` (contract VC-1, VC-2).

### Implementation for User Story 1

- [X] T005 [US1] Append the `cms_measure` column to `viewdefinitions/patient.ViewDefinition.json` `select[0].column[]`: `{ "name": "cms_measure", "path": "meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()", "type": "code" }` — no measure `where` filter, keep the existing provenance `where` (contract viewdefinition-cms-column.md, research R7).

**Checkpoint**: T004 passes; the Patient view JSON is valid and carries the column.

---

## Phase 4: User Story 2 - Processor attributes each persisted resource to its CMS measure (Priority: P1)

**Goal**: Derive the CMS measure from the input filename and stamp it as a dedicated, idempotent
`meta.tag` on every resource the processor persists (alongside `source-file`).

**Independent Test**: Process a `CMS122_*` file and inspect a persisted resource — `meta.tag`
contains `{system: …/cms-measure, code: "CMS122"}`; a non-conforming filename yields code
`unknown`. `python -m unittest tests.test_cms_measure -v` is green.

### Tests for User Story 2 ⚠️ (write first, must FAIL before T012–T014)

- [X] T006 [P] [US2] Create `tests/test_cms_measure.py` with derivation cases for `cms_measure_from_filename`: `CMS165_bulk_*.json`→`CMS165`, `CMS2_*.json`→`CMS2`, `CMS122_*.json`→`CMS122`, `cms165_x.json`→`CMS165`, `CMS165.json`→`CMS165`, `CMSX_x.json`→`unknown`, `CMSReport_x.json`→`unknown`, `patient_export.json`→`unknown` (data-model §1, contract C-2).
- [X] T007 [US2] Add to `tests/test_cms_measure.py`: `stamp()` adds exactly one cms-measure tag with the derived code; calling `stamp()` twice leaves exactly one (idempotent re-stamp); pre-existing other-system tags and `meta.profile` survive (INV-CMS-2/3, contract C-5/C-6).
- [X] T008 [US2] Add to `tests/test_cms_measure.py`: the directory/filename disagreement rule warns only when the filename code is concrete AND the directory slug maps to a different concrete code; filename `unknown` produces no warning (FR-007, data-model §4).

### Implementation for User Story 2

- [X] T009 [US2] Add the pure helper `cms_measure_from_filename(filename: str) -> str` in process.py near `stamp()` (~line 160): match `^CMS\d+` case-insensitively against the basename via stdlib `re`, return uppercased `CMS<digits>` or `"unknown"` (FR-001/006, research R2). Add `import re` if absent.
- [X] T010 [US2] In `stamp()` (process.py:164), append a `cms-measure` tag derived from `source_filename` via T009, with `code` = the CMS code and `display` = `MEASURE_SLUG_BY_CMS.get(code, "unknown measure")` (FR-002/003/004/006, contract C-1..C-7). Depends on T002, T003, T009.
- [X] T011 [US2] In `discover_inputs()` (process.py:443), log one WARNING per file when the filename code is concrete and the inverse-crosswalk of the directory slug is a different concrete code: `logger.warning("CMS measure mismatch for %s: filename=%s directory=%s (%s); using filename.", ...)` (FR-007/SC-006, data-model §4). Depends on T003, T009.

**Checkpoint**: T006–T008 pass; processing a `CMS122_*` fixture stamps `code: "CMS122"` on each persisted resource; mismatched placement warns.

---

## Phase 5: User Story 3 - Operator re-attributes "unknown" resources later (Priority: P2)

**Goal**: Renaming a non-conforming file to the CMS convention and re-running re-attributes the
same resources in place — no duplicate tag, no duplicate resource. This falls out of US2's
idempotent stamping (`SYSTEM_CMS_MEASURE` in `OWN_TAG_SYSTEMS`); this phase proves it.

**Independent Test**: quickstart §E — process a prefix-less file (lands `unknown`), rename to
`CMS165_*`, re-process; the same resource ids now carry `CMS165`, one tag, no duplicate.

### Tests for User Story 3 ⚠️

- [X] T012 [P] [US3] Add a re-attribution test to `tests/test_cms_measure.py`: `stamp()` a resource with an `unknown`-yielding filename, then `stamp()` the same resource dict with a `CMS2_*` filename; assert exactly one cms-measure tag now coded `CMS2` and no duplicate (SC-004, contract C-5). Depends on T010.

### Implementation for User Story 3

- [X] T013 [US3] Verify end-to-end against a scratch input dir (quickstart §E): copy a `CMS165_*` fixture to `/tmp/export_noprefix.json`, `python process.py --input-dir /tmp` (resources tagged `unknown`), rename to `/tmp/CMS165_reattributed.json`, re-run; confirm same resource ids re-attribute to `CMS165` with no duplicate resource or tag. If a gap surfaces, fix in process.py (otherwise no code change — mechanism delivered by T002/T010).

**Checkpoint**: Re-attribution works in place; `unknown` count drops on re-run.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, conformance gate, lint, and the cross-story end-to-end measure filter.

- [X] T014 [P] Update `README.md`: document the `…/CodeSystem/cms-measure` tag system, the `CMS<n>` filename convention, the `unknown` sentinel (with the HL7 DataAbsentReason alternative noted), and the new `patient_view.cms_measure` column (constitution README-as-living-documentation rule).
- [X] T015 FHIR conformance gate (Principle III): run `python process.py` over `test/input/`, then `java -jar validator_cli.jar output/**/*.json -version 4.0.1 -ig hl7.fhir.us.ecr#$ECR_IG_VERSION -ig hl7.fhir.us.core#$US_CORE_VERSION -ig hl7.fhir.us.davinci-deqm#$DEQM_VERSION`; confirm zero new errors from the added tag (contract C-6), applying `known-validation-issues.md` filtering.
- [X] T016 Run the full unit suite and lint: `python -m unittest discover -s tests -v` and `ruff check .`; confirm green.
- [ ] T017 End-to-end measure filter (quickstart §D, against Aidbox): `python process.py` then `python publish_views.py`; query the materialized `patient_view` with `WHERE cms_measure = 'CMS165'` and confirm only CMS165-sourced patients return (and a `_tag` Condition query mirrors it) — SC-001, SC-003.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: depends on Setup — **blocks US2/US3 stamping and the US1 column's system URL**.
- **User Stories (Phase 3–5)**: depend on Foundational.
  - US1 (view column) is independently unit-testable and does not need the US2 helper.
  - US2 (stamping) depends on the T009 helper + T002/T003 constants.
  - US3 (re-attribution) depends on US2's idempotent stamp (T010) for its test.
- **Polish (Phase 6)**: T014/T016 anytime after their targets exist; T015 and T017 need US1+US2 landed (they validate the combined data + view).

### User Story Dependencies

- **US1 (P1)**: needs Foundational only (uses the system URL string). Independently testable.
- **US2 (P1)**: needs Foundational (T002/T003) + its own helper (T009). Independently testable.
- **US3 (P2)**: needs US2's stamping mechanism (T010). Test-and-verify; no new production code expected.

### Within Each Story

- Tests are written first and must FAIL before the implementation tasks that satisfy them.
- In US2: helper (T009) → `stamp()` change (T010) and `discover_inputs()` warning (T011).

### Parallel Opportunities

- T004 (test_viewdefinition.py) is `[P]` vs. all process.py work — different file.
- T006 (creating test_cms_measure.py) is `[P]` vs. process.py work; T007/T008/T012 add to the
  same test file and are therefore sequential with each other.
- T014 (README.md) is `[P]` vs. everything else.
- Most process.py tasks (T002, T003, T009, T010, T011) touch the **same file** → sequential.

---

## Parallel Example: kickoff after Foundational

```bash
# These touch different files and can proceed together:
Task: "T004 [US1] extend tests/test_viewdefinition.py with the cms_measure column assertion"
Task: "T006 [US2] create tests/test_cms_measure.py with derivation cases"
Task: "T014 update README.md for the cms-measure tag + column"
# Meanwhile the process.py edits (T009 → T010 → T011) proceed in sequence on one file.
```

---

## Implementation Strategy

### MVP scope

Per the spec, **US1 and US2 together are the MVP** — US1 (the filterable column) is only
demonstrable end-to-end once US2 stamps the data it reads. Deliver: Phase 1 → Phase 2 → Phase 3
(US1) → Phase 4 (US2) → validate with T017. US1's column is independently *unit*-testable
before US2, but the user-facing "filter by measure" result needs both.

### Incremental delivery

1. Setup + Foundational → constants in place.
2. US1 (view column) → unit-test green; view publishes. 
3. US2 (stamping) → resources carry the tag; conformance gate (T015) green.
4. Validate combined: T017 measure-filter query returns only the selected measure (MVP demo).
5. US3 (re-attribution) → prove rename-and-re-run flips `unknown`→`CMS<n>` in place.
6. Polish: README (T014), full suite + lint (T016).

---

## Notes

- `[P]` = different files, no incomplete dependencies; same-file `process.py` tasks are sequential.
- The change is intentionally additive and small (research R1): one helper, two constants, one
  `stamp()` line, one `discover_inputs()` warning, one view column — no new module, no new
  dependency, no config change.
- Verify each unit test FAILS before its implementation task; commit after each task or logical group.
- The cms-measure tag is additive to `meta.tag`, so it must introduce zero new HL7-validator
  errors (T015 enforces this).
