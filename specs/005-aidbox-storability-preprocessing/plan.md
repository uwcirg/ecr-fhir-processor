# Implementation Plan: Aidbox Storability Pre-Processing

**Branch**: `005-aidbox-storability-preprocessing` | **Date**: 2026-07-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-aidbox-storability-preprocessing/spec.md`; constitution
`.specify/memory/constitution.md` **v1.3.0** (Principle VIII — Input Pre-Processing for Aidbox
Storability; subordinate to Principle V — never fabricate/silently drop clinical content).

## Summary

Make every emitted resource **storable on the Aidbox ingestion surface** — a second validation
surface distinct from the HL7 FHIR Reference Validator gate — without buying storage with fabricated
or dropped clinical values. The 2026-06-12 live run stored 39/50; the 11 rejections trace to three
documented causes (`known-validation-issues.md` → "Aidbox ingestion-time validation").

> **Amendment (2026-07-02).** The first live run with the transform (`log/…101340.log`) surfaced two
> gaps the original three-cause model missed, now folded into this feature: **(Cause 4)** a base-FHIR
> `ext-1` rejection on an empty `triggerCodeValueSetVersion` sub-extension in the CMS2 eICR Composition
> — no non-mutating lever, so a second structure-only prune is added (FR-015; lever 4 below); and a
> **run-accounting** gap where a transform that ran but whose resource then failed on an independent
> cause (a mis-set `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` re-enabling Cause 3) reported `remediated=0`
> and was invisible — fixed by surfacing a `transformed` count independent of storage (FR-016).

The work has four levers, applied in the constitution's priority order (non-mutating before
transform):

1. **Cause 1 — reference target-profile conformance (Observation ×2, MedicationRequest ×1 + the two
   message Bundles carrying them).** Cleared by the **existing** per-request `aidbox-validation-skip:
   reference` header the processor already sends when `config.server.validation_skip` includes
   `"reference"` (`fhir_common.py:259`). **No content change; no new code** — this feature confirms
   and documents the lever (empirically 39→42 on 2026-06-12).
2. **Cause 3 — terminology display-name binding (the MeasureReports).** Cleared **box-side** by
   leaving `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` unset. **No processor change** — the processor MUST
   NOT rewrite terminology displays (FR-004).
3. **Cause 2 — base-FHIR `mrp-2` invariant (every MeasureReport, 5 standalone + 3 nested in message
   Bundles).** The **only** cause with no non-mutating lever and the crux of this feature. A new,
   documented, non-fabricating transform **removes each stratifier `stratum` that has neither `value`
   nor `component`** (a `population`-only stratum has no stratification key — malformed structure, not
   clinical content, per the product decision recorded in the spec). Every removal is logged at
   WARNING with any population counts it carried (FR-006), and applied to **every** MeasureReport the
   processor persists — standalone **and** nested inside persisted message Bundles (FR-005), so a
   message Bundle carrying an unpruned MeasureReport is not rejected whole.
4. **Cause 4 — base-FHIR `ext-1` invariant (the CMS2 eICR Composition + its message Bundle).** Also no
   non-mutating lever (`ext-1` is a base cardinality invariant). A second documented, non-fabricating
   transform **removes each child of an `eicr-trigger-code-flag-extension` that carries neither a
   `value[x]` nor nested extensions** — in the sample data an empty `triggerCodeValueSetVersion`; the
   `triggerCode`/`triggerCodeValueSet` siblings (the clinical payload) are preserved and no version is
   fabricated. Logged at WARNING per removal (FR-006), applied to the promoted Composition and every
   copy nested in a persisted message/document Bundle (FR-015), so the Bundle is not rejected whole.

Around those levers, the run's accounting is extended to make remediation **transparent, auditable,
and idempotent** (User Story 3): the transformed resource is the **single canonical representation**
written to `output/` and PUT to Aidbox (FR-008); a **deferral** state isolates any resource type that
could only be stored by fabrication (FR-007, none in the current sample); a **three-state exit code**
distinguishes all-stored (0) / completed-with-deferrals / unexpected-error (FR-012); a **per-type
summary** reports stored/remediated/deferred/**transformed** (FR-012, FR-016, SC-006); and
`known-validation-issues.md` is reconciled so each Cause records its chosen lever/transform (FR-013),
replacing the stale "out of scope" / `BOX_FHIR_SCHEMA_VALIDATION=false` framing.

**Scope of code change (deliberately small).** The persistence pipeline, `FhirClient`, config, and
the reference-skip header already exist and are reused. This feature adds (a) **two** pruning
transforms applied on the write path in `process.py` (Cause 2 stratum prune; Cause 4 trigger-code
sub-extension prune), (b) a `remediated`/`deferred`/`transformed` accounting extension to
`RunSummary`/`FileOutcome`/exit-code in `fhir_common.py`, (c) targeted `unittest`s, and (d)
documentation reconciliation. Cause 1 and Cause 3 need **no** code.

## Technical Context

**Language/Version**: Python 3, **standard library only** (Principle I). No runtime dependency is
added — the pruning transform is dict-walking (`json` already in use); accounting is dataclass
fields. Dev/CI only: `ruff`, stdlib `unittest`, and the HL7 `validator_cli.jar` (for the no-regression
gate, FR-009).

**Primary Dependencies**: None new. Reuses `process.py` (`Pipeline`, `_process_measure_report`,
`_process_message`, `_guarded_put`), `fhir_common.py` (`FhirClient.submit_put` — already emits the
`aidbox-validation-skip` header; `RunSummary`/`FileOutcome`/`exit_code`), and the existing
`config.server.validation_skip` mechanism.

**Storage**: Target Aidbox FHIR server (remote, OAuth2 client-credentials, FHIR Schema engine
**enabled** — `BOX_FHIR_SCHEMA_VALIDATION=true`, FR-014). Emitted/transformed resources are mirrored
to `output/{measure}/{YYYY-MM-DD}/` (the same bytes that are PUT — FR-008). Canonical inputs in
`test/input/` are **never** edited (FR-008, Principle III).

**Testing**: (1) **Targeted stdlib `unittest`** — new `tests/test_stratum_prune.py` (pruning is
idempotent, removes only value-and-component-less strata, preserves conforming siblings and all other
elements, logs a WARNING carrying removed population counts, walks into message-Bundle-nested
MeasureReports) plus extensions to `tests/test_summary.py` (per-type stored/remediated/deferred
counts) and a new `tests/test_exit_codes.py` (three-state exit code). (2) **HL7 no-regression gate**
— `scripts/validate.sh` over the transformed `output/` produces **zero new** signatures vs.
`test/conformance-baseline.sigs` (FR-009); regenerate the baseline only if pruning *legitimately
removes* a signature, never to accept a new one. (3) **End-to-end against Aidbox** (quickstart) — a
persistence run against a clean box (schema engine on, reference-skip enabled, no terminology server)
stores the full storable set and a re-run is diff-free/duplicate-free.

**Target Platform**: Linux (developer + GitHub Actions CI); anywhere Python 3 + network to Aidbox.

**Project Type**: Single-project CLI utility — **no structural change**. Two entry points
(`process.py`, `publish_views.py`) over shared `fhir_common.py`; `process.py` is 836 lines, well under
the ~1000-line split threshold, so the transform stays in `process.py` (Single-File Simplicity).

**Performance Goals**: Not latency-critical. Pruning is an in-memory walk over each MeasureReport's
`group.stratifier.stratum` arrays (tens of elements); negligible vs. network round-trips.

**Constraints**: Zero runtime dependencies; non-mutating levers preferred over transforms (Principle
VIII); never fabricate/silently drop clinical content (Principle V) — every removal logged + counts
captured; single canonical representation (`output/` == PUT bytes); fixtures immutable; no new
HL7-validator signature vs. baseline; per-type failure/deferral isolation; idempotent re-run
(retained-id PUT); schema engine stays enabled (never `BOX_FHIR_SCHEMA_VALIDATION=false`).

**Scale/Scope**: The 2026-06-12 sample of 50 resources across the two measures with fixtures
(`poor-diabetic-control`, `controllable-bp`). Target: **50/50** stored via the stratum-pruning
strategy; **0** deferrals expected for the current sample (the deferral path is a required mechanism,
FR-007, but does not trigger on this data).

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase, the `test/input/`
fixtures, the 2026-06-12 run logs, and the Aidbox docs already captured in
`known-validation-issues.md`; decisions are in [research.md](./research.md) (R1–R8). **No
`NEEDS CLARIFICATION` remains.** The three spec Clarifications (2026-07-01 session) — prune applies to
nested MRs too, single canonical representation, distinct deferral exit code — are carried directly
into FR-005/FR-008/FR-012 and the design below.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | Pruning transform + accounting use stdlib only (dict walk, dataclass fields); no package added; transform stays in `process.py` (< 1000 lines) | ✅ PASS |
| II. FHIR Profile Conformance | Storability remediation targets the **Aidbox** surface and MUST NOT introduce a new HL7-validator signature vs. the committed baseline (FR-009). IG-version config untouched | ✅ PASS |
| III. Dual-Gate Validation Testing | Both gates honored: gate 1 (`validator_cli.jar`) re-run over the transformed `output/` for zero-new-signature; gate 2 (Aidbox acceptance) is the storability target. Fixtures in `test/input/` stay immutable (FR-008) | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | N/A to new shapes — operates on the two measures already fixtured. CMS2 remains fixture-less (out of scope, unchanged) | ✅ PASS (N/A) |
| V. Data Integrity & Defensive Processing | **Central gate.** No fabrication (FR-007 defers instead); no silent drop (every removed stratum logged WARNING + counts, FR-006); per-type failure/deferral isolation (FR-011); idempotent retained-id re-run (FR-010) | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | Unchanged promotion model; MeasureReports remain first-class and are now storable so they're actually analyzable. Pruning does not reach into or overwrite higher-fidelity copies | ✅ PASS |
| VII. Analytics View Definitions & Materialization | Unaffected — this feature stores the resources the existing views select from; no ViewDefinition change | ✅ PASS (N/A) |
| **VIII. Input Pre-Processing for Aidbox Storability** | **Directly satisfied.** Non-mutating levers first (Cause 1 header reused; Cause 3 box-side config), transform only where no lever exists (Cause 2 `mrp-2`); transform is non-fabricating and structure-only; every remediation documented in `known-validation-issues.md` (FR-013) + logged; fixtures immutable; no conformance regression; never disables the schema engine (FR-014) | ✅ PASS |
| Deployment & Security | base URL/creds from `config.json` only; reuses existing `server.validation_skip`; no new secret. `config.example.json` already carries `validation_skip` | ✅ PASS |
| Development Workflow | Small `process.py`/`fhir_common.py` change + new/extended `unittest` + `known-validation-issues.md` reconciliation + README note; CI lint + unit + HL7 no-regression gate | ✅ PASS |

**Result**: **No violations.** No Complexity Tracking entries required. The plan operationalizes
Principle VIII for the first time while keeping it strictly subordinate to Principle V (storability is
never bought with fabricated or silently-dropped clinical content).

## Project Structure

### Documentation (this feature)

```text
specs/005-aidbox-storability-preprocessing/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R8 (per-Cause lever/transform, mrp-2 semantics, exit codes, no-regression)
├── data-model.md        # Phase 1 — entities (Emitted resource, Rejection cause, Remediation action/record, Storability outcome) + state/exit-code model
├── quickstart.md        # Phase 1 — runnable persist→verify→re-run validation guide against a clean Aidbox
├── contracts/           # Phase 1
│   ├── stratum-prune.md          # Transform contract: mrp-2 pruning (inputs, invariants, logging, idempotency)
│   ├── trigger-code-ext-prune.md # Transform contract: Cause 4 ext-1 empty trigger-code sub-extension prune
│   └── run-accounting.md         # Outcome/exit-code contract: stored/remediated/deferred/transformed + exit states
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
process.py                    # MODIFIED — add prune_measurereport_strata() (Cause 2) AND
                              #   prune_empty_trigger_code_extensions() (Cause 4) transforms + wire into
                              #   _process_measure_report (standalone) and _process_message (nested MRs +
                              #   the eICR Composition trigger-code section) BEFORE mirror + PUT (FR-005,
                              #   FR-015, FR-008). _record_remediation records a transform regardless of
                              #   PUT result; extend run()/_report_summary for remediated + deferred +
                              #   transformed accounting (FR-016).
