# Implementation Plan: Stratum Prune Reporting

**Branch**: `008-stratum-prune-reporting` | **Date**: 2026-11-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-stratum-prune-reporting/spec.md`

## Summary

This feature adds reporting to the existing Cause 2 `mrp-2` stratum prune; what gets pruned does not change. The prune currently returns only a removed-stratum count. Here it is changed to return a small result object with three counts: **removed**, **kept** and **stratifiers emptied**. Results are summed across nested MeasureReports, and the three counts are written into the RunSummary per-file note. Each removal WARNING also gains `group[i]` and a stratifier identifier (`id`, then code, then `#index`). Which strata are removed, the resource bytes and the run accounting all stay the same: `remediations_applied` still receives the *removed* count, so `remediated` and `transformed` don't move. Reports that need no prune produce no new output.

## Technical Context

**Language/Version**: Python 3.11 (standard library only), unchanged.

**Primary Dependencies**: None new. Dev/CI only: `ruff`, stdlib `unittest`.

**Storage**: N/A. No change to what is PUT to Aidbox or mirrored to `output/`.

**Testing**: stdlib `unittest` (`python3 -m unittest discover -s tests -v`) plus `ruff check process.py tests/`. Extend `tests/test_stratum_prune.py` (counts, emptied-vs-pre-empty, identifier fallback, WARNING content, nested summing) and `tests/test_summary.py` (note text, silence when nothing is pruned). Update the existing `== int` assertions in `test_stratum_prune.py` and `test_rerun.py` to read `.removed`. Fixture check by dry-run (quickstart). The HL7 gate (`scripts/validate.sh`) should show no new signature, which holds trivially because content is unchanged.

**Target Platform**: Linux (developer + GitHub Actions CI).

**Project Type**: Single-project CLI. Edits `process.py` only; `fhir_common.py` is unchanged.

**Performance Goals**: N/A. Counting happens inside the existing single pass over strata.

**Constraints**: Zero runtime dependencies (Principle I). No change to the prune predicate, to how an emptied `stratum` is represented (property deleted), to idempotency, to resource bytes, to outcome statuses or counts, or to the exit code (spec FR-009/FR-010). WARNING level is kept (FR-011). Clean reports produce zero new output (FR-007).

**Scale/Scope**: About 4 functions touched in `process.py`: `prune_measurereport_strata`, `prune_nested_measurereports`, the two call sites in `_process_measure_report`/`_process_message`, and a new `_stratifier_label` helper plus a `StratumPruneResult` dataclass. Two feature-005 contract docs get addenda. The README Cause 2 paragraph gets one sentence.

### Resolved unknowns

There were none. Every design choice could be settled from the code and the fixtures; they're recorded in [research.md](./research.md) (R1–R6).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | stdlib `dataclasses` only | ✅ PASS |
| II. FHIR Profile Conformance | No resource-content change, so the conformance baseline is unaffected | ✅ PASS |
| III. Dual-Gate Validation Testing | HL7 gate re-run expected to be byte-identical; Aidbox gate unaffected (same bytes). Unit tests cover the new behavior | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | Applies to every MeasureReport regardless of measure/population; fixture dry-run covers all 7 | ✅ PASS |
| V. Data Integrity & Defensive Processing | *Strengthens* it: removal stays at WARNING and is now attributable to a stratifier; loss of a whole stratifier dimension is surfaced instead of implied. Never fabricates (prune unchanged) | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | No persistence change | ✅ PASS (N/A) |
| VII. Analytics View Definitions | No view change | ✅ PASS (N/A) |
| VIII. Input Pre-Processing for Aidbox Storability | Same transform, richer audit log ("every remediation … logged"). Remediation key `aidbox-cause-2-mrp2-stratum-prune` unchanged, so the `known-validation-issues.md` registry test is unaffected | ✅ PASS |
| Clear, Predictable Output | Summary gains deterministic counts; no new files | ✅ PASS |
| Development Workflow | README Cause 2 paragraph updated; ruff + unittest in CI | ✅ PASS |

**Result**: No violations. Complexity Tracking not required. Re-checked after Phase 1 design: still passing (the design adds no dependency, file or content change).

## Project Structure

### Documentation (this feature)

```text
specs/008-stratum-prune-reporting/
├── plan.md              # This file
├── research.md          # Phase 0: R1–R6 design decisions
├── data-model.md        # Phase 1: StratumPruneResult, removal record, stratifier label
├── quickstart.md        # Phase 1: unit + dry-run validation
├── contracts/
│   └── stratum-prune-reporting.md   # Addendum to 005 stratum-prune.md / run-accounting.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
process.py                     # StratumPruneResult, _stratifier_label, prune_* return type,
                               #   WARNING text, per-file note text at the two call sites
tests/test_stratum_prune.py    # new count/label/WARNING tests; .removed in existing asserts
tests/test_summary.py          # per-file note carries 3 counts; silent when removed == 0
tests/test_rerun.py            # .removed in the idempotency assert
specs/005-aidbox-storability-preprocessing/contracts/stratum-prune.md   # pointer to 008 addendum
specs/005-aidbox-storability-preprocessing/contracts/run-accounting.md  # pointer to 008 addendum
README.md                      # Cause 2 paragraph: summary now reports removed/kept/emptied
```

**Structure Decision**: Single project, no structural change. Everything stays in `process.py`, following the "Single-File Simplicity" principle; `fhir_common.py` (`FileOutcome`/`RunSummary`) is not touched, because the counts travel in the existing `detail` string.

## Complexity Tracking

None. No constitution violations.
