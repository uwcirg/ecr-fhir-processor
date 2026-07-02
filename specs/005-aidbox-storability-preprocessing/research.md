# Phase 0 Research: Aidbox Storability Pre-Processing

All decisions below are grounded in the existing codebase (`process.py`, `fhir_common.py`), the
`test/input/` fixtures, the 2026-06-12 live-run logs, and the Aidbox behavior already documented in
`known-validation-issues.md` → "Aidbox ingestion-time validation". No `NEEDS CLARIFICATION` remained
after this pass.

---

## R1 — Cause 1 (reference target-profile conformance): reuse the existing header, no code change

- **Decision**: Rely on the **existing** per-request `aidbox-validation-skip: reference` header,
  which the processor already emits when `config.server.validation_skip` contains `"reference"`
  (`fhir_common.py:259–260`, driven by `config.server.validation_skip`, `fhir_common.py:219`). No
  resource content is altered (FR-003).
- **Rationale**: Constitution Principle VIII mandates non-mutating levers before any transform. This
  lever is per-request (surgical), already wired, and **empirically confirmed** on 2026-06-12 to clear
  all three Cause-1 rejections (Observation ×2 + MedicationRequest ×1), moving the run 39→42. The box
  must have `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true`; that is a documented deployment assumption, not
  processor work.
- **Alternatives considered**: (a) *Rewrite the referenced resource's `meta.profile` to match the
  referencing element's `targetProfile`* — rejected: mutates clinical/provenance content and could
  regress HL7 conformance (FR-009). (b) *Drop the offending reference* — rejected: silently drops
  clinical linkage (Principle V).

## R2 — Cause 3 (terminology display-name binding): box-side config, no transform

- **Decision**: Rely on the target box leaving `AIDBOX_TERMINOLOGY_SERVICE_BASE_URL` **unset** (binding
  validation skipped box-wide). The processor MUST NOT rewrite terminology `display` values (FR-004).
- **Rationale**: This is a box-side non-mutating lever (Principle VIII). The mismatched display
  (`decrease` → "Lower score indicates better quality") is upstream supplier data of the same class the
  HL7 gate already tolerates; rewriting it would mutate content the processor does not own.
- **Alternatives considered**: (a) *Rewrite `display` to the canonical string* — rejected: mutating
  content to satisfy a binding is exactly the kind of fabrication Principle V/VIII forbids, and it is
  unnecessary because the box lever exists. (b) *Strip the `display`* — rejected: silent drop.
- **Boundary**: If a terminology server is later configured on the box, Cause 3 resurfaces and needs
  its own remediation decision — explicitly **out of scope** here (spec Assumptions).

## R3 — Cause 2 (`mrp-2`): the only cause needing a transform; what the transform is

- **Decision**: Remove each stratifier `stratum` for which **neither `value` nor `component` is
  present** (a `population`-only stratum). Leave every conforming stratum (has `value` xor `component`)
  and every other MeasureReport element untouched. The invariant is
  `group.stratifier.stratum.all(value.exists() xor component.exists())`; a `population`-only stratum
  violates it and Aidbox rejects with a hard 422 and **no** per-constraint skip lever exists.
- **Rationale (non-fabricating, structure-only)**: A stratum's `value`/`component` **is** its
  stratification key — the label that says *which* sub-group the `population` counts describe. A stratum
  with neither key is an **unlabeled** bucket: its counts cannot be attributed to any stratum, so the
  element carries no interpretable clinical meaning. Removing it discards structurally-malformed
  scaffolding, not clinical content — the product decision recorded in the spec (Assumptions) and
  Principle VIII's explicit example. Because removal *does* discard whatever counts the stratum held,
  Principle V's "never silently" rule applies: **every removal is logged at WARNING with the removed
  stratum's population counts** (FR-006), so it is auditable, never silent.
- **Alternatives considered**: (a) *Fabricate a `value`* (e.g. a placeholder CodeableConcept) —
  rejected outright: inventing a stratification key is fabricating clinical meaning (Principle V, the
  hard line). (b) *Keep the stratum and disable the schema engine* — rejected: `BOX_FHIR_SCHEMA_VALIDATION=false`
  is a DO-NOT-USE engine selector that 404s every PUT (FR-014, `known-validation-issues.md`). (c)
  *Defer all MeasureReports* — rejected: a non-fabricating structure-only transform exists, so
  deferral (the fabrication-only escape hatch, FR-007) is not warranted; deferral would leave the last
  resource group unstored for no reason.

## R4 — Pruning scope: standalone AND nested-in-message-Bundle MeasureReports

- **Decision**: Apply the prune to **every MeasureReport the processor persists**: the standalone
  MeasureReport path (`_process_measure_report`, `process.py:635`) **and** MeasureReports nested inside
  the message/document Bundle on the message path (`_process_message`, `process.py:642`), in-place,
  **before** `_maybe_mirror` and the `PUT` (FR-005, FR-008).
- **Rationale**: The 2026-06-12 run shows the violation in **5 standalone + 3 nested** MeasureReports.
  A message Bundle is PUT **whole** (`process.py:655`); an unpruned nested MeasureReport makes Aidbox
  reject the entire Bundle (and its promoted Composition never lands cleanly). The spec Clarification
  (2026-07-01) resolved this explicitly: *all* MeasureReports, standalone and nested. Pruning before
  the mirror guarantees the `output/` bytes equal the PUT bytes (FR-008).
- **Alternatives considered**: *Prune only standalone MRs* — rejected: leaves the message Bundles
  rejected whole, contradicting FR-005 and the clarification.