fhir_common.py                # MODIFIED — FileOutcome gains "remediated"/"deferred" status +
                              #   remediations_applied; RunSummary tracks remediated/deferred/transformed;
                              #   exit_code three-state (0 / DEFERRALS / UNEXPECTED-ERROR) per FR-012;
                              #   REMEDIATION_TRIGGER_CODE_EXT_PRUNE added to the REMEDIATIONS registry.
config.example.json           # UNCHANGED — server.validation_skip already present (["reference"] enables Cause 1).
scripts/validate.sh           # UNCHANGED — reused as the FR-009 no-regression gate over transformed output/.
test/conformance-baseline.sigs# MAYBE regenerated — only if pruning legitimately removes a signature (FR-009);
                              #   never to admit a NEW signature. [[conformance-gate-baseline-stale]]
known-validation-issues.md    # MODIFIED — reconcile the "Aidbox ingestion-time validation" section:
                              #   per Cause record the chosen lever/transform (FR-013); drop the stale
                              #   "mrp-2 out of scope" line and the BOX_FHIR_SCHEMA_VALIDATION=false suggestion.

tests/
├── test_stratum_prune.py         # NEW — mrp-2 pruning invariants, idempotency, nested-MR walk, WARNING+counts
├── test_trigger_code_ext_prune.py# NEW — Cause 4 ext-1 pruning invariants, idempotency, nested walk, WARNING
├── test_summary.py               # EXTENDED — per-type stored/remediated/deferred/transformed; _record_remediation
└── test_exit_codes.py            # NEW — three-state exit code (0 / deferrals / unexpected error)

README.md                     # UPDATE — replace the pre-Principle-VIII "deferred MeasureReport" stance;
                              #   note MeasureReports are now made storable via documented stratum pruning.
```

**Structure Decision**: Single-project CLI, unchanged from features 001–004. The change is a **narrow
write-path transform plus an accounting extension**, both in the existing entry point / shared module.
No new module, entry point, config field, or dependency; `process.py` stays under the single-file
threshold. The transform lives on the **write path only** so the canonical `test/input/` fixtures stay
immutable while the transformed resource is the single representation both mirrored to `output/` and
PUT to Aidbox (FR-008).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty. The deferral mechanism (FR-007) is
> required by Principle V/VIII, not added complexity: it does not trigger on the current sample but
> must exist so storability is never achieved by fabrication.
