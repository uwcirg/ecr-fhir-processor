# Phase 1 Data Model: Aidbox Storability Pre-Processing

This feature adds **no new persisted FHIR resource type**. It (a) transforms an existing resource type
(MeasureReport) on the write path and (b) extends the run's in-memory accounting model. The entities
below are the spec's Key Entities mapped onto the concrete code they touch.

---

## 1. Emitted resource

The FHIR resource on its way to Aidbox — the unit that is stored, remediated, or deferred.

| Field | Source | Notes |
|-------|--------|-------|
| resource type | `resourceType` (or `Bundle.type`) | Classified by `classify_resource` (`process.py:467`) into collection / measure-report / message. |
| retained id | `id` | Used for idempotent update-in-place PUT (FR-010). Never regenerated. |
| content | full resource dict | For a MeasureReport, may have `population`-only strata removed (§4). For all others, **byte-identical** to the stamped resource. |
| canonical bytes | mirrored file + PUT body | The **same** dict is written to `output/{measure}/{date}/` and PUT to Aidbox (FR-008). |

**Invariant**: the mirrored `output/` bytes equal the submitted bytes (single representation). The
`test/input/` fixture is the pre-transform input and is never modified (Principle III).

---

## 2. Aidbox rejection cause

A documented reason Aidbox refuses to store a resource. Each maps to one chosen remediation strategy.

| Cause | Aidbox signal | Affected (2026-06-12) | Remediation | Content changed? |
|-------|---------------|-----------------------|-------------|------------------|
| **1 — reference target-profile** | 422 `invalid-target-profile` | Observation ×2, MedicationRequest ×1 (+ 2 message Bundles) | Non-mutating lever: `aidbox-validation-skip: reference` header (existing) | **No** |
| **2 — `mrp-2` base invariant** | 422 constraint `mrp-2` | every MeasureReport (5 standalone + 3 nested) | Content transform: remove value+component-less strata (§4) | **Yes** (structure-only) |
| **3 — terminology display binding** | 422 `terminology-binding-error` | same MeasureReports | Non-mutating box-side lever: terminology server unset | **No** |

Only Cause 2 has no non-mutating lever, so it is the only content transform (Principle VIII priority).

---

## 3. Remediation action & Remediation record

**Remediation action** — what the processor did to make a resource storable:

- **lever** — a per-request header (Cause 1) or reliance on box-side config (Cause 3); no content change.
- **transform** — stratum removal (Cause 2); content changed, structure-only, non-fabricating.
- **deferral** — resource type isolated because only fabrication could store it (FR-007). *Not
  triggered by the current sample.*

**Remediation record** — the audit trail proving nothing was silent (SC-003):

- **runtime log** — a WARNING (or above) line per applied lever/transform. For a removed stratum, the
  line MUST include any population counts the stratum carried (FR-006).
- **documentation** — a matching entry in `known-validation-issues.md` keyed to the Aidbox cause: the
  exact message, root cause, and the lever/transform applied (FR-013). A remediation the processor
  performs that is *not* documented there is a defect.

---

## 4. MeasureReport stratum transform (Cause 2)

The concrete structure the transform operates on and its rules. See the transform contract
([contracts/stratum-prune.md](./contracts/stratum-prune.md)) for the full behavioral spec.

```
MeasureReport
└── group[]                         # unchanged
    └── stratifier[]                # unchanged (kept even if it ends up with 0 strata? see rule below)
        └── stratum[]               # <-- pruned here
            ├── value    (0..1)     # stratification key (CodeableConcept)
            ├── component(0..*)     # stratification key (multi-dimension)
            └── population(0..*)    # counts described by the key
```

**mrp-2**: `group.stratifier.stratum.all(value.exists() xor component.exists())`.

**Prune rule** — a stratum is **removed** iff it has **neither** `value` **nor** `component`
(regardless of whether it has a `population`). A stratum with `value` xor `component` is **kept**
untouched.

**Preservation invariants** (all must hold; tested):

1. Conforming sibling strata in the same stratifier are untouched.
2. Every other element of the MeasureReport (group populations, measure-scoring, DEQM
   `extension-criteriaReference`, meta, etc.) is untouched.
3. Idempotent: running the transform on an already-pruned MeasureReport removes nothing and changes
   nothing.
4. Applies to standalone MeasureReports **and** MeasureReports nested inside a persisted
   message/document Bundle (FR-005).
5. Each removal emits a WARNING carrying the removed stratum's population counts (FR-006).

> **Edge case (spec)**: a stratifier whose strata are all malformed loses all its strata; a stratifier
> with a mix loses only the malformed ones. An empty `stratifier` (0 strata) does not violate `mrp-2`
> (the `.all()` is vacuously true), so the stratifier element itself is left in place — the transform
> removes strata, not stratifiers, keeping the change minimal.

---

## 5. Storability outcome & exit-code model

Extends the existing `FileOutcome`/`RunSummary`/`exit_code` (`fhir_common.py:58–94`).

### Per-resource outcome status (vocabulary)

| Status | Meaning | Counts toward |
|--------|---------|---------------|
| `succeeded` | stored, no transform applied | stored |
| `remediated` | stored **after** a transform (or under a lever) was applied | stored + remediated |
| `deferred` | isolated — only fabrication could store it; not submitted | deferred |
| `failed` | unexpected rejection/transport error (undocumented cause) | unexpected error |
| `skipped` | excluded by type filter / unreadable / unrecognized (unchanged) | — |

> Cause 1 lever-only submissions may be reported as `succeeded` or `remediated` per the contract in
> [contracts/run-accounting.md](./contracts/run-accounting.md); the transform (Cause 2) is always
> `remediated`.

### Per-type summary (FR-012, SC-006)

The run summary (`_report_summary`, `process.py:791`) already stratifies by FHIR type; extend the
per-type row to report **stored / remediated / deferred** (in addition to the existing
succeeded/failed/skipped), so an operator reads the outcome from the run's own summary without Aidbox
server logs.

### Exit-code state machine (FR-012)

```
any status == failed (unexpected)      → EXIT_UNEXPECTED_ERROR   (distinct non-zero)
else any status == deferred            → EXIT_COMPLETED_WITH_DEFERRALS (distinct non-zero, ≠ above)
else                                   → 0   (every in-scope resource stored)
```

- Precedence: an unexpected error dominates a deferral (an unexpected failure is the more urgent
  signal). Deferral MUST NOT be reported using the unexpected-error code.
- Current sample: no `failed`, no `deferred` after remediation ⇒ **exit 0** with `remediated > 0`.
