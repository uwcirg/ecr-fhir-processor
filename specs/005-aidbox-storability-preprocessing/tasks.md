---

description: "Task list for Aidbox Storability Pre-Processing"
---

# Tasks: Aidbox Storability Pre-Processing

**Input**: Design documents from `specs/005-aidbox-storability-preprocessing/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (stratum-prune.md, run-accounting.md), quickstart.md

**Tests**: INCLUDED — the spec defines Independent Tests + acceptance scenarios per story, and Constitution Principle III requires unit tests for transformation logic and dual-gate validation. Test tasks are therefore first-class here.

**Organization**: Tasks are grouped by the three user stories from spec.md so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 (P1), US2 (P2), US3 (P2)
- Exact file paths are included in each task.

## Path Conventions

Single-project CLI at repo root: entry points `process.py` / `publish_views.py` over shared `fhir_common.py`; tests in `tests/`; docs at root (`known-validation-issues.md`, `README.md`); conformance gate `scripts/validate.sh` + `test/conformance-baseline.sigs`. No structural change (plan.md → Structure Decision).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the environment and existing levers this feature builds on.

- [ ] T001 Verify prerequisites for both validation surfaces: `java` + `validator_cli.jar` resolve at repo root (FR-009 HL7 no-regression gate), and `config.example.json` carries `server.validation_skip` (the Cause-1 lever, currently `[]`). Record findings; do not change fixtures.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend the shared run-accounting substrate that US2 (`remediated`) and US3 (`deferred`, three-state exit code, per-type summary) both build on, and add the remediation-key registry that US1/US2 logging and the US3 doc-audit share.

**⚠️ CRITICAL**: US2 and US3 cannot be completed until this phase is done. (US1 is levers/config/docs only, but its T005 doc markers reference the T003b registry keys, so T003b should precede T005.)

- [ ] T002 [P] Extend the outcome vocabulary and counters in `fhir_common.py`: add `remediated` and `deferred` to the `FileOutcome.status` vocabulary (data-model §5) and add `remediated`/`deferred` integer counters to `RunSummary` (currently `read/submitted/succeeded/failed/skipped`, `fhir_common.py:78`).
- [ ] T003 Replace the two-state `RunSummary.exit_code` (`fhir_common.py:93`, `0 if failed==0 else 1`) with the three-state machine + named constants (`EXIT_UNEXPECTED_ERROR`, `EXIT_COMPLETED_WITH_DEFERRALS`) per contracts/run-accounting.md: unexpected `failed` dominates → error code; else any `deferred` → deferrals code; else `0`. `remediated` never changes the code. Keep `failed → 1` so existing behavior is backward-compatible. These constants are the single source of truth for the exit values (documented in README, T020). (depends on T002)
- [ ] T003b [P] Add a remediation-key registry + logging helper in `fhir_common.py` (or `process.py`): define one stable key per Aidbox accommodation — `REMEDIATION_REFERENCE_SKIP` (`"aidbox-cause-1-reference-skip"`), `REMEDIATION_TERMINOLOGY_UNSET` (`"aidbox-cause-3-terminology-unset"`), `REMEDIATION_MRP2_STRATUM_PRUNE` (`"aidbox-cause-2-mrp2-stratum-prune"`) — collected in a `REMEDIATIONS` frozenset, plus `log_remediation(key, msg, *args)` that asserts `key in REMEDIATIONS` and logs at WARNING (FR-006, FR-013). This is the single source of truth for the T005/T008/T012 remediation logging and the T019 documentation audit, closing the FR-013 loop (runtime remediations ⊆ registry ⊆ documented).

**Checkpoint**: Shared accounting model + remediation registry ready — US2 and US3 can proceed.

---

## Phase 3: User Story 1 - Land everything storable without altering content (Priority: P1) 🎯 MVP

**Goal**: Recover the resources that need **no content change** — Cause 1 (reference target-profile) via the existing per-request `aidbox-validation-skip: reference` header, and Cause 3 (terminology display) via the box leaving its terminology server unset. No resource content is modified.

**Independent Test**: Run persistence against a clean Aidbox (schema engine on, `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true`, no terminology server) with `config.server.validation_skip=["reference"]`; confirm every non-MeasureReport resource is stored (HTTP 200) and its content is byte-identical to the emitted output.

### Tests for User Story 1

- [ ] T004 [P] [US1] Extend `tests/test_validation_skip.py` to assert (a) `FhirClient.submit_put` emits the `aidbox-validation-skip: reference` header when `config.server.validation_skip=["reference"]` and omits it when empty (`fhir_common.py:259`), and (b) the submitted resource dict is unchanged by enabling the lever (FR-003, no content mutation).

### Implementation for User Story 1

- [ ] T005 [US1] Reconcile the Cause 1 and Cause 3 subsections of `known-validation-issues.md` → "Aidbox ingestion-time validation": record the chosen non-mutating lever per cause (reference-skip header for Cause 1; unset terminology server for Cause 3) and that the processor makes **no** content change for either (FR-002, FR-003, FR-004, FR-013); add a `REMEDIATION: aidbox-cause-1-reference-skip` and a `REMEDIATION: aidbox-cause-3-terminology-unset` marker line to the respective subsections (audited by T019).
- [ ] T006 [US1] Update `README.md` to state that Cause 1/Cause 3 storability comes from non-mutating levers (reference-skip header driven by `config.server.validation_skip=["reference"]`; box-side terminology config), not content edits — replacing any pre-Principle-VIII framing.

**Checkpoint**: US1 delivers the storability MVP (levers only, zero content change) and is shippable on its own.

---

## Phase 4: User Story 2 - Make MeasureReports storable by removing malformed structure (Priority: P2)

**Goal**: Make every MeasureReport storable by removing each stratifier `stratum` that has neither `value` nor `component` (base-FHIR `mrp-2`), treating an unlabeled stratum as malformed structure — non-fabricating, structure-only — and logging every removal with any counts it carried.

**Independent Test**: Take a MeasureReport with a value/component-less stratum, run it through pre-processing, and confirm (a) the malformed stratum is gone, (b) it passes Aidbox ingestion, (c) a WARNING records the removal and its counts, and (d) no other element changed.

**Depends on**: Phase 2 (needs the `remediated` outcome status).

### Tests for User Story 2

- [ ] T007 [P] [US2] Create `tests/test_stratum_prune.py` covering the transform contract (contracts/stratum-prune.md C1–C9, scenarios 1–7): removes a `population`-only stratum; preserves conforming siblings byte-identical; no-op on clean input; idempotent (second call removes 0); WARNING carries the removed stratum's population counts (via `assertLogs`); nested-in-message-Bundle walk; everything-else-untouched (deep-equal minus the removed path). Write FIRST and ensure it FAILS before T008–T011.

### Implementation for User Story 2

- [ ] T008 [US2] Implement `prune_measurereport_strata(report, source_filename) -> int` in `process.py`: remove each stratum where `value is None and not component`; leave conforming strata and all other elements untouched; idempotent; log each removal via `log_remediation(REMEDIATION_MRP2_STRATUM_PRUNE, ...)` (T003b) including the removed stratum's `population` counts (FR-005, FR-006, contract C1–C6, C9).
- [ ] T009 [US2] Implement `prune_nested_measurereports(bundle, source_filename) -> int` in `process.py`: find every MeasureReport in `bundle.entry[*].resource`, recursing into nested Bundles, and apply `prune_measurereport_strata` to each (FR-005, contract C7).
- [ ] T010 [US2] Wire the standalone prune into `Pipeline._process_measure_report` (`process.py:635`) **before** `_maybe_mirror(...)` so the mirrored `output/` bytes equal the PUT bytes (FR-008, contract C8); when strata were removed, mark the outcome `remediated` (data-model §5).
- [ ] T011 [US2] Wire `prune_nested_measurereports` into `Pipeline._process_message` (`process.py:642`) **before** `_maybe_mirror(...)` and the whole-Bundle PUT (`process.py:655`) so a message Bundle carrying an unpruned MeasureReport is not rejected whole (FR-005); mark the message-Bundle outcome `remediated` when strata were removed.
- [ ] T012 [US2] Reconcile the Cause 2 subsection of `known-validation-issues.md`: document the stratum-prune transform (exact `mrp-2` message, root cause, the removal rule + logging), add a `REMEDIATION: aidbox-cause-2-mrp2-stratum-prune` marker line (audited by T019), and **remove** the stale "mrp-2 ... out of scope per the gate philosophy" line and the `BOX_FHIR_SCHEMA_VALIDATION=false` architectural suggestion, which Principle VIII/FR-014 forbid (FR-013, FR-014).
- [ ] T013 [US2] Run the HL7 no-regression gate over the transformed output (`scripts/validate.sh "output/**/*.json" config.json`) and confirm **zero new** signatures vs. `test/conformance-baseline.sigs` (FR-009, SC-005). If the prune legitimately *removes* a signature, regenerate the baseline with the pinned validator (`scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json`) and commit `test/conformance-baseline.sigs`; never regenerate to admit a new signature.

**Checkpoint**: US1 AND US2 both work — the levers land content-unchanged resources and MeasureReports become storable via the documented, non-fabricating prune.

---

## Phase 5: User Story 3 - Transparent, auditable, idempotent remediation (Priority: P2)

**Goal**: Make every accommodation visible and repeatable — a per-type stored/remediated/deferred summary, a deferral path (never fabricate) reflected in a distinct exit code, idempotent re-runs, and a documentation entry for every applied remediation.

**Independent Test**: Run persistence twice against the same Aidbox; confirm a per-type summary of stored/remediated/deferred counts, that every applied lever/transform appears in the logs with a matching `known-validation-issues.md` entry, and that the second run creates no duplicates and no diffs for already-stored resources.

**Depends on**: Phase 2 (three-state exit code + counters). Reads the `remediated` outcomes produced by US2.

### Tests for User Story 3

- [ ] T014 [P] [US3] Create `tests/test_exit_codes.py` for the three-state exit code (contracts/run-accounting.md): all-stored (incl. remediated) → `0`; a `deferred` with no unexpected `failed` → `EXIT_COMPLETED_WITH_DEFERRALS`; any unexpected `failed` → `EXIT_UNEXPECTED_ERROR` even alongside a deferral (precedence). Write FIRST; ensure it FAILS before T016.
- [ ] T015 [P] [US3] Extend `tests/test_summary.py` to assert `_report_summary` emits per-FHIR-type `stored`/`remediated`/`deferred` counts (in addition to succeeded/failed/skipped), via `assertLogs` (FR-012, SC-006).

### Implementation for User Story 3

- [ ] T016 [US3] Implement the deferral path in `process.py`: where a resource type could only be stored by fabricating or dropping clinical content, mark its outcomes `deferred` (isolated, not submitted) rather than fabricating (FR-007, FR-011). Not triggered by the current sample — provide the mechanism so `run()` returns `EXIT_COMPLETED_WITH_DEFERRALS` via the T003 property.
- [ ] T017 [US3] Extend `_report_summary` (`process.py:791`) per-type rows and the totals line to include `remediated` and `deferred` counts, and log the resolved `exit_code`'s meaning, so an operator reads stored/remediated/deferred per type from the run's own summary without Aidbox logs (FR-012, SC-006).
- [ ] T018 [US3] Extend `tests/test_rerun.py` to assert an idempotent re-run **after remediation** produces no duplicate resources and no content diffs for already-stored resources (retained-id PUT update-in-place) and exits `0` (FR-010, SC-004).
- [ ] T019 [P] [US3] Create `tests/test_remediation_docs.py` asserting the FR-013 two-way invariant against the `REMEDIATIONS` registry (T003b): (a) for every key in `REMEDIATIONS`, `known-validation-issues.md` contains a `REMEDIATION: <key>` line (no applied remediation is undocumented); and (b) every `REMEDIATION: <key>` line in the doc maps to a registry key (no stale/orphan marker). This makes "an undocumented remediation is a defect" a deterministic check, not markdown prose-scraping (FR-013, SC-003).

**Checkpoint**: All three stories independently functional; remediation is transparent, auditable, and idempotent.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Whole-feature validation and documentation currency.

- [ ] T020 [P] Update `README.md` end-to-end: MeasureReports are now made storable via documented stratum pruning (not deferred); the run reports per-type stored/remediated/deferred with a three-state exit code; the schema engine stays enabled (never `BOX_FHIR_SCHEMA_VALIDATION=false`). Remove the pre-Principle-VIII "deferred MeasureReport" stance.
- [ ] T021 Run `ruff check .` and the full `python -m unittest` suite; fix any regressions from the T002/T003 accounting change in pre-existing tests.
- [ ] T022 Execute `quickstart.md` end-to-end against a clean Aidbox (schema engine on, reference-skip enabled, no terminology server): confirm the full storable set lands (targeting 50/50, SC-001), per-type summary + exit `0` with `remediated>0`, and a diff-free/duplicate-free re-run (SC-004).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. **Blocks US2 and US3.** (US1 does not depend on it.)
- **US1 (Phase 3)**: Depends on Setup only — levers/config/docs, no shared-model dependency.
- **US2 (Phase 4)**: Depends on Foundational (needs `remediated`).
- **US3 (Phase 5)**: Depends on Foundational (needs three-state exit code + counters); reads `remediated` outcomes produced by US2 for a fully meaningful summary but its mechanism/tests are independent.
- **Polish (Phase 6)**: Depends on all desired stories being complete.

### User Story Dependencies

- **US1 (P1)**: Independent — can ship as the MVP alone.
- **US2 (P2)**: Independent of US1; requires Phase 2.
- **US3 (P2)**: Independent test-wise; requires Phase 2; its summary is richest once US2 is present.

### Within Each User Story

- Tests written first and failing before implementation (T007 before T008–T011; T014 before T016).
- Transform functions (T008/T009) before their wiring (T010/T011).
- Accounting property (T003) before exit-code/summary behavior (T016/T017).
- Documentation reconciliation lands in the same story as the code it describes.

### Parallel Opportunities

- Within Foundational, T002 and T003b are [P] (different concerns); T003 depends on T002.
- US1 test (T004) is independent of US2/US3 work and can proceed in parallel once Setup is done.
- Within US3, T014, T015, and T019 (three different test files) run in parallel.
- Across stories: after Phase 2, US2 and US3 implementation can be staffed in parallel (US3 reads US2's `remediated` only for the end-to-end summary check in T022).

---

## Parallel Example: User Story 3

```bash
# Launch the two US3 test files together (different files, no shared state):
Task: "Create tests/test_exit_codes.py for the three-state exit code"
Task: "Extend tests/test_summary.py for per-type stored/remediated/deferred counts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup.
2. Phase 3: US1 — enable/confirm the reference-skip lever + terminology box config, document Causes 1/3.
3. **STOP and VALIDATE**: run against a clean Aidbox; confirm non-MeasureReport resources land content-unchanged (targets ~42/50 as on 2026-06-12).
4. Ship — US1 is valuable and shippable alone.

