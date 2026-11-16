# Tasks: Stratum Prune Reporting

**Input**: Design documents from `specs/008-stratum-prune-reporting/`
**Prerequisites**: plan.md, spec.md, research.md (R1–R6), data-model.md, contracts/stratum-prune-reporting.md (R1–R10, test scenarios 1–11), quickstart.md

**Tests**: Included. The contract lists test scenarios and the constitution (Principle III, CI) requires unit coverage. Write each story's tests first and confirm they fail before implementing.

**Organization**: By user story (spec.md US1 P1, US2 P2, US3 P3). Nearly all code changes are in `process.py`. Tasks touching it are sequential; test-file tasks in different files may be done in parallel.

**Constraints for every task** (spec FR-009/FR-010):
- Do NOT change the prune predicate (`stratum.get("value") is None and not stratum.get("component")`).
- Do NOT change the deletion of an emptied `stratum` property, the resource bytes, `_record_remediation`, `FileOutcome`/`RunSummary` in `fhir_common.py`, or the exit code.
- Do NOT run anything against Aidbox; dry-run only.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Baseline capture)

**Purpose**: Record pre-change behavior so SC-003/SC-004/SC-005 can be proven by diff afterwards.

- [X] T001 Confirm the suite is green before changes: run `ruff check process.py tests/` and `python3 -m unittest discover -s tests -v` from the repo root. If anything already fails, stop and report it before editing `process.py`.
- [X] T002 Capture the pre-change dry-run baseline: `python3 process.py --config config.example.json --dry-run --input-dir test/input --output-dir <scratchpad>/before-output > <scratchpad>/before.log 2>&1`, where `<scratchpad>` is the session scratchpad directory (not the repo). Keep both the log and the mirror for T019/T020.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Introduce the result type and switch the prune's return value without changing any observable output. Every story builds on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add a frozen dataclass `StratumPruneResult` (fields `removed: int = 0`, `kept: int = 0`, `emptied: int = 0`; `__add__` returning the field-wise sum) to `process.py`, directly above `_summarize_stratum_populations` in the "MeasureReport mrp-2 stratum prune" section. Docstring: cite data-model.md and the invariants `emptied <= removed`, and `removed + kept` = strata before the prune.
- [X] T004 Change `prune_measurereport_strata` in `process.py` to return `StratumPruneResult`, with `removed` computed exactly as today (contract R1). Leave `kept`/`emptied` at 0 for now; they are filled in US1. Update the return annotation and docstring.
- [X] T005 Change `prune_nested_measurereports` in `process.py` to accumulate with `total = StratumPruneResult()` and `total = total + prune_measurereport_strata(...)`, returning `StratumPruneResult` (contract R4). Update the annotation and docstring.
- [X] T006 Update the two call sites in `process.py` so output is unchanged: in `_process_measure_report`, `result = prune_measurereport_strata(...)` then `_record_remediation(outcome, result.removed, f"pruned {result.removed} mrp-2 stratum(s)")`; in `_process_message`, the same with `removed_mrp2 = prune_nested_measurereports(...)` → use `.removed`. Leave the Cause 4 (`removed_tc`) lines untouched.
- [X] T007 [P] Update existing int assertions in `tests/test_stratum_prune.py` to the result type: `removed = …` → `result = …` and `self.assertEqual(result.removed, N)` (tests `test_removes_malformed_stratum`, `test_preserves_conforming_siblings`, `test_noop_on_clean_input`, `test_idempotent`, `test_nested_measurereport_pruned`); `test_no_measurereport_is_a_noop` asserts `.removed == 0`.
- [X] T008 [P] Update `tests/test_rerun.py` `test_transform_is_idempotent_on_rerun`: `self.assertEqual(removed_second.removed, 0)`.
- [X] T009 Run `ruff check process.py tests/` and `python3 -m unittest discover -s tests -v`. Everything must pass with no behavior change (contract scenario 9).

**Checkpoint**: Same output as before; the result type is in place.

---

## Phase 3: User Story 1 - See how much of each pruned MeasureReport survived (Priority: P1) 🎯 MVP

**Goal**: The RunSummary per-file note reports removed, kept and emptied counts for every file where the prune removed at least one stratum (FR-001–FR-004, FR-008).

