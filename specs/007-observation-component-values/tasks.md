---

description: "Task list for feature 007-observation-component-values"
---

# Tasks: Surface Component & Coded Measurements in the Observation View

**Input**: Design documents from `specs/007-observation-component-values/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/observation-view-columns.md, quickstart.md

**Tests**: No automated test tasks are generated. The spec did not request TDD, and the existing
directory-driven `tests/test_viewdefinition.py` shape suite already covers the edited file (research
R5). Value-level correctness is validated by the e2e quickstart, which the **user runs against
Aidbox** (Claude stops at offline steps — memory: never run against Aidbox).

**Organization**: Tasks are grouped by user story. Note: this feature edits a **single file**
(`viewdefinitions/observation.ViewDefinition.json`), so most tasks are sequential-in-file; the two
stories remain independently testable (US1 can ship alone as the MVP).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1, US2
- **(user runs — live Aidbox)**: an e2e step the user executes against the server; Claude does not run it

## Path Conventions

Single-project CLI (unchanged from 001–006). The only edited artifact is
`viewdefinitions/observation.ViewDefinition.json` at the repo root; docs at the repo root.

---

## Phase 1: Setup (Shared)

**Purpose**: Establish the no-regression baseline before editing.

- [ ] T001 Confirm the edit target and record the baseline: verify `viewdefinitions/observation.ViewDefinition.json` parses (`python3 -c "import json; json.load(open('viewdefinitions/observation.ViewDefinition.json'))"`) and note its current column set (the "existing" columns in `specs/007-observation-component-values/data-model.md`) as the FR-005/SC-004 no-regression reference.
- [ ] T002 (user runs — live Aidbox) Capture the pre-edit `sof.observation_view` row count (`SELECT count(*) FROM sof.observation_view;`, quickstart Step 0) to prove one-row-per-Observation is preserved (SC-002).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: None. This is a data-only edit to one existing, already-discovered ViewDefinition;
`publish_views.py`/`fhir_common.py`/`process.py`/config/tests are unchanged (plan Summary, research
R1). There is no shared code or schema to build before the stories.

**⚠️ Cross-story note**: US1 and US2 both edit the **same file**. They are independently *testable*
but must be applied **sequentially in that file** (they cannot be edited in parallel).

**Checkpoint**: No foundational work required — proceed directly to User Story 1.

---

## Phase 3: User Story 1 - See blood-pressure panel readings (Priority: P1) 🎯 MVP

**Goal**: Surface each blood-pressure panel's Systolic and Diastolic readings as two generic
component triads on the same one-row-per-Observation row (FR-001/FR-002/FR-003/FR-004/FR-007).

**Independent Test**: Query `sof.observation_view` for `code = '85354-9'` and confirm each row shows
two populated triads (e.g. Systolic 128 mmHg / Diastolic 88 mmHg) — 0 all-empty measurement rows.

### Implementation for User Story 1

- [ ] T003 [US1] Add the two generic component triads (6 columns: `component1_display`, `component1_value`, `component1_unit`, `component2_display`, `component2_value`, `component2_unit`) to the `select[].column` array in `viewdefinitions/observation.ViewDefinition.json`, placed after `effective_date_time`, using the **primary (indexer)** paths and types from `specs/007-observation-component-values/data-model.md` (`component[0]`/`component[1]` → `.code.coding.first().display` [string], `.value.ofType(Quantity).value` [decimal], `.value.ofType(Quantity).unit` [string]). Do not add `forEach` (FR-003).
- [ ] T004 [US1] Verify offline: `python3 -c "import json; json.load(open('viewdefinitions/observation.ViewDefinition.json'))"` parses, then `python3 -m unittest tests.test_viewdefinition -v` passes (key column, provenance `where`, single `cms_measure` all intact; quickstart Step 1).
- [ ] T005 [US1] (user runs — live Aidbox) `python3 publish_views.py --config config.json`; confirm the Observation view `PUT` + `$materialize` succeed. **If the `component[0]`/`component[1]` indexer is rejected or yields null**, apply the fallback in `viewdefinitions/observation.ViewDefinition.json` (`component[0]`→`component.first()`, `component[1]`→`component.last()`, suffixes unchanged) per research R2 / the contract, and re-run (quickstart Step 2).
- [ ] T006 [US1] (user runs — live Aidbox) Query `sof.observation_view WHERE code = '85354-9'` for the six component columns; assert two populated triads with the source Systolic/Diastolic values + "mmHg" units and **0 rows with all-empty measurement columns** (SC-001; quickstart Step 3).

**Checkpoint**: User Story 1 is fully functional and independently testable — the reported gap is closed. **This is a shippable MVP.**

---

## Phase 4: User Story 2 - No silently-empty rows for the other Observation shapes (Priority: P2)

**Goal**: Add the coded-result display label so coded Observations are readable, and confirm the
scalar-quantity case is unchanged (no regression) — rounding out coverage for every Observation
shape in the fixtures (FR-005/FR-006/FR-009).

**Independent Test**: Query the depression-screening rows and confirm `value_code_display` is
non-null; query the Hemoglobin A1c row and confirm its value/unit are unchanged.

### Implementation for User Story 2

- [ ] T007 [US2] Add the `value_code_display` column (path `value.ofType(CodeableConcept).coding.first().display`, type string) to the `select[].column` array in `viewdefinitions/observation.ViewDefinition.json`, placed immediately after the existing `value_code` (data-model.md). Leave `value_code` and all top-level `value_*` columns unchanged (FR-005).
- [ ] T008 [US2] Verify offline: re-run `python3 -m unittest tests.test_viewdefinition -v` (still green after the added column).
- [ ] T009 [US2] (user runs — live Aidbox) Re-publish/materialize if not already carrying T007, then query `sof.observation_view WHERE code IN ('73831-0','73832-8')`; assert `value_code` present **and** `value_code_display` non-null (FR-006; quickstart Step 4).
- [ ] T010 [US2] (user runs — live Aidbox) Regression + invariant check: query `code = '4548-4'` (Hemoglobin A1c) — `value_quantity`/`value_unit` unchanged vs. T001 baseline and all component columns null (FR-005/SC-004; Step 5); and `SELECT count(*)` equals the T002 baseline (SC-002; Step 6).

**Checkpoint**: Every Observation shape in the fixtures (panel, scalar, coded) reports its recorded value(s) — FR-009 satisfied.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Documentation to reflect the new columns and the indexer-verification outcome.

- [ ] T011 [P] Update `README.md` to note the Observation view now surfaces component (blood-pressure) measurements as two generic triads plus a coded-result display label.
- [ ] T012 [P] Update `known-validation-issues.md` to record the outcome of the `component[0]`/`component[1]` indexer verification (primary accepted, or fallback `.first()`/`.last()` applied) from T005 — the first use of a positional index in this repo's view set.
- [ ] T013 (user runs — live Aidbox) Run the full `specs/007-observation-component-values/quickstart.md` end-to-end as the final acceptance pass (all 6 steps green).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 offline (Claude); T002 live (user). No dependencies.
- **Foundational (Phase 2)**: None — no blocking work.
- **User Story 1 (Phase 3)**: Starts after Setup. Delivers the MVP.
- **User Story 2 (Phase 4)**: Independently testable, but **edits the same file as US1** → T007 must be applied sequentially after T003 in `observation.ViewDefinition.json` (not in parallel).
- **Polish (Phase 5)**: After the story(ies) you intend to ship are validated.

### Within Each User Story

- Edit the JSON (T003 / T007) → offline verify (T004 / T008) → live publish+query (T005–T006 / T009–T010). Offline verification precedes the live gate.

### Parallel Opportunities

- Parallelism is **minimal by nature** — the sole code artifact is one JSON file, so its edit tasks are same-file sequential.
- Only the two Polish doc updates are parallel: **T011 [P]** (`README.md`) and **T012 [P]** (`known-validation-issues.md`) touch different files with no dependency on each other.

```bash
# The only parallelizable pair (different files):
Task: "Update README.md — Observation view now surfaces component triads + coded display"
Task: "Update known-validation-issues.md — record component[1] indexer verification outcome"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001 (baseline) → T003 (add triads) → T004 (offline verify).
2. User runs T002, T005, T006 against Aidbox — **STOP and VALIDATE**: BP panels now readable.
3. Ship: the reported analytics-team gap is closed with US1 alone.

### Incremental Delivery

1. US1 → validate → ship (MVP: BP triads).
2. US2 (add `value_code_display`, confirm no regression) → validate → ship.
3. Polish docs (T011–T012) and run the full quickstart (T013).

### Notes

- All edits land in `viewdefinitions/observation.ViewDefinition.json`; no code/config/test changes (plan Structure Decision).
- Live/e2e tasks (T002, T005–T006, T009–T010, T013) are **run by the user** against Aidbox; Claude completes the offline tasks (T001, T003–T004, T007–T008, T011–T012).
- The indexer→fallback decision (T005) is resolved by the server-acceptance gate, not assumed.
- Commit after each story's offline edits are verified (T004; T008).
