---
description: "Task list for 004-remaining-viewdefinitions"
---

# Tasks: ViewDefinitions for the Remaining Resource Types

**Input**: Design documents from `/specs/004-remaining-viewdefinitions/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Unit tests ARE in scope for this feature — the spec/plan/contract/research (R8) all call for
a directory-driven `tests/test_viewdefinition.py` extension, so test tasks are included. The
authoritative conformance gate for each view is **Aidbox `PUT` + `$materialize` success** (e2e
quickstart), not `validator_cli.jar` (research.md R5).

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3 (maps to spec.md user stories)
- Every task includes an exact file path.

## Scope reminder

**Purely additive data + tests.** No production code changes: `publish_views.py`, `fhir_common.py`,
`process.py`, and `config*.json` are UNCHANGED (research.md R1). The feature is: author eleven
`viewdefinitions/*.ViewDefinition.json` files + generalize the unit test + update README + validate e2e.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the existing auto-discovery + shared file shape so the eleven new files drop in unchanged.

- [X] T001 Confirm auto-discovery and the shared file shape baseline: read `discover_viewdefinitions()` in `publish_views.py` and the existing `viewdefinitions/patient.ViewDefinition.json` to verify every `viewdefinitions/*.json` is globbed and that no code change is required (research.md R1). Record nothing to change; this is a read-only baseline check.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock down the shared skeleton every one of the eleven files reuses, so all author tasks are mechanical fill-ins.

**⚠️ CRITICAL**: Establishes the universal columns + provenance `where` reused by all of Phase 3.

- [X] T002 Establish the shared ViewDefinition skeleton convention used by all eleven files, per data-model.md §0 and `contracts/viewdefinitions-remaining.md`: the universal `id` column (`getResourceKey()`, type `string`), the `cms_measure` column (`meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()`, type `code`), and the top-level provenance `where` (`meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()`). Capture this skeleton (matching `viewdefinitions/patient.ViewDefinition.json`) as the copy/paste basis for T003–T013.

**Checkpoint**: Shared skeleton confirmed — the eleven author tasks can proceed in parallel.

---

## Phase 3: User Story 1 - Analyst queries flattened clinical and reference data across resource types (Priority: P1) 🎯 MVP

**Goal**: Eleven checked-in, conformant `ViewDefinition` files — one per resource type — each flattening
first-class resources of its type to one row per resource with the FR-002 default columns plus the
universal `id`/`cms_measure` and provenance `where`.

**Independent Test**: After publish/materialize against a server holding the processed fixtures, query
each new `sof.<type>_view` and confirm one row per persisted resource with the expected columns
populated (null where the source field is absent) — quickstart §3.

### Implementation for User Story 1

> Each task authors ONE complete, conformant file from the T002 skeleton + that type's column→FHIRPath
> table in data-model.md. All eleven are different files ⇒ fully parallel.

- [X] T003 [P] [US1] Author `viewdefinitions/condition.ViewDefinition.json` (id `condition`, name `condition_view`, resource `Condition`) with columns per data-model.md §1 (clinical_status, verification_status, category, code, code_system, code_display, subject, encounter, onset_date_time, recorded_date) + universal id/cms_measure + provenance `where`.
- [X] T004 [P] [US1] Author `viewdefinitions/encounter.ViewDefinition.json` (id `encounter`, name `encounter_view`, resource `Encounter`) with columns per data-model.md §2 (status, class, type, type_display, subject, period_start, period_end, service_provider, location) + universal columns + provenance `where`.
- [X] T005 [P] [US1] Author `viewdefinitions/observation.ViewDefinition.json` (id `observation`, name `observation_view`, resource `Observation`) with columns per data-model.md §3 (status, category, code, code_system, code_display, value_quantity, value_unit, value_code, value_string, effective_date_time, subject, encounter) + universal columns + provenance `where`.
- [X] T006 [P] [US1] Author `viewdefinitions/practitioner.ViewDefinition.json` (id `practitioner`, name `practitioner_view`, resource `Practitioner`) with columns per data-model.md §4 (npi, identifier, name_family, name_given, gender, active) + universal columns + provenance `where`.
- [X] T007 [P] [US1] Author `viewdefinitions/organization.ViewDefinition.json` (id `organization`, name `organization_view`, resource `Organization`) with columns per data-model.md §5 (identifier, name, type, active, address_city, address_state, address_postal_code) + universal columns + provenance `where`.
- [X] T008 [P] [US1] Author `viewdefinitions/location.ViewDefinition.json` (id `location`, name `location_view`, resource `Location`) with columns per data-model.md §6 (identifier, name, status, type, address_city, address_state, address_postal_code, managing_organization) + universal columns + provenance `where`.
- [X] T009 [P] [US1] Author `viewdefinitions/measure.ViewDefinition.json` (id `measure`, name `measure_view`, resource `Measure`) with columns per data-model.md §7 (url, version, name, title, status, scoring, identifier) + universal columns + provenance `where`. Add a `description` noting it is empty-until-loaded (zero rows until Measure resources exist; research.md R5).
- [X] T010 [P] [US1] Author `viewdefinitions/bundle.ViewDefinition.json` (id `bundle`, name `bundle_view`, resource `Bundle`) — metadata-only per data-model.md §8 / FR-011 (type, timestamp, identifier); NO nested-entry flattening + universal columns + provenance `where`. NOTE: the planned `entry_count` (`entry.count()`) column was dropped — the target Aidbox `$materialize` engine rejects the FHIRPath `count()` aggregate (HTTP 500 `geval`/`count`); server acceptance is the authoritative gate (research.md R5). Deviation recorded in data-model.md §8.
- [X] T011 [P] [US1] Author `viewdefinitions/procedure.ViewDefinition.json` (id `procedure`, name `procedure_view`, resource `Procedure`) with columns per data-model.md §9 (status, category, code, code_display, subject, encounter, performed_date_time) + universal columns + provenance `where`.
- [X] T012 [P] [US1] Author `viewdefinitions/medicationrequest.ViewDefinition.json` (id `medicationrequest`, name `medicationrequest_view`, resource `MedicationRequest`) with columns per data-model.md §10 (status, intent, medication_code, medication_display, medication_reference, subject, encounter, authored_on, requester) + universal columns + provenance `where`.
- [X] T013 [P] [US1] Author `viewdefinitions/servicerequest.ViewDefinition.json` (id `servicerequest`, name `servicerequest_view`, resource `ServiceRequest`) with columns per data-model.md §11 (status, intent, category, code, code_display, subject, encounter, authored_on, requester) + universal columns + provenance `where`.
- [X] T014 [US1] Extend `tests/test_viewdefinition.py` with a directory-driven shape suite over every `viewdefinitions/*.json` (research.md R8): assert valid JSON; required fields `resourceType == "ViewDefinition"`, `id`, `name`, `status`, `resource`, non-empty `select`; an `id` column using `getResourceKey()`; and no row-multiplying `forEach` in `select`. Keep the existing Patient-specific assertions. (Provenance/cms_measure assertions are added by US3 / T021.)
- [X] T015 [US1] Run `python -m unittest tests/test_viewdefinition.py` and confirm the generic shape suite passes for all twelve files (the eleven new + Patient).
- [ ] T016 [US1] E2E (quickstart §3): with the views published+materialized, query each new `sof.<type>_view` and confirm one row per persisted resource of that type with columns populated from the source (null where absent, never fabricated — SC-003/SC-004). Spot-check the worked examples (Condition `code=44054006`; Observation `value_quantity=9.2`, `value_unit=%`).

**Checkpoint**: Eleven conformant view files exist and pass shape assertions; once published they return correct flat rows. MVP deliverable complete.

---

## Phase 4: User Story 2 - Operator publishes and materializes all views in one step (Priority: P1)

**Goal**: The unchanged publish/materialize step auto-discovers and delivers all twelve views in one
invocation, with per-view outcome reporting, idempotent re-run, and per-view failure isolation.

**Independent Test**: Run the publish step once and confirm all twelve views published + materialized
with a per-view roll-up and exit 0; re-run yields no duplicates; one bad view fails alone.

### Implementation for User Story 2

> No new files — exercises the existing mechanism against the Phase 3 view files. T017→T018→T019 are sequential (same server state); T020 is independent.

- [X] T017 [US2] Dry-run discovery (quickstart §1): run `python publish_views.py --dry-run --verbose` and confirm all twelve ViewDefinition files are discovered, each planned as `PUT …/ViewDefinition/<id>` + `POST …/$materialize`, with no server contact.
- [ ] T018 [US2] Publish + materialize (quickstart §2 / FR-004, SC-001, SC-006): run `python publish_views.py --config config.json --verbose` and confirm a per-view block for each of the twelve and a roll-up `12 published, 12 materialized, 0 failed`, exit status 0, with the same invocation as the Patient-only run.
- [ ] T019 [US2] Idempotent re-run (quickstart §8 / FR-009, SC-006): re-run `python publish_views.py --config config.json` and confirm success again with exactly one of each `ViewDefinition/<id>` and `sof.<type>_view` (no duplicates).
- [ ] T020 [US2] Failure isolation (quickstart §9 / FR-010, SC-007): point `--viewdefinitions-dir` at a copy where one view has a deliberately non-conformant column, run, and confirm the server's reason is logged, that one view is reported failed (publish vs materialize distinguished), the run exits non-zero, and every other view is still published and materialized.

**Checkpoint**: Operator delivers all twelve views in one command, idempotently, with isolated failure — US1 + US2 both work.

---

## Phase 5: User Story 3 - Measure-scoped, provenance-scoped rows across every view (Priority: P2)

**Goal**: Every new view restricts to processor-persisted resources (provenance `where`) and exposes a
working `cms_measure` filter — the same scoping the Patient view has, now total across all types.

**Independent Test**: On a server also holding unrelated resources of these types, query each new view
and confirm only processor-persisted rows appear; filter by a CMS measure code and confirm only that
measure's resources are returned.

### Implementation for User Story 3

> T021 edits the same test file as T014 — sequence it after T014 (not parallel). T022/T023 are e2e checks.

- [X] T021 [US3] Extend the directory-driven suite in `tests/test_viewdefinition.py` to assert, for every `viewdefinitions/*.json`: the top-level provenance `where` filter (`…/processed-by` = `ecr-fhir-processor`) is present, and a single-valued `cms_measure` column reading `…/cms-measure` exists (research.md R8 / FR-005, FR-006). Re-run `python -m unittest tests/test_viewdefinition.py` to confirm all twelve pass.
- [ ] T022 [US3] E2E provenance scoping (quickstart §3 / SC-002): on a server also holding unrelated resources of these types, query each new view and confirm only processor-persisted rows (those bearing the `…/processed-by` tag) appear and zero unrelated rows.
- [ ] T023 [US3] E2E measure scoping (quickstart §4 / SC-005): filter each new view on `cms_measure` (e.g. `WHERE cms_measure = 'CMS122'`) and confirm only that measure's rows return, and that `SELECT DISTINCT cms_measure` yields known codes (e.g. CMS2/CMS122/CMS165) or the `unknown` sentinel.

**Checkpoint**: Provenance + measure scoping verified uniform across all twelve views — all stories functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, edge-case validation, and lint.

- [X] T024 [P] Update `README.md` "What it does" to note the materialized views now span twelve resource types (Patient + the eleven new), per plan.md Project Structure.
- [ ] T025 Validate the two special-case views e2e: `sof.measure_view` materialized but returns zero rows (quickstart §6, research.md R5 — success not failure), and `sof.bundle_view` returns container metadata only with no nested clinical columns (quickstart §7, FR-011).
- [ ] T026 Run the full quickstart.md e2e end-to-end, including the cross-view join (quickstart §5) to confirm views join on their reference columns (`subject`, `encounter`) within this project's data.
- [X] T027 [P] Run `ruff` lint and confirm clean — no production code was changed by this feature (Principle I).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (defines the shared skeleton).
- **User Story 1 (Phase 3, P1)**: Depends on Foundational. The MVP.
- **User Story 2 (Phase 4, P1)**: Depends on Foundational; requires the Phase 3 files to exist on disk to publish them.
- **User Story 3 (Phase 5, P2)**: Depends on Foundational; T021 depends on T014 (same test file); e2e tasks depend on US2 having published the views.
- **Polish (Phase 6)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Independent — authors the view files; independently testable via shape unit tests + per-view query.
- **US2 (P1)**: Consumes US1's files but exercises an unchanged mechanism; independently testable as a single publish run.
- **US3 (P2)**: Verifies scoping baked into US1's files; its only code touch (T021) follows T014 in the same file.

### Within Each User Story

- US1: T002 skeleton → T003–T013 author files (parallel) → T014 generic test → T015 run tests → T016 e2e query.
- US2: T017 dry-run → T018 publish → T019 re-run → T020 failure isolation.
- US3: T021 test assertions (after T014) → T022 provenance e2e → T023 measure e2e.

### Parallel Opportunities

- **T003–T013** (eleven view files) are all `[P]` — different files, no inter-dependencies — author them all concurrently. This is the bulk of the work.
- **T024** and **T027** in Polish are `[P]` (README vs lint).
- US1, US2, US3 can be staffed in priority order; US2/US3 e2e steps need US1's files published first.

---

## Parallel Example: User Story 1 (author all eleven views at once)

```bash
# All eleven ViewDefinition files are independent — launch together:
Task: "Author viewdefinitions/condition.ViewDefinition.json per data-model.md §1"
Task: "Author viewdefinitions/encounter.ViewDefinition.json per data-model.md §2"
Task: "Author viewdefinitions/observation.ViewDefinition.json per data-model.md §3"
Task: "Author viewdefinitions/practitioner.ViewDefinition.json per data-model.md §4"
Task: "Author viewdefinitions/organization.ViewDefinition.json per data-model.md §5"
Task: "Author viewdefinitions/location.ViewDefinition.json per data-model.md §6"
Task: "Author viewdefinitions/measure.ViewDefinition.json per data-model.md §7"
Task: "Author viewdefinitions/bundle.ViewDefinition.json per data-model.md §8"
Task: "Author viewdefinitions/procedure.ViewDefinition.json per data-model.md §9"
Task: "Author viewdefinitions/medicationrequest.ViewDefinition.json per data-model.md §10"
Task: "Author viewdefinitions/servicerequest.ViewDefinition.json per data-model.md §11"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup (T001) — confirm discovery, nothing to change.
2. Phase 2 Foundational (T002) — lock the shared skeleton.
3. Phase 3 US1 (T003–T016) — author the eleven files + generic shape test + per-view query.
4. **STOP and VALIDATE**: unit tests pass; each view returns correct flat rows.
5. This alone delivers the analytics payoff for every remaining resource type.

### Incremental Delivery

1. Setup + Foundational → skeleton ready.
2. US1 → eleven conformant views authored & shape-tested → **MVP**.
3. US2 → one-command publish/materialize, idempotent, failure-isolated.
4. US3 → provenance + measure scoping verified uniform across all views.
5. Polish → README, measure-empty/bundle-metadata validation, lint.

---

## Notes

- `[P]` = different files, no dependencies.
- The eleven author tasks (T003–T013) are the core deliverable; everything else is verification or docs.
- The unit test (`tests/test_viewdefinition.py`) is touched by T014 (US1) then T021 (US3) — same file, so sequential.
- Authoritative conformance gate = Aidbox `PUT` + `$materialize` success (e2e), not the HL7 validator (research.md R5).
- No production code changes — if any helper is touched, keep it stdlib-only (Principle I).
- Commit after each logical group; the Measure view (zero rows today) and Bundle view (metadata-only) are intentional, not bugs.
