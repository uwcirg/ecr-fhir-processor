# Phase 0 Research: Surface Component & Coded Measurements in the Observation View

**Feature**: 007-observation-component-values | **Date**: 2026-07-07

All unknowns were resolvable from the existing codebase, the `test/input/` fixtures, and the
002/004 precedent. No `NEEDS CLARIFICATION` remains. Format: Decision / Rationale / Alternatives.

---

## R1 — Delivery mechanism: edit one existing view file, no code change

**Decision**: Deliver by editing `viewdefinitions/observation.ViewDefinition.json` only. Do not
touch `publish_views.py`, `fhir_common.py`, `process.py`, config, or the test suite.

**Rationale**: `publish_views.py::discover_viewdefinitions()` globs `viewdefinitions/*.json` and
PUTs + `$materialize`s each with per-view failure isolation (established 002/004). The Observation
view is already discovered and materialized; adding columns to it is a pure data-file edit. The
directory-driven `tests/test_viewdefinition.py` (004 R8) already iterates every checked-in view and
asserts JSON validity, required fields, a `getResourceKey()` key column, the provenance `where`, and
a single-valued `cms_measure` column — all preserved by this edit, so no test change is needed.

**Alternatives considered**: A new companion view (e.g. `observation_component_view`) — rejected:
splits one-row-per-Observation analytics across two tables for no benefit; the clarified design puts
the triads on the same row. Code-side flattening in `process.py` — rejected: violates "views are the
analytics deliverable" (Principle VII) and would change persisted output.

---

## R2 — Positional second component: FHIRPath expression (**the one real risk**)

**Decision**: Source the two triads **positionally** with indexers as the **primary** expression:
- triad 1 from `component[0]`, triad 2 from `component[1]`.

Document a **fallback** for the two-component case in case Aidbox's SQL-on-FHIR FHIRPath does not
accept/evaluate the indexer: triad 1 → `component.first()...`, triad 2 → `component.last()...`.
The **authoritative resolver is the server-acceptance gate** (Principle III gate 2): if `PUT` +
`$materialize` succeed and the quickstart query returns the expected Systolic/Diastolic values, the
primary expression stands; if the indexer is rejected or yields null, switch to the fallback (a
one-line-per-column edit) and re-run.

**Rationale**:
- The clarified design (spec 2026-07-07) is explicitly **positional and generic** — "first nested
  part → triad 1, second → triad 2," disambiguated by the `component_display` label — so the
  expression must select by position, not by measurement code.
- `component[0]` / `component[1]` is the natural, extensible way to express "the Nth component"
  (a third triad would be `component[2]`), and indexers are core FHIRPath. Aidbox ships a complete
  FHIRPath engine, so indexer support is **likely** — but **not demonstrated anywhere in this
  repo**: every checked-in view (patient, encounter, organization, servicerequest, …) uses only
  `.first()`, `.where()`, `.ofType()`, and `.coding.first()`. That absence is why this is flagged as
  the feature's single risk and gated on server acceptance rather than assumed.
- The `.first()`/`.last()` fallback is guaranteed to work for the **exactly-two-component**
  blood-pressure panel present in the fixtures (`.last()` = the second when there are two), and
  `.first()` is already proven in this repo. Its weakness (it does not generalize cleanly to a third
  positional slot) is acceptable because it is only a fallback for the present two-component data.

**Alternatives considered**:
- **Match components by measurement code** (`component.where(code.coding.exists(code='8480-6'))` for
  Systolic, `'8462-4'` for Diastolic) — **rejected**: the user explicitly did *not* want
  type-specific columns; this would hard-code blood-pressure LOINC codes into generic slots and
  defeat the "generic, extensible, self-describing" intent. (Noted only as the last-resort option if
  *both* indexer and `.first()/.last()` were somehow unsupported — not expected.)
- **`forEach` over `component`** to emit one row per component — **rejected**: violates the
  one-row-per-Observation invariant (FR-003) and the rest of the view set.
- **`.skip(1).first()` for the second** — rejected: `skip` is not in the SQL-on-FHIR required subset
  and is no more likely supported than the indexer, while being less readable than `.last()`.

---

## R3 — Triad column definitions (paths + types)

**Decision**: Add six component columns; each triad = display (string) + value (decimal) + unit
(string). Primary (indexer) form:

| Column | Path (primary) | Type |
|--------|----------------|------|
| `component1_display` | `component[0].code.coding.first().display` | string |
| `component1_value` | `component[0].value.ofType(Quantity).value` | decimal |
| `component1_unit` | `component[0].value.ofType(Quantity).unit` | string |
| `component2_display` | `component[1].code.coding.first().display` | string |
| `component2_value` | `component[1].value.ofType(Quantity).value` | decimal |
| `component2_unit` | `component[1].value.ofType(Quantity).unit` | string |

**Rationale**: Mirrors the repo's proven idioms for the value/unit/display of a coded quantity
(`code.coding.first().display`, `value.ofType(Quantity).value/.unit` — already used for the
top-level Observation value and across other views). `decimal` matches the existing `value_quantity`
column type; the fixture BP values (128, 88) are integers but decimal is the correct, lossless type.
Absent value/unit/display → null (FR-004), never fabricated. The fallback swaps `component[0]`→
`component.first()` and `component[1]`→`component.last()` with identical suffixes.

**Alternatives considered**: Adding component code/system columns too — rejected: the clarified
design is a strict **triad** (display, value, unit); code/system can be added later as a reviewable
refinement if the analytics team asks.

---

## R4 — Coded-value case: add `value_code_display`

**Decision**: Add one column `value_code_display` with path
`value.ofType(CodeableConcept).coding.first().display` (string), placed immediately after the
existing `value_code`. Keep `value_code` (the code) unchanged.

**Rationale**: The clarification requested "coding.code (already included) as well as coding.display
(needs to be added)." The depression-screening Observations (LOINC 73831-0 / 73832-8) carry a coded
result whose bare code is currently unreadable without a lookup; the display makes the row
self-interpretable. The path mirrors the existing `value_code`
(`value.ofType(CodeableConcept).coding.first().code`) and the `code_display`/`*_display` idiom used
throughout the view set.

**Alternatives considered**: A coding `system` column — rejected as out of the clarified scope
(code + display only); addable later.

---

## R5 — Testing: existing suite covers it; e2e via quickstart

**Decision**: No new or edited test file. Rely on (1) the directory-driven
`tests/test_viewdefinition.py` shape suite (already covers the edited file) and (2) the e2e
quickstart the user runs against Aidbox.

**Rationale**: The shape suite asserts structural conformance for *every* view in the directory; the
seven added columns keep every asserted property (valid JSON, required fields, `getResourceKey()`
key column, provenance `where`, single-valued `cms_measure`). Value-level correctness (the actual
Systolic/Diastolic numbers, the coded display, no regression, unchanged row count) is only knowable
against a server holding the processed fixtures — that is the quickstart's job and the Principle III
gate-2 authority. `tests/test_discovery.py`'s fixture count is unaffected (it counts eCR inputs, not
views — verified in 006).

**Alternatives considered**: A unit test asserting the specific new column names/paths — rejected as
brittle against a **reviewable** default column set; the directory-driven structural suite plus the
e2e query is the established balance (002/004).

---

## R6 — Conformance & baseline: no impact

**Decision**: No change to `test/conformance-baseline.sigs`; the HL7 `validator_cli.jar` gate does
not apply.

**Rationale**: This feature changes **no processed resource** — it only reads existing persisted
Observations through a view — so the conformance-signature baseline that tracks processed-output
fidelity is untouched (consistent with the memory note that the baseline tracks fixtures/output, not
view files). A `ViewDefinition` is a SQL-on-FHIR logical-model resource outside the eCR/US-Core IG
set, so gate 1 (reference validator) is N/A (004 R5); the gate is Aidbox acceptance (gate 2).

**Alternatives considered**: Regenerating the baseline "to be safe" — rejected: nothing in
`test/input`/output changed, so a regeneration would be a no-op or spurious churn.

---

## Summary of decisions

| # | Decision |
|---|----------|
| R1 | Edit one view file; no code/test change; reuse the proven discover/PUT/`$materialize` path |
| R2 | Positional triads via `component[0]`/`component[1]` (primary) with `.first()`/`.last()` fallback; **server-acceptance gate resolves indexer support** |
| R3 | Six triad columns: display(string)/value(decimal)/unit(string) per component |
| R4 | Add `value_code_display` (`value.ofType(CodeableConcept).coding.first().display`); keep `value_code` |
| R5 | No test change — directory-driven shape suite + e2e quickstart cover it |
| R6 | No conformance-baseline change; HL7 validator N/A |