### Incremental Delivery

1. Setup → US1 (MVP: levers, zero content change).
2. Phase 2 Foundational → US2 (stratum prune makes MeasureReports storable → targets 50/50).
3. US3 (transparency: per-type summary, deferral mechanism, three-state exit code, idempotent re-run, doc completeness).
4. Polish: README currency + quickstart e2e.

### Parallel Team Strategy

After Phase 2: Developer A takes US2 (transform + wiring + Cause-2 docs + no-regression gate); Developer B takes US3 (exit codes + summary + idempotency + doc-completeness audit). US1 (levers/docs) can be done by either before or alongside, as it is code-light.

---

## Notes

- [P] = different files, no dependency on incomplete tasks.
- The only content transform is the Cause-2 stratum prune; Causes 1 and 3 use non-mutating levers (Principle VIII priority).
- The transform runs on the write path **before** the output mirror, so `output/` bytes equal the PUT bytes (FR-008); `test/input/` fixtures stay immutable (Principle III).
- Regenerate `test/conformance-baseline.sigs` only to *drop* a legitimately-removed signature, never to admit a new one (FR-009). [[conformance-gate-baseline-stale]]
- Never set `BOX_FHIR_SCHEMA_VALIDATION=false` (FR-014) — it breaks the FHIR REST API.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
