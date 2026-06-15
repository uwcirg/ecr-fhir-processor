---
description: "Task list for Patient ViewDefinition + Publish/Materialize"
---

# Tasks: Patient ViewDefinition + Publish/Materialize

**Input**: Design documents from `/specs/002-patient-viewdefinition/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Test tasks ARE included — the plan's Testing section explicitly requests targeted
stdlib `unittest` for pure logic plus an end-to-end quickstart validation, and the repo already
follows a `tests/test_*.py` `unittest` convention.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are included in each description

## Path Conventions

Single-project CLI utility (per plan.md "Project Structure"). New code at repo root:
`fhir_common.py`, `publish_views.py`, `viewdefinitions/`; tests in `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding for the new artifacts

- [ ] T001 Create the `viewdefinitions/` directory at repository root (checked-in ViewDefinition home; discovered generically by the publish step — FR-011)
- [ ] T002 [P] Add a `.gitkeep` or confirm `viewdefinitions/` is tracked, and verify `.ruff.toml` lint config covers the new root-level `fhir_common.py` / `publish_views.py` (no config change expected — confirm only)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extract the shared primitives that the new entry point depends on, without changing `process.py` behavior (research.md R1). This BLOCKS User Story 2.

**⚠️ CRITICAL**: `publish_views.py` (US2) imports from `fhir_common.py`; this phase must complete before US2 implementation begins.

- [ ] T003 Create `fhir_common.py` at repo root by moving these primitives out of `process.py`: `FhirClient` (OAuth2 client-credentials, token caching, single 401-refresh retry, `aidbox-validation-skip` header, generic `request(method, url, body)` + `submit_put`), `RunConfig`, `load_config`, `validate_config`, `setup_logging`, `FileOutcome`, `RunSummary` (incl. `exit_code()`), and supporting constants/exceptions (`REQUIRED_SERVER_FIELDS`, `DEFAULT_PATHS`, `PLACEHOLDER_PREFIX`, `SubmissionError`)
- [ ] T004 Update `process.py` to import the moved primitives from `fhir_common.py` (pure move + import; no behavior change) and remove the now-duplicated definitions
- [ ] T005 Verify `process.py` behavior is unchanged: run the existing test suite (`python -m unittest discover tests`) and re-run the feature-001 validation pipeline per `specs/001-mvp-fhir-processor/quickstart.md`; all previously-passing checks still pass
- [ ] T006 [P] Run `ruff check fhir_common.py process.py` and resolve any lint findings introduced by the extraction

**Checkpoint**: Shared module exists, `process.py` still green — User Story 2 can begin.

---

## Phase 3: User Story 1 - Analyst queries flattened Patient demographics (Priority: P1) 🎯 MVP

**Goal**: Deliver the checked-in, conformant Patient `ViewDefinition` that flattens first-class Patient resources to one row per patient with the default DoH demographic columns — the analytics deliverable.

**Independent Test**: With the publish step available, publish + materialize the view against a server holding N Patients and confirm `SELECT count(*) FROM sof.patient_view` returns N with demographic columns populated from the source (null where absent). The artifact itself is independently verifiable via the JSON/required-field unit test (T008) without a server.

### Tests for User Story 1

- [ ] T007 [P] [US1] Add `tests/test_viewdefinition.py` with a test asserting `viewdefinitions/patient.ViewDefinition.json` parses as valid JSON and carries required fields (`resourceType == "ViewDefinition"`, `id`, `name`, `status`, `resource == "Patient"`, non-empty `select` with a `column` array) — write FIRST, expect it to FAIL until T009 lands

### Implementation for User Story 1

- [ ] T008 [US1] Author `viewdefinitions/patient.ViewDefinition.json`: `resourceType: "ViewDefinition"`, `id: "patient"`, `name: "patient_view"`, `status: "active"`, `resource: "Patient"`, and a single top-level `select` whose `column` array defines the 14 DoH columns with FHIRPath per `data-model.md` §1 / `contracts/viewdefinition-patient.md` (`id`→`getResourceKey()`, `mrn`, `name_family`, `name_given`, `gender`, `birth_date`, `deceased`, `race_code`/`race_display`, `ethnicity_code`/`ethnicity_display`, `address_city`/`address_state`/`address_postal_code`) — no row-multiplying `forEach`; multi-valued elements reduced with `.first()` (one row per patient, FR-002/FR-003/FR-010)
- [ ] T009 [US1] Confirm `tests/test_viewdefinition.py` required-field test now passes against the authored file (`python -m unittest tests.test_viewdefinition`)

**Checkpoint**: The Patient ViewDefinition artifact exists and passes its file-level contract test. End-to-end query validation occurs once US2 provides publishing (quickstart, T020).

---

## Phase 4: User Story 2 - Operator publishes and materializes the view (Priority: P1)

