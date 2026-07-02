# Contract: Run Accounting — Storability Outcomes & Three-State Exit Code

Extends the existing `FileOutcome` / `RunSummary` / `exit_code` (`fhir_common.py:58–94`) and the
per-type summary (`_report_summary`, `process.py:791`). No new CLI flags; this changes the meaning of
the run's outcome vocabulary, summary output, and process exit status.

## Outcome status vocabulary

Existing: `succeeded | failed | skipped`. Add: **`remediated`**, **`deferred`**.

| Status | When | Storability meaning |
|--------|------|---------------------|
| `succeeded` | stored, no transform applied | stored (untouched) |
| `remediated` | stored after a content transform (Cause 2 stratum prune) was applied | stored (remediated) |
| `deferred` | resource type isolated: only fabrication could store it (FR-007); not submitted | not stored, by design |
| `failed` | non-2xx / transport error for a **not-yet-documented** cause | unexpected error |
| `skipped` | type-filter exclusion / unreadable / unrecognized (unchanged) | n/a |

> A Cause-1 lever-only PUT (reference-skip header) MAY be reported `succeeded` (its content was not
> changed). The mrp-2 transform is always `remediated`. The distinction the run must preserve is
> **stored vs. deferred vs. unexpected-error**; `remediated` is the reportable subset of stored that
> required a transform (SC-003, SC-006).

## Remediation logging & documentation audit (FR-013)

Every applied lever/transform is logged via `log_remediation(key, …)` (WARNING) with a `key` drawn
from the `REMEDIATIONS` registry — one stable key per Aidbox accommodation
(`aidbox-cause-1-reference-skip`, `aidbox-cause-3-terminology-unset`,
`aidbox-cause-2-mrp2-stratum-prune`). Each key has a matching `REMEDIATION: <key>` marker line in
`known-validation-issues.md`, and `tests/test_remediation_docs.py` asserts the two-way invariant
(every registry key documented; every doc marker maps to a key). This makes runtime remediations ⊆
registry ⊆ documented, so "an undocumented remediation is a defect" is a deterministic check.

> The `REMEDIATION:` marker is **distinct** from the `PATTERN:` lines and is **not** consumed by
> `scripts/validate.sh` (which reads `PATTERN:` for the HL7 gate); it is read only by the audit test.

## `RunSummary` additions

- Track `remediated: int` and `deferred: int` counts (alongside succeeded/failed/skipped).
- Per-type stratification (`by_type` in `_report_summary`) gains `remediated` and `deferred` columns,
  so each resource-type row reads: submitted / succeeded / **remediated** / failed / **deferred** /
  skipped (FR-012, SC-006).

## Exit-code contract (replaces `0 if failed==0 else 1`)

Three distinguishable states (FR-012):

| Constant (illustrative) | Value | Condition |
|-------------------------|-------|-----------|
| success | `0` | every in-scope resource stored (no `failed`, no `deferred`) |
| `EXIT_COMPLETED_WITH_DEFERRALS` | e.g. `2` | at least one `deferred`, and **no** unexpected `failed` |
| `EXIT_UNEXPECTED_ERROR` | e.g. `1` | at least one unexpected `failed` (undocumented rejection / transport error) |

Rules:

- **Precedence**: unexpected error dominates deferral. If any `failed` exists, exit
  `EXIT_UNEXPECTED_ERROR` regardless of deferrals.
- Deferral MUST NOT be reported using the unexpected-error code (they are distinct values).
- `remediated` does **not** change the exit code — a fully-remediated-and-stored run exits `0`.
- Values must be stable and documented (README) so operators/CI can branch on them.

## Test scenarios (→ `tests/test_exit_codes.py`, `tests/test_summary.py`)

1. **All stored, some remediated** ⇒ exit `0`; per-type row shows `remediated > 0`; `deferred == 0`.
2. **A deferral, no unexpected error** ⇒ exit `EXIT_COMPLETED_WITH_DEFERRALS`; summary shows the
   deferred type; exit ≠ unexpected-error code.
3. **An unexpected `failed`** (undocumented 422) ⇒ exit `EXIT_UNEXPECTED_ERROR`, even if a deferral is
   also present (precedence).
4. **Per-type counts** ⇒ `_report_summary` output includes stored/remediated/deferred per FHIR type
   (assert via `assertLogs`).
5. **Idempotent re-run** ⇒ a second run over already-stored resources produces no duplicates and no
   content diffs; exit `0` (FR-010, SC-004).
