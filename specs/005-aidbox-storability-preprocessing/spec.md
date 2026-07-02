# Feature Specification: Aidbox Storability Pre-Processing

**Feature Branch**: `005-aidbox-storability-preprocessing`

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "Updates per un-addressed changes to constitution." (Implements Constitution
Principle VIII — Input Pre-Processing for Aidbox Storability, v1.3.0.)

## User Scenarios & Testing *(mandatory)*

Context: the processor already conforms to the HL7 FHIR Reference Validator gate, but a live
submission run against the target Aidbox server stored only 39 of 50 resources. The 11 rejections
trace to three documented ingestion-time causes (see `known-validation-issues.md` → "Aidbox
ingestion-time validation"). Aidbox ingestion is a **second validation surface**, separate from the
HL7 conformance gate. This feature makes the resources storable on that surface without buying
storage with fabricated or dropped clinical values.

### User Story 1 - Land everything storable without altering content (Priority: P1)

As the operator running the processor against Aidbox, I want every resource that can be accepted
without changing its clinical content to be stored, so the analytics store holds the maximum
faithful data set.

This covers the two rejection causes that have a non-mutating lever: (a) reference target-profile
conformance rejections, cleared by sending the per-request reference-skip header the processor
already supports, and (b) terminology display-name rejections, cleared by the target box leaving its
terminology binding validation unconfigured. No resource content is modified.

**Why this priority**: This is the storability MVP — it recovers the majority of rejected resources
(the 2026-06-12 run went 39 → 42 stored with the reference lever alone) using only levers that carry
zero risk of altering clinical meaning. It is valuable and shippable on its own.

**Independent Test**: Run persistence against a clean Aidbox (schema engine on, reference-skip
enabled, no terminology server) using the sample fixtures; confirm every non-MeasureReport resource
is stored (HTTP 200), with no resource content changed relative to the emitted output.

**Acceptance Scenarios**:

1. **Given** an Observation/MedicationRequest whose reference target-profile disagrees with the
   referenced resource's profile, **When** it is persisted with the reference-skip lever enabled,
   **Then** Aidbox stores it and its content is byte-identical to the pre-persistence resource.
2. **Given** a resource carrying a non-canonical terminology display name, **When** the target box
   has no terminology service configured, **Then** the resource is stored without the display being
   rewritten by the processor.
3. **Given** the sample fixture set, **When** a persistence run completes, **Then** every resource
   that requires no content change is stored, and the run reports that count.

---

### User Story 2 - Make MeasureReports storable by removing malformed structure (Priority: P2)

As the operator, I want MeasureReports that violate the base FHIR `mrp-2` invariant to become
storable via a documented, non-fabricating transform, so measure-evaluation results also land in the
analytics store.

The rejection is caused by a stratifier `stratum` that has neither `value` nor `component` (only a
`population`), which base FHIR R4 forbids and Aidbox rejects as a hard error with no server-side
lever. The remediation removes each such stratum, treating an unlabeled stratum (no stratification
key) as malformed structure rather than clinical content. Because removal discards whatever the
stratum carried, every removal is logged at WARNING or above — including any population counts it
held — and recorded in `known-validation-issues.md`, so nothing is dropped silently.

**Why this priority**: MeasureReports are the last unstored group; this is the only cause with no
non-mutating lever and the crux of the new pre-processing work. It ships after P1 because P1 already
delivers standalone value.

**Independent Test**: Take a MeasureReport with a value/component-less stratum, run it through
pre-processing, and confirm (a) the malformed stratum is gone, (b) the result passes Aidbox
ingestion, (c) a WARNING log line records the removal and any counts it carried, and (d) no other
element of the MeasureReport changed.

**Acceptance Scenarios**:

1. **Given** a MeasureReport whose `group.stratifier.stratum` has a `population` only and no `value`
   or `component`, **When** it is pre-processed, **Then** that stratum is removed and the
   MeasureReport is stored by Aidbox.
2. **Given** such a stratum carries a population count, **When** it is removed, **Then** a WARNING
   log entry records the removed stratum and its counts, so the drop is auditable.
3. **Given** a MeasureReport whose strata all conform (each has a `value` or `component`), **When**
   it is pre-processed, **Then** no stratum is removed and the resource is unchanged.

---

### User Story 3 - Transparent, auditable, idempotent remediation (Priority: P2)

As the operator (and as a reviewer/auditor), I want every storability accommodation to be visible and
repeatable, so I can trust that nothing was changed or dropped silently and can re-run safely.

**Why this priority**: The constitution forbids silent remediation (Principle V) and requires
documented, idempotent, per-type-isolated persistence (Principles V & VIII). Without this story, P1/P2
could technically store resources while hiding what they changed — unacceptable.

**Independent Test**: Run persistence twice against the same Aidbox; confirm the run emits a per-type
summary of stored/remediated/deferred counts, that every applied lever or transform appears in the
logs, that a matching entry exists in `known-validation-issues.md`, and that the second run creates no
duplicates and no diffs for already-stored resources.

**Acceptance Scenarios**:

1. **Given** a persistence run that applies any remediation, **When** it completes, **Then** it emits
   a per-resource-type summary of how many resources were stored, remediated, and deferred.
2. **Given** any resource that could only be made storable by fabricating a clinical value, **When**
   persistence runs, **Then** that resource type is deferred (not fabricated), and the deferral is
   logged and reflected in the process exit status.
3. **Given** a completed persistence run, **When** the run is repeated, **Then** no already-stored
   resource is duplicated or altered.
4. **Given** any remediation applied by the processor, **When** a reviewer inspects
   `known-validation-issues.md`, **Then** the remediation (cause, lever/transform, affected type) is
   documented there.

---

### Edge Cases

- **A transform would fabricate or drop clinical content**: The processor MUST NOT do it; the
  affected resource type is deferred (isolated, surfaced in exit status), never fabricated.
- **A remediation needed for Aidbox would introduce a new HL7-validator error**: The conflict MUST be
  surfaced for review, not silently accepted; the storability gain MUST NOT regress conformance.
- **The target box lacks the assumed server-side levers** (reference-skip disabled, or a terminology
  service configured): the corresponding cause resurfaces as a rejection; the processor MUST surface
  those failures per type rather than mask them.
- **A stratum lacks value and component but its parent stratifier has other, conformant strata**: only
  the malformed stratum is removed; conformant siblings are untouched.
- **A resource is rejected by Aidbox for a cause not yet documented**: it is treated as a real,
  undocumented failure — surfaced and blocking for that resource, never auto-suppressed.
- **Re-running after a resource was earlier deferred** (e.g., server rules later relaxed): the now-
  storable resource lands without duplicating or rolling back resources that already succeeded.

## Clarifications

### Session 2026-07-01

- Q: Does the `mrp-2` stratum-pruning also apply to MeasureReports nested inside the eCR message
  Bundles, or only to standalone MeasureReports? → A: All MeasureReports — standalone and those
  nested inside persisted message/document Bundles.
- Q: Is the remediated resource written to the on-disk `output/` files too, or is the transform
  applied only on the write path to Aidbox? → A: Single representation — the transformed resource is
  the canonical emitted output, written to `output/` and PUT to Aidbox.
- Q: When a resource is deferred (only fabrication could store it), does the run exit non-zero, and
  is that distinct from an unexpected error? → A: Distinct non-zero exit code for "completed with
  deferrals," separate from the unexpected-error code; all-stored exits 0.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The processor MUST treat Aidbox ingestion-time validation as a validation surface
  distinct from the HL7 FHIR Reference Validator gate, and MUST make emitted resources storable on
  that surface as a persistence goal.
- **FR-002**: The processor MUST prefer non-mutating levers over content transforms: where a
  per-request header or a documented server-side configuration makes a resource storable without
  altering its content, that lever MUST be used before any content transform is considered.
- **FR-003**: For reference target-profile conformance rejections (Cause 1), the processor MUST send
  the per-request reference-skip header when configured to do so, and MUST NOT alter the referenced
  or referencing resource's content to resolve the rejection.
- **FR-004**: For terminology display-name rejections (Cause 3), the processor MUST rely on the target
  box's terminology configuration and MUST NOT rewrite terminology display values to satisfy the
  binding.
- **FR-005**: For the `mrp-2` base-invariant rejection (Cause 2), the processor MUST remove each
  stratifier `stratum` that has neither a `value` nor a `component`, and MUST leave all conforming
  strata and every other element of the MeasureReport unchanged. This pruning MUST apply to **every**
  MeasureReport the processor persists — both standalone MeasureReports and those nested inside
  persisted message/document Bundles — so that a message Bundle carrying an unpruned MeasureReport is
  not rejected as a whole.
- **FR-006**: The processor MUST log every applied lever and every content transform at WARNING level
  or above. For a removed stratum, the log entry MUST include any population counts the removed
  stratum carried, so the removal is auditable and never silent.
- **FR-007**: The processor MUST NOT fabricate clinical values to make any resource storable. Where
  the only way to make a resource storable would be fabrication or dropping clinical content, the
  processor MUST defer (isolate) that resource type and surface the deferral (logged and reflected in
  exit status).
- **FR-008**: The remediated resource MUST be the single canonical representation the processor
  produces — the same transformed resource is written to the on-disk `output/` files and PUT to
  Aidbox (no divergence between the stored output and the submitted bytes). Pre-processing MUST NOT
  edit the canonical `test/input/` fixtures.
- **FR-009**: A storability remediation MUST NOT introduce any new HL7-validator error signature
  against the committed conformance baseline; if a needed transform would break conformance, the
  processor MUST surface the conflict rather than accept it silently. Because the transform is part
  of the canonical output (FR-008), the conformance baseline MAY be regenerated to drop signatures a
  transform legitimately removes, but MUST NOT gain any new signature.
- **FR-010**: Persistence with remediation MUST be idempotently re-runnable per resource type, so a
  re-run neither duplicates, diverges, nor rolls back resources that already succeeded.
- **FR-011**: Failures and deferrals MUST be isolated per resource type: one type failing to store
  MUST NOT block or roll back the storage of other types.
- **FR-012**: Each persistence run MUST emit a per-resource-type summary of how many resources were
  stored, remediated, and deferred, and MUST reflect the outcome in the process exit status using
  three distinguishable states: (a) exit 0 when every in-scope resource was stored; (b) a distinct
  non-zero exit code for "completed with deferrals" (an expected, intentional outcome — some resource
  type could only be stored via fabrication and was isolated); and (c) a separate non-zero exit code
  for unexpected errors (e.g., an undocumented Aidbox rejection or transport failure). Deferral MUST
  NOT be reported using the unexpected-error code.
- **FR-013**: Every remediation the processor applies (lever or transform, keyed to its Aidbox cause)
  MUST be documented in `known-validation-issues.md`; a remediation the processor performs that is not
  documented there is a defect.
- **FR-014**: The processor MUST NOT rely on disabling the Aidbox FHIR Schema validation engine to
  achieve storability; runs assume the schema engine remains enabled.
- **FR-015**: For the `ext-1` base-invariant rejection (Cause 4), the processor MUST remove each child
  sub-extension of an eICR `eicr-trigger-code-flag-extension` that carries neither a `value[x]` nor
  nested extensions (a url-only shell — in the sample data an empty `triggerCodeValueSetVersion`), and
  MUST leave the `triggerCode`/`triggerCodeValueSet` siblings and every other element unchanged. It
  MUST NOT fabricate a version value (Principle V). Like FR-005 this pruning MUST apply wherever such
  an extension is persisted — the promoted eICR Composition and every copy nested inside a persisted
  message/document Bundle — so the Bundle is not rejected as a whole. Every removal MUST be logged at
  WARNING naming the removed sub-extension (FR-006).
- **FR-016**: The run summary MUST surface that a content transform was applied to a resource
  **independently of whether that resource was ultimately stored** — so a transform that ran but whose
  resource then failed on an unrelated cause is not reported as though no remediation occurred. The
  `stored`/`remediated` counts continue to mean stored-via-remediation; a separate per-type and total
  `transformed` count reports transforms applied regardless of storage outcome, and does not affect the
  exit code.

### Key Entities *(include if feature involves data)*

- **Emitted resource**: a FHIR resource on its way to the Aidbox server; the unit that is stored,
  remediated, or deferred. Carries a resource type and a retained id used for idempotent update.
- **Aidbox rejection cause**: a documented reason Aidbox refuses to store a resource (reference
  target-profile conformance, `mrp-2` invariant, terminology display mismatch, `ext-1` empty
  trigger-code sub-extension). Each maps to a chosen remediation strategy.
- **Remediation action**: what the processor did to make a resource storable — a non-mutating lever
  (request header / reliance on server config) or a content transform (stratum removal, empty
  trigger-code sub-extension removal) or a deferral.
- **Remediation record**: the runtime log entry plus the `known-validation-issues.md` documentation
  describing an applied remediation, including any clinical counts a transform removed.
- **Storability outcome**: per resource (and aggregated per type) — stored, remediated-then-stored,
  transformed-but-not-stored, or deferred — surfaced in the run summary and exit status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every sample resource that can be made storable without fabricating or dropping a
  clinical value is stored — raising the stored count from the 39/50 pre-remediation baseline to the
  full storable set (targeting 50/50 for the current sample, given the chosen stratum-pruning
  strategy).
- **SC-002**: 100% of storability remediations are lever-based or structure-only; zero resources are
  stored with any fabricated clinical value.
- **SC-003**: 100% of applied remediations are both logged at runtime and documented in
  `known-validation-issues.md`; zero remediations are silent.
- **SC-004**: Re-running persistence produces zero duplicate resources and zero content diffs for
  resources already stored.
- **SC-005**: Zero new HL7-validator error signatures appear versus the committed conformance baseline
  after remediation.
- **SC-006**: After any run, an operator can determine from the run's own summary and exit status how
  many resources per type were stored, remediated, or deferred — without reading Aidbox server logs.

## Assumptions

- The target Aidbox runs with its FHIR Schema validation engine enabled; disabling it is treated as
  out of scope and prohibited (it breaks the FHIR REST API per `known-validation-issues.md`).
- Cause 1 is handled by the box enabling the reference-skip capability plus the processor's existing
  `config.server.validation_skip` (e.g. `["reference"]`); this feature reuses that mechanism rather
  than adding a new one.
- Cause 3 is handled server-side by the target box leaving its terminology service unconfigured, so
  the processor does not transform terminology displays. If a terminology service is later configured
  on the box, Cause 3 resurfaces and would require its own remediation decision (out of scope here).
- Per the product decision recorded for this feature, an unlabeled stratifier stratum (no `value`, no
  `component`) is treated as malformed structure rather than clinical content; its removal is
  permitted provided the removal is logged with any counts it carried.
- The current sample set is the 50 resources from the 2026-06-12 submission run; real-world data is
  assumed to share the same resource shapes and rejection causes.
- MeasureReports are in scope for storage even though the first materialized analytics view is
  Patient; storability is pursued for all processed resource types, not only those with a
  ViewDefinition today.
- Conformance remains owned by the HL7 validator gate (`scripts/validate.sh` +
  `test/conformance-baseline.sigs`); this feature does not change that gate, only the Aidbox write
  path.