**Independent Test**: The quickstart dry-run over `test/input`: each MeasureReport and message-Bundle line ends with `pruned 1 mrp-2 stratum(s), kept 4, 1 stratifier(s) left empty`.

### Tests for User Story 1 ⚠️ (write first; they must fail before T013–T014)

- [X] T010 [P] [US1] Add a `PruneCountsTest` class to `tests/test_stratum_prune.py`, reusing the module's `_stratum`/`CONFORMING`/`MALFORMED`/`COMPONENT` helpers. Build multi-stratifier reports inline (the `_report` helper has only one stratifier). Cover contract scenarios:
  - (1) a stratifier with only `MALFORMED`, plus a second stratifier with 2 conforming strata → `StratumPruneResult(removed=1, kept=2, emptied=1)`;
  - (2) one stratifier `[CONFORMING, MALFORMED, COMPONENT]` → `(1, 2, 0)`;
  - (3) a stratifier with no `stratum` key AND one with `stratum: []`, beside a stratifier with only `MALFORMED` → `emptied == 1` (pre-empty stratifiers are not counted; FR-003);
  - (4) clean report `[CONFORMING, COMPONENT]` → `(0, 2, 0)`;
  - (5) idempotency → second call is `removed=0, emptied=0` with `kept` equal to the first call's;
  - (8) a message Bundle with one MeasureReport directly in `entry` and one inside a nested document Bundle → field-wise sum of both.
- [X] T011 [P] [US1] Add a `PruneSummaryNoteTest` class to `tests/test_summary.py`. Use a dry-run `process.Pipeline` built like `_dry_pipeline` in `tests/test_rerun.py` (with `write_mirror=False`, `output_dir` a `tempfile.TemporaryDirectory`). Process the fixture `test/input/controllable-bp/standard/CMS165_bulk_dial_high_00042/MeasureReport_ae8ea7e3-ff01-4e9c-a736-4f7d09ade91d.json` with `KIND_MEASURE_REPORT`, and assert the outcome's `detail` contains `pruned 1 mrp-2 stratum(s), kept 4, 1 stratifier(s) left empty` and `remediations_applied == 1` (contract scenario 10, SC-001). Repeat with the message Bundle `…/CMS165_bulk_dial_high_00042/Bundle_43914e77-6cd5-451f-992e-e0474417a2b9.json` and `KIND_MESSAGE`, checking the Bundle outcome (`outcomes[0]`) carries the same Cause 2 clause.
- [X] T012 [US1] Run the new tests and confirm they FAIL (kept/emptied still 0; note still the old format).

### Implementation for User Story 1

- [X] T013 [US1] In `prune_measurereport_strata` (`process.py`), compute `kept` (sum of `len(kept)` for every stratifier with a list `stratum`, including untouched ones; non-list/absent `stratum` contributes 0) and `emptied` (+1 when `strata` was non-empty and `kept` is empty, i.e. exactly the branch that does `del stratifier["stratum"]`). Return `StratumPruneResult(removed, kept, emptied)`. The pruning itself must not change (research R2, contract R2/R3).
- [X] T014 [US1] Add a small helper `_stratum_prune_note(result: StratumPruneResult) -> str` in `process.py` returning `f"pruned {r.removed} mrp-2 stratum(s), kept {r.kept}, {r.emptied} stratifier(s) left empty"` (research R3, contract R7). Use it at both call sites from T006 in place of the old f-string. Still pass `result.removed` as `_record_remediation`'s count (contract R9).
- [X] T015 [US1] Run `python3 -m unittest discover -s tests -v`. T010/T011 and all prior tests pass.

**Checkpoint**: MVP. Per-file summary shows all three counts.

---

## Phase 4: User Story 2 - Trace each removal to its stratifier (Priority: P2)

**Goal**: Each removal WARNING names `group[<i>]` and a stratifier label (FR-005, FR-006, FR-011).

**Independent Test**: Prune a report with malformed strata in two stratifiers. Two WARNINGs are logged, each with its own group index and label.

### Tests for User Story 2 ⚠️ (write first; they must fail before T018)

