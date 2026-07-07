---
description: "Task list for 006-missing-viewdefinitions"
---

# Tasks: ViewDefinitions for the Missing Persisted Resource Types

**Input**: Design documents from `/specs/006-missing-viewdefinitions/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: The existing directory-driven `tests/test_viewdefinition.py` (built in 004, research R8)
already asserts the invariant shape of **every** `viewdefinitions/*.json`, so the two new files are
covered with **no test edit** and the removed file simply drops out of iteration (research R1/R6).
No new test file is authored. The authoritative conformance gate for each view is **Aidbox `PUT` +
`$materialize` success** (e2e quickstart), not `validator_cli.jar` (research R6).

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3 (maps to spec.md user stories)
- Every task includes an exact file path.

## Scope reminder

**Data files only — add two, remove one. No production code change.** `publish_views.py`,
`fhir_common.py`, `process.py`, `config*.json`, and `tests/test_viewdefinition.py` are UNCHANGED
(research R1). The feature is: author `measurereport.ViewDefinition.json` +
`composition.ViewDefinition.json`, delete `measure.ViewDefinition.json`, update docs, validate e2e.
After it, the set of view target types equals the set of resource types the processor persists
first-class (closure invariant, SC-004).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing auto-discovery + test coverage so the two new files drop in and the
removed one drops out with no code/test change.

- [ ] T001 Confirm auto-discovery baseline (read-only): read `discover_viewdefinitions()` in `publish_views.py` and an existing view (`viewdefinitions/observation.ViewDefinition.json`) to verify every `viewdefinitions/*.json` is globbed and PUT + `$materialize`d with per-view isolation — no code change required (research R1). Record nothing to change.
- [ ] T002 Confirm test coverage baseline (read-only): read `tests/test_viewdefinition.py` and verify the shape suite iterates `VIEWDEFINITIONS_DIR.glob("*.json")` (directory-driven), so the two new files are asserted automatically and the removed file drops out — no test edit needed. Verify no test references the `measure` view by name, and that `tests/test_discovery.py`'s `len(files) == 18` counts eCR **input** fixtures (via `process.discover_inputs`), not views, so it is unaffected (research R1/R6).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock the shared skeleton both new files reuse, so authoring is a mechanical fill-in.

**⚠️ CRITICAL**: Establishes the universal columns + provenance `where` reused by US1 and US2.

- [ ] T003 Establish the shared ViewDefinition skeleton convention both new files reuse, per data-model.md "Shared, unchanged conventions" and `contracts/viewdefinitions-missing.md` C1: the universal `id` column (`getResourceKey()`, type `string`), the `cms_measure` column (`meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()`, type `code`), the top-level provenance `where` (`meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()`), and reference columns via `<ref>.getReferenceKey()` (never raw `.reference` — null under Aidbox normalization, research R4). Use `viewdefinitions/observation.ViewDefinition.json` as the copy/paste basis for T004 and T007.

**Checkpoint**: Shared skeleton confirmed — the two author tasks (T004, T007) can proceed in parallel.

---

## Phase 3: User Story 1 - Analyst queries measure-result data as a flat table (Priority: P1) 🎯 MVP

**Goal**: A checked-in, conformant `measurereport.ViewDefinition.json` flattening each persisted
first-class `MeasureReport` to one row, exposing the measure canonical, status/type, subject/reporter
keys, reporting period, named population counts, measure score, improvement notation, and the
`cms_measure` attribution — the resource that ties each processed eCR to its CMS-measure outcome, and
today unviewed.

**Independent Test**: After publish/materialize against a server holding the processed fixtures, query
`sof.measurereport_view` and confirm one row per persisted MeasureReport with the expected columns
populated (null where the source field is absent) and measure-scoped filtering working — quickstart
Steps 3 & 5.

### Implementation for User Story 1

- [ ] T004 [P] [US1] Author `viewdefinitions/measurereport.ViewDefinition.json` (id `measurereport`, name `measurereport_view`, status `active`, resource `MeasureReport`) with columns exactly per data-model.md Entity 1: universal `id`; `measure` (string), `status` (code), `type` (code); `subject`/`reporter` via `getReferenceKey()`; `period_start`/`period_end` (dateTime); `improvement_notation` (`improvementNotation.coding.first().code`, code); `measure_score` (`group.first().measureScore.value`, decimal); the named population-count columns `initial_population`/`denominator`/`denominator_exclusion`/`denominator_exception`/`numerator`/`numerator_exclusion` each `group.first().population.where(code.coding.where(code='<pop>').exists()).count.first()` (integer); plus `cms_measure` and the provenance `where`. **Gotcha (from 004 T010):** the Aidbox `$materialize` engine rejects the FHIRPath aggregate `count()`. These columns use `.count` (navigation of the `MeasureReport.group.population.count` element) + `.first()`, NOT the `count()` aggregate — this is intended and distinct; T006's `$materialize` is the authoritative check that the server accepts these expressions.
- [ ] T005 [US1] Run `python3 -m unittest tests.test_viewdefinition -v` and confirm the directory-driven shape suite now covers the new file and passes (valid JSON; `resourceType`/`id`/`name`/`status`/`resource`/non-empty `select`; `getResourceKey()` id column; provenance `where`; single-valued `cms_measure`; no row-multiplying `forEach`). No test edit.
- [ ] T006 [US1] E2E (quickstart Steps 2, 3, 5 / SC-001, SC-005, SC-006): publish + materialize, then query `sof.measurereport_view` and confirm — `$materialize` accepted (authoritative gate; watch for the `count()` 500 gotcha); one row per persisted MeasureReport and zero rows for unrelated ones; population columns reflect the source `group.population.count`; `measure_score` and any absent population are null (never fabricated, FR-010); `subject` equals the matching `patient_view.id`; and `WHERE cms_measure = 'CMS165'` returns only that measure's rows.

**Checkpoint**: The MeasureReport view exists, passes shape assertions, and returns correct flat rows. MVP deliverable complete.

---

## Phase 4: User Story 2 - Analyst accounts for the source clinical documents (Priority: P2)

**Goal**: A checked-in, conformant `composition.ViewDefinition.json` flattening each promoted
first-class `Composition` to one row of **document-level metadata only** (status, type, category,
subject/encounter/author/custodian keys, date, title) — no `section`/nested clinical content — so
analysts can count and attribute source eICR documents.

**Independent Test**: After publish/materialize, query `sof.composition_view` and confirm one row per
promoted Composition with metadata columns populated, reference keys that join to the other views, and
no section/clinical column — quickstart Step 4.

### Implementation for User Story 2

- [ ] T007 [P] [US2] Author `viewdefinitions/composition.ViewDefinition.json` (id `composition`, name `composition_view`, status `active`, resource `Composition`) with columns exactly per data-model.md Entity 2: universal `id`; `status` (code); `type_code`/`type_system`/`type_display` from `type.coding.first()`; `category` (`category.first().coding.first().code`, code); `subject`/`encounter`/`custodian` via `getReferenceKey()`; `author` via `author.first().getReferenceKey()` (0..* → `.first()` reducer); `date` (dateTime); `title` (string); plus `cms_measure` and the provenance `where`. Metadata-only — MUST NOT include any `section`/nested-clinical column (FR-005).
- [ ] T008 [US2] Run `python3 -m unittest tests.test_viewdefinition -v` and confirm the shape suite passes with the composition file included (same invariant assertions as T005). No test edit.
- [ ] T009 [US2] E2E (quickstart Steps 4, 5 / SC-002, SC-005): publish + materialize, then query `sof.composition_view` and confirm — `$materialize` accepted; one row per promoted Composition (in-population scenarios), provenance-scoped; `type_code = 55751-2` (Public Health Case Report); `subject`/`encounter`/`author`/`custodian` are populated reference keys that join to `patient_view`/`encounter_view`/`practitioner_view`/`organization_view` (not null, not `Type/`-prefixed); no `section` column exists; and `WHERE cms_measure = 'CMS165'` returns only that measure's rows.

**Checkpoint**: The Composition metadata view exists, passes shape assertions, and returns correct flat rows — US1 + US2 both deliverable.

---

## Phase 5: User Story 3 - Every persisted first-class resource type has exactly one view (Priority: P2)

**Goal**: Remove the mis-targeted `Measure` view and confirm the closure invariant — the set of view
target types equals the set of resource types the processor persists first-class: no persisted type
without a view, no view without a persisted type.

**Independent Test**: List the target `resource` of every checked-in view and confirm it equals the set
of types the processor persists first-class (Measure absent; MeasureReport + Composition present) —
quickstart Step 6.

### Implementation for User Story 3

- [ ] T010 [US3] Delete `viewdefinitions/measure.ViewDefinition.json` (`git rm viewdefinitions/measure.ViewDefinition.json`) — it targets `Measure`, a type this pipeline never persists, so it is permanently empty (research R5, FR-003, SC-003).
- [ ] T011 [US3] Run the full unit suite `python3 -m unittest -v` and confirm still green after the removal: the directory-driven `tests/test_viewdefinition.py` no longer iterates the deleted file and no test referenced it; `tests/test_discovery.py` (input-file count) is unaffected.
- [ ] T012 [US3] Closure check (quickstart Step 6 / SC-004): run `python3 -c "import json,glob; print(sorted(json.load(open(f))['resource'] for f in glob.glob('viewdefinitions/*.json')))"` and confirm the printed set equals the processor's first-class persisted types — `Bundle, Composition, Condition, Encounter, Location, MeasureReport, MedicationRequest, Observation, Organization, Patient, Practitioner, Procedure, ServiceRequest` — with `Measure` absent and `MeasureReport`/`Composition` present.
- [ ] T013 [US3] E2E (quickstart Steps 2, 6): run `python3 publish_views.py --config config.json` and confirm the per-view roll-up publishes + materializes `measurereport` and `composition`, emits **no** `measure` view line, and exits 0. Note that a pre-existing server-side `sof.measure_view` is orphaned (never re-published) and its removal is an operator action outside this file-only feature (contract C5).

**Checkpoint**: The view set contains no view that can never return a row; persisted-type ↔ view correspondence holds — all stories functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, idempotency/lint validation, full e2e acceptance.

- [ ] T014 [P] Update `README.md` "What it does" to note the materialized views now cover MeasureReport and Composition and no longer ship an empty Measure view, per plan.md Project Structure.
- [ ] T015 [P] Update `known-validation-issues.md` if it references the `Measure`/empty view or the 004 "empty-until-loaded" note — reconcile it with the removal (Measure view retired; MeasureReport + Composition added). If it makes no such reference, record that no change is needed.
- [ ] T016 Idempotent re-run (quickstart Step 7 / C6): re-run `python3 publish_views.py --config config.json` and confirm success again with exactly one `ViewDefinition/measurereport`, one `ViewDefinition/composition`, and their single `sof.*_view` each (no duplicates), exit 0.
- [ ] T017 [P] Run `ruff` lint and confirm clean — no production code was changed by this feature (Principle I).
- [ ] T018 Run the full `quickstart.md` end-to-end (Steps 0–7) as final acceptance, confirming all its success checkboxes.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately (read-only confirmations).
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS US1/US2 (defines the shared skeleton).
- **User Story 1 (Phase 3, P1)**: Depends on Foundational. The MVP (MeasureReport view).
- **User Story 2 (Phase 4, P2)**: Depends on Foundational; independent of US1 (different file).
- **User Story 3 (Phase 5, P2)**: Independent of US1/US2 (the removal + closure); its closure check (T012) and e2e (T013) are most meaningful once the two new files exist, but the removal itself does not depend on them.
- **Polish (Phase 6)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Independent — authors the MeasureReport file; testable via the shape suite + a per-view query.
- **US2 (P2)**: Independent — authors the Composition file; testable via the shape suite + a per-view query. No dependency on US1.
- **US3 (P2)**: Independent — removes the Measure view and asserts the closure invariant. The closure set in T012 assumes US1/US2 files are present; sequence T012/T013 after T004 & T007 for a complete check.

### Within Each User Story

- US1: T004 author → T005 unit suite → T006 e2e query.
- US2: T007 author → T008 unit suite → T009 e2e query.
- US3: T010 remove → T011 unit suite → T012 closure check → T013 e2e publish.

### Parallel Opportunities

- **T004 (MeasureReport)** and **T007 (Composition)** are different files with no interdependency — author them concurrently (the two core deliverables).
- **T014**, **T015**, and **T017** in Polish are `[P]` (README vs known-issues vs lint — different files/actions).
- US1, US2, US3 can be staffed in parallel by different people once Foundational is done.

---

## Parallel Example: author both new views at once

```bash
# The two new ViewDefinition files are independent — launch together:
Task: "Author viewdefinitions/measurereport.ViewDefinition.json per data-model.md Entity 1"
Task: "Author viewdefinitions/composition.ViewDefinition.json per data-model.md Entity 2"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup (T001–T002) — confirm discovery + test coverage, nothing to change.
2. Phase 2 Foundational (T003) — lock the shared skeleton.
3. Phase 3 US1 (T004–T006) — author the MeasureReport view + shape test + per-view query.
4. **STOP and VALIDATE**: shape suite passes; `sof.measurereport_view` returns correct flat rows.
5. This alone closes the most measure-relevant gap — the previously unviewed MeasureReport.

### Incremental Delivery

1. Setup + Foundational → skeleton ready.
2. US1 → MeasureReport view authored & shape-tested → **MVP**.
3. US2 → Composition metadata view authored & shape-tested.
4. US3 → remove the empty Measure view; verify the closure invariant.
5. Polish → README + known-issues docs, idempotent re-run, lint, full quickstart.

---

## Notes

- `[P]` = different files, no dependencies.
- The two author tasks (T004, T007) are the core deliverable; everything else is verification or docs.
- **No test file is edited** — the directory-driven `tests/test_viewdefinition.py` from 004 already
  covers new files and ignores removed ones (research R1/R6).
- **`count()` gotcha (004 T010):** Aidbox `$materialize` rejects the FHIRPath aggregate `count()`. The
  MeasureReport population columns use `.count` element navigation (`population.where(...).count.first()`),
  which is distinct and expected to be accepted — T006's `$materialize` is the authoritative check.
- Authoritative conformance gate = Aidbox `PUT` + `$materialize` success (e2e), not the HL7 validator (research R6).
- No production code changes — if any helper is touched, keep it stdlib-only (Principle I).
- Removing the Measure view is intentional (it never returned a row), not a regression — see plan.md Constitution Check.
- Commit after each logical group.