## R5 — Single canonical representation (output == submitted bytes)

- **Decision**: The transform mutates the in-memory resource **once, on the write path, before**
  `_maybe_mirror(...)`. The mirrored `output/` file and the bytes PUT to Aidbox are therefore identical
  (FR-008). The `test/input/` fixtures are read-only and never edited (Principle III).
- **Rationale**: The spec Clarification (2026-07-01) chose a single representation over an
  Aidbox-only write-path transform, so an auditor comparing `output/` to what Aidbox stored sees no
  divergence. The existing pipeline already mirrors the *stamped* resource (`process.py:631`, `:638`,
  `:653`); inserting the prune just upstream of the mirror preserves that property.
- **Alternatives considered**: *Transform only on the Aidbox write path, keep the un-pruned resource in
  `output/`* — rejected by the clarification (would create a diff between emitted and stored bytes).

## R6 — Deferral + three-state exit code

- **Decision**: Extend the run accounting with two new outcome states beyond today's
  succeeded/failed/skipped (`fhir_common.py:66`): **remediated** (stored after a transform was applied)
  and **deferred** (a resource type isolated because only fabrication could store it). Replace the
  current two-state `exit_code` (`fhir_common.py:93`, `0 if failed==0 else 1`) with **three
  distinguishable states** (FR-012): `0` when every in-scope resource stored; a distinct non-zero code
  for **completed-with-deferrals** (expected/intentional); a separate non-zero code for
  **unexpected errors** (undocumented Aidbox rejection, transport failure). Deferral MUST NOT use the
  unexpected-error code.
- **Rationale**: FR-007/FR-012 and the 2026-07-01 clarification require distinguishing an *intentional*
  deferral from an *unexpected* failure so an operator can tell "we stored everything storable, one
  type was isolated by design" from "something broke." "remediated" makes SC-003/SC-006 reportable
  (how many were stored *because of* a transform).
- **Current sample**: **0 deferrals expected** — the stratum-pruning strategy makes all MeasureReports
  storable, so the sample targets exit `0` with a non-zero *remediated* count. The deferral path is a
  required mechanism (Principle V/VIII), exercised by unit tests rather than the sample.
- **Alternatives considered**: *Fold deferral into the existing `failed`/exit-1* — rejected: conflates
  an intentional, expected outcome with a real error, defeating FR-012's operator-visibility goal.

## R7 — No HL7 conformance regression (FR-009)

- **Decision**: After transforming, re-run the HL7 gate (`scripts/validate.sh` over the transformed
  `output/`, using `config.ig_versions`) and require **zero new signatures** vs. the committed
  `test/conformance-baseline.sigs`. Because the transform is part of the canonical output (FR-008), the
  baseline **MAY** be regenerated to *drop* signatures the prune legitimately removes, but MUST NOT
  gain any signature. Regeneration, when needed, uses the pinned validator version:
  `scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json`
  (see `known-validation-issues.md` → "delta vs. source baseline"). [[conformance-gate-baseline-stale]]
- **Rationale**: Principle VIII forbids a storability gain that regresses HL7 conformance. Removing a
  `population`-only stratum should not *introduce* a validator error (it removes a base-invariant
  violation, if anything); the gate proves that empirically each run. A DEQM/eCR profile could in
  principle require a stratum — R8 checks that.
- **Alternatives considered**: *Skip the HL7 gate on the transformed output* — rejected: FR-009
  requires proving no regression; the gate is cheap and already exists.

## R8 — Does removing a stratum break a profile requirement (DEQM / eCR)?

- **Decision**: Treat the DEQM/eCR MeasureReport profiles as **not requiring** the specific
  `population`-only stratum (they constrain populations and measure-scoring, not the presence of an
  unlabeled stratum), and let the FR-009 gate (R7) be the empirical arbiter: if the prune produced a
  new validator signature, the gate fails and the design is revisited. On the current fixtures the
  removed stratum is a supplier artifact (`group[0].stratifier[1].stratum[0]`), not a profile-mandated
  element.
- **Rationale**: The `mrp-2` violation is a **base-FHIR R4** invariant, and the offending stratum is
  the malformed one; conforming strata (with `value`/`component`) are retained, so the stratifier
  itself and its DEQM `extension-criteriaReference` populations survive. The no-regression gate (R7)
  makes this a checked assumption rather than a bet.
- **Alternatives considered**: *Statically model every DEQM/eCR stratum cardinality rule in code* —
  rejected as over-engineering; the HL7 validator already encodes those rules and is run as the gate.

---

## Summary of decisions

| # | Topic | Decision |
|---|-------|----------|
| R1 | Cause 1 (reference profile) | Reuse existing `aidbox-validation-skip: reference` header; no code, no content change |
| R2 | Cause 3 (terminology) | Rely on box-side unset terminology server; never rewrite `display` |
| R3 | Cause 2 (`mrp-2`) | Remove `value`+`component`-less strata; structure-only, non-fabricating, WARNING+counts |
| R4 | Prune scope | Standalone AND message-Bundle-nested MeasureReports, in-place before mirror+PUT |
| R5 | Canonical representation | Transform once on write path before mirror ⇒ `output/` bytes == PUT bytes; fixtures immutable |
| R6 | Deferral & exit codes | Add remediated + deferred states; three-state exit (0 / deferrals / unexpected error) |
| R7 | No conformance regression | HL7 gate over transformed output; zero new signatures; baseline may drop, never gain |
| R8 | Profile requirement check | DEQM/eCR don't mandate the malformed stratum; FR-009 gate is the empirical arbiter |