- [X] T016 [P] [US2] Add a `StratifierLabelTest` class to `tests/test_stratum_prune.py` for `process._stratifier_label(stratifier, index)` (contract scenario 7):
  - `{"id": "stratifier-payer", "code": [...]}` → `"stratifier-payer"`;
  - no id, `code=[{"coding":[{"system":"s","code":"plan","display":"SDE Payer"}]}]` → `"code=plan"`;
  - no id, a coding without `code` plus `text` → `"text=SDE Payer"`;
  - no id, `code` as a lone dict (not a list) with a coding → `"code=…"` (defensive);
  - `{}` at index 3 → `"#3"`;
  - the result is never empty.
- [X] T017 [P] [US2] Add a `PruneWarningLocationTest` class to `tests/test_stratum_prune.py` (contract scenario 6). The report has group 0 with stratifier `{"id": "strat-a", stratum: [MALFORMED]}` and group 1 with stratifier `{"code":[{"text":"strat-b"}], stratum:[CONFORMING, MALFORMED]}`. Under `assertLogs("ecr-fhir-processor", level="WARNING")`, assert exactly 2 records, one containing `group[0] stratifier strat-a` and the other `group[1] stratifier text=strat-b`, both still containing `process.REMEDIATION_MRP2_STRATUM_PRUNE`, the source filename and the population counts. Assert the existing `test_warning_carries_population_counts` still passes unchanged.

### Implementation for User Story 2

- [X] T018 [US2] In `process.py`:
  (a) add `_stratifier_label(stratifier: dict, index: int) -> str` next to `_summarize_stratum_populations`, using this order: `id`, then the first `coding.code` across `stratifier["code"]` (normalize a lone dict to `[dict]`), giving `code=<code>`, then the first non-empty `text`, giving `text=<text>`, then `#<index>` (research R4, contract R6);
  (b) in `prune_measurereport_strata`, iterate `enumerate(report.get("group", []) or [])` and `enumerate(group.get("stratifier", []) or [])`, and change the `log_remediation` format to `"Removed value/component-less MeasureReport stratum (base-FHIR mrp-2) from %s at group[%d] stratifier %s; carried populations: %s"` with args `source_filename, group_index, _stratifier_label(stratifier, stratifier_index), _summarize_stratum_populations(stratum)` (contract R5). Keep the WARNING level and the remediation key.
- [X] T019 [US2] Run `python3 -m unittest discover -s tests -v`. T016/T017 and all prior tests pass.

**Checkpoint**: WARNINGs are traceable to a stratifier.

---

## Phase 5: User Story 3 - Clean reports stay quiet (Priority: P3)

**Goal**: Nothing new for MeasureReports/files where nothing was pruned (FR-007, SC-003).

**Independent Test**: A clean report produces no prune WARNING and its outcome detail is unchanged.

- [X] T020 [P] [US3] Add a `CleanReportSilenceTest` class to `tests/test_stratum_prune.py`: prune `[CONFORMING, COMPONENT]` under `self.assertNoLogs("ecr-fhir-processor", level="WARNING")` (Python 3.10+) (contract scenario 4).
- [X] T021 [P] [US3] In `tests/test_summary.py`, add a test: a dry-run `Pipeline` processes a deep copy of the T011 MeasureReport fixture pre-cleaned by calling `process.prune_measurereport_strata` on it first. Assert the outcome's `detail` contains no `mrp-2`, `remediations_applied == 0`, and `status == "succeeded"` (contract scenario 11).
- [X] T022 [US3] Run `python3 -m unittest discover -s tests -v`. These are expected to pass without further code changes, because `_record_remediation` already returns early when `removed <= 0`. If either fails, fix `process.py` so no note or log is emitted when `result.removed == 0`.

**Checkpoint**: All three stories are complete and independently tested.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T023 Capture the post-change dry-run: `python3 process.py --config config.example.json --dry-run --input-dir test/input --output-dir <scratchpad>/after-output > <scratchpad>/after.log 2>&1`. Verify:
  - every MeasureReport/message-Bundle summary line ends with `pruned 1 mrp-2 stratum(s), kept 4, 1 stratifier(s) left empty` (SC-001);
  - every prune WARNING contains `group[0] stratifier stratifier-payer` (SC-002);
  - the per-type rows and the `read=… | resources: …` totals and `exit_code=` lines equal those in `before.log` (SC-005).