**Goal**: Deliver `publish_views.py` — a separate, stdlib-only entry point that discovers every ViewDefinition file, `PUT`s each under its stable id (update-in-place), `POST`s `$materialize`, reports publish and materialize outcomes separately per view, isolates failures, and reflects any failure in the exit status.

**Independent Test**: Run the step twice against the same server; the first run creates/materializes the view, the second updates in place with no duplicate and reports success; an induced bad ViewDefinition surfaces the server's reason and exits non-zero while other views still proceed.

### Tests for User Story 2

- [ ] T010 [P] [US2] In `tests/test_viewdefinition.py`, add tests for ViewDefinition file **discovery** from a temp directory (matching files found; a malformed-JSON file and an `id`-less file each fail *that file* without raising, FR-008) — write FIRST, expect FAIL
- [ ] T011 [P] [US2] In `tests/test_viewdefinition.py`, add a test for the `$materialize` `Parameters` **body builder** (produces `{resourceType: "Parameters", parameter: [{name: "type", valueCode: "<type>"}]}`, default `view`, research.md R3) — write FIRST, expect FAIL
- [ ] T012 [P] [US2] In `tests/test_viewdefinition.py`, add a test for **outcome → exit-code aggregation** (all publish+materialize ok → exit 0; any publish or materialize failure → non-zero; materialize `skipped` when publish failed) reusing `FileOutcome`/`RunSummary` — write FIRST, expect FAIL

### Implementation for User Story 2

- [ ] T013 [P] [US2] Extend `config.example.json` with an OPTIONAL `server.materialize_type` field documented as defaulting to `"view"` (research.md R3); do not add any secret
- [ ] T014 [US2] Create `publish_views.py` entry point with its own `argparse` parser: `--config` (default `config.json`), `--viewdefinitions-dir` (default `viewdefinitions`), `--materialize-type` (default from `server.materialize_type` else `view`), `--dry-run`, `--verbose`, `--log-dir` (default `log`); import `load_config`/`validate_config`/`setup_logging`/`FhirClient`/`FileOutcome`/`RunSummary` from `fhir_common.py` (contracts/publish-materialize-cli.md CLI)
- [ ] T015 [US2] Implement startup behavior in `publish_views.py`: load config, run `validate_config` and fail loudly before any network call when required `server.*` is missing/placeholder (unless `--dry-run`); then discover ViewDefinition files from `--viewdefinitions-dir`, treating zero files as an operator error (exit non-zero; `--dry-run` may warn) — FR-006/FR-007
- [ ] T016 [US2] Implement ViewDefinition file **discovery** in `publish_views.py`: scan the dir for `*.json`, parse each, require `resourceType == "ViewDefinition"` and an `id`; a malformed or id-less file fails that file (recorded, reflected in exit) without blocking others (FR-011, data-model §2)
- [ ] T017 [US2] Implement the `$materialize` **Parameters body builder** in `publish_views.py` (single `type` valueCode parameter from the resolved materialize type) — research.md R3
- [ ] T018 [US2] Implement the per-view **publish + materialize** flow in `publish_views.py`: `PUT {base}/ViewDefinition/{id}` (200/201 = ok) via `FhirClient`; on publish ok, `POST {base}/ViewDefinition/{id}/$materialize` with the Parameters body; on publish failure record it and **skip** materialize for that view; continue to remaining views (per-view isolation, FR-005/FR-008, contracts §"Server operations")
- [ ] T019 [US2] Implement per-view **outcome reporting + exit code** in `publish_views.py`: record publish and materialize results separately (materialize success carries `viewName`/`viewType`; failure carries the `OperationOutcome` reason), print the per-view summary + roll-up line, write the timestamped audit log under `log/`, and exit `0` iff every view published AND materialized (else non-zero, after all attempted) — FR-008/FR-009, SC-004

**Checkpoint**: `publish_views.py` runs end-to-end; unit tests T010–T012 pass; idempotent re-run produces no duplicate (SC-003).

---

## Phase 5: User Story 3 - Maintainer adds the next resource type later (Priority: P3)

**Goal**: Confirm the publish/materialize mechanism is resource-type-agnostic — adding a new ViewDefinition file requires no code or invocation change (FR-011, SC-006). Patient remains the only authored view (FR-012); this story protects the generalization, it does not add a second production view.

**Independent Test**: Drop a second minimal ViewDefinition file into a temp `viewdefinitions/` dir and confirm the same discovery/publish path processes both with no change to `publish_views.py`.

### Tests for User Story 3

- [ ] T020 [P] [US3] In `tests/test_viewdefinition.py`, add a test that discovery over a temp dir containing the Patient view plus a second minimal ViewDefinition file returns BOTH as processable work units, with no code change to the discovery function (proves FR-011/SC-006)

### Implementation for User Story 3

- [ ] T021 [US3] Add a short "Adding another resource type" note to `README.md` documenting that a maintainer drops a new `*.ViewDefinition.json` into `viewdefinitions/` and re-runs `publish_views.py` with no mechanism change, and that speculative non-Patient views are intentionally NOT authored yet (FR-012)

**Checkpoint**: Generalization is verified by test and documented; no speculative views added.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, lint, and the end-to-end validation that spans US1 + US2

- [ ] T022 [P] Update `README.md` with `publish_views.py` usage (CLI flags, config, dry-run, materialize-type) and a note that the ViewDefinition conformance gate is Aidbox acceptance, not `validator_cli.jar` (research.md R5)
- [ ] T023 [P] Run `ruff check publish_views.py fhir_common.py process.py tests/test_viewdefinition.py` and resolve findings
- [ ] T024 Run the full `quickstart.md` end-to-end validation against an Aidbox ≥ 2508 holding the fixture Patients: dry-run (§1), publish+materialize (§2), query `sof.patient_view` for N rows + correct columns (§3, SC-001/SC-002/SC-005), idempotent re-run (§4, SC-003), induced-failure surfacing (§5, SC-004), and empty-set edge case (§6)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **BLOCKS User Story 2** (publish_views.py imports `fhir_common.py`). Does NOT block User Story 1.
- **User Story 1 (Phase 3)**: Depends only on Setup — the ViewDefinition file + its file-level unit test do not need `fhir_common.py`. Can run in parallel with Phase 2.
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2). Independent of US1's artifact for its own unit tests.
- **User Story 3 (Phase 5)**: Depends on Foundational (discovery exists, US2 T016). Logically validates US2's generality.
- **Polish (Phase 6)**: T024 (e2e) depends on BOTH US1 (the view) and US2 (the publisher). T022/T023 depend on the relevant files existing.

### User Story Dependencies

- **US1 (P1)**: Independent artifact (the ViewDefinition JSON). Its end-to-end query proof needs US2 to publish, but the artifact and its contract test stand alone.
- **US2 (P1)**: Needs Foundational. Its unit tests stand alone; its e2e uses the US1 artifact.
- **US3 (P3)**: Needs US2's discovery function. No new production view.

### Within Each User Story

- Tests are written FIRST and expected to FAIL before implementation (T007 before T008/T009; T010–T012 before T014–T019; T020 before relying on it).
- In US2: CLI/imports (T014) → startup (T015) → discovery (T016) → body builder (T017) → publish+materialize flow (T018) → reporting/exit (T019). T013 (config example) is independent [P].

### Parallel Opportunities

- T002 [P] alongside T001.
- T006 [P] after the T003→T004→T005 chain.
- **US1 (Phase 3) can run fully in parallel with Foundational (Phase 2)** — different files, no shared code.
- US2 test tasks T010, T011, T012 [P] together (same file `tests/test_viewdefinition.py` — coordinate edits or stage sequentially if one author); T013 [P] independent of all US2 code.
- Polish T022, T023 [P] together.

---

## Parallel Example: Foundational + User Story 1 overlap

```bash
# Once Setup (T001–T002) is done, these two tracks proceed concurrently:

# Track A — Foundational (blocks US2):
Task: "Create fhir_common.py by moving shared primitives out of process.py (T003)"

# Track B — User Story 1 (the MVP artifact, no dependency on fhir_common.py):
Task: "Write tests/test_viewdefinition.py required-field test (T007)"
Task: "Author viewdefinitions/patient.ViewDefinition.json (T008)"
```

---

## Implementation Strategy

### MVP First

The MVP is the **combination of US1 + US2** (both P1): the Patient view is useless until it is on
the server and materialized, and the publisher is useless without a view. Recommended path:

1. Phase 1: Setup.
2. Phase 2: Foundational (`fhir_common.py` extraction) — verify `process.py` unchanged.
3. Phase 3: US1 — author the ViewDefinition (can overlap Phase 2).
4. Phase 4: US2 — build `publish_views.py`.
5. **STOP and VALIDATE**: run quickstart §1–§4 (T024 subset) — publish, materialize, query N rows,
   idempotent re-run. This is the demoable MVP.

### Incremental Delivery

1. Setup + Foundational → shared module ready, processor still green.
2. US1 + US2 → publish/materialize/query works → **MVP demo**.
3. US3 → confirm generalization (test + README) without authoring speculative views.
4. Polish → README, lint, full e2e including failure + empty-set edge cases.

---

## Notes

- [P] = different files, no dependency on incomplete tasks. Several US2 unit tests share
  `tests/test_viewdefinition.py`; treat their [P] as "logically independent" and serialize the
  actual file writes if one person is editing.
- Tests are written before implementation and expected to fail first (project `unittest` convention).
- The ViewDefinition conformance gate is **Aidbox acceptance** (`PUT` + `$materialize`), not
  `validator_cli.jar` (research.md R5) — do not wire this resource into the HL7 validator.
- Patient is the ONLY authored view (FR-012); US3 proves the mechanism generalizes without adding
  a second production view.
- Commit after each task or logical group; re-run `process.py` tests after the extraction to prove
  the no-op refactor.