- [X] T024 Byte-identity check (SC-004): `diff -r <scratchpad>/before-output <scratchpad>/after-output`. Only provenance `meta.tag`/`meta.source` values (version, processed-on) may differ. To confirm, compare with `meta` stripped, e.g. a short Python one-liner that loads each pair and compares `{k: v for k in resource if k != "meta"}`.
- [X] T025 [P] Append a short "Amended by 008" note under the Signature section of `specs/005-aidbox-storability-preprocessing/contracts/stratum-prune.md`, pointing to `specs/008-stratum-prune-reporting/contracts/stratum-prune-reporting.md`. It should say the return type is now `StratumPruneResult` and the WARNING gains `group[i]` + stratifier label. Do not rewrite the 005 text (FR-012).
- [X] T026 [P] Append a matching "Amended by 008" note to `specs/005-aidbox-storability-preprocessing/contracts/run-accounting.md`, near the `remediations_applied` section. It should give the new per-file Cause 2 note format and state that `remediations_applied` still receives the removed count (FR-012).
- [X] T027 [P] In `README.md`'s Cause 2 bullet (around line 129), change "Every removal is logged at WARNING with the population counts the stratum carried" to also mention the group/stratifier location, and add that the RunSummary per-file note reports strata removed, kept, and stratifiers left empty.
- [X] T028 [P] In `known-validation-issues.md`, Cause 2 section, update the sentence about the WARNING log to mention the group/stratifier location. Leave the `REMEDIATION: aidbox-cause-2-mrp2-stratum-prune` marker line unchanged, because `tests/test_remediation_docs.py` depends on it.
- [X] T029 [P] Fix `specs/008-stratum-prune-reporting/quickstart.md`: add `--config config.example.json` to every `python3 process.py --dry-run …` command (no `config.json` exists in the repo, and dry-run doesn't need credentials).
- [X] T030 Final gate: `ruff check process.py tests/` and `python3 -m unittest discover -s tests -v` both clean. Optionally run `scripts/validate.sh` and expect no new signature vs `test/conformance-baseline.sigs` (SC-006). A transient `phinvads.cdc.gov` timeout is not a regression.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T002)**: no dependencies. T002 MUST run before any `process.py` edit.
- **Foundational (T003–T009)**: after Setup; blocks all stories.
- **US1 (T010–T015)**: after Foundational.
- **US2 (T016–T019)**: after Foundational. Independent of US1 in behavior, but both edit `prune_measurereport_strata`, so do them one after the other (US1 first by priority).
- **US3 (T020–T022)**: after Foundational. Its tests are meaningful only after US1/US2, because they guard against regressions those stories could introduce.
- **Polish (T023–T030)**: after all stories. T023/T024 need T002's baseline.

### Within Each User Story

Tests first (must fail), then the `process.py` implementation, then the full-suite run.

### Parallel Opportunities

- T007 ∥ T008 (different test files).
- T010 ∥ T011 (`test_stratum_prune.py` vs `test_summary.py`).
- T016 ∥ T017 add separate classes to the same file. They're logically independent, but edit sequentially to avoid conflicts.
- T020 ∥ T021 (different files).
- T025 ∥ T026 ∥ T027 ∥ T028 ∥ T029 (different doc files).
- All `process.py` tasks (T003–T006, T013–T014, T018) are sequential.

## Parallel Example: User Story 1

```text
Task: "T010 [US1] PruneCountsTest in tests/test_stratum_prune.py"
Task: "T011 [US1] PruneSummaryNoteTest in tests/test_summary.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Setup (baseline), then Foundational (result type, no behavior change).
2. US1: counts in the per-file note.
3. STOP and validate with the quickstart dry-run. That alone answers "how much survived?"

### Incremental Delivery

1. Foundational → US1 (MVP) → US2 (traceable WARNINGs) → US3 (silence guard) → Polish (docs, byte-identity proof).
2. Each phase ends with a green suite and can be committed on its own on branch `008-stratum-prune-reporting`.

## Notes

- Expected fixture result (verified 2026-11-13): every one of the 7 standalone MeasureReports and 4 message Bundles gives removed=1, kept=4, emptied=1, always `stratifier-payer` in `group[0]`. The synthetic tests (T010, T016, T017) carry the real coverage of edge cases.
- Never run `process.py` without `--dry-run`; live/Aidbox runs are done by the user.
