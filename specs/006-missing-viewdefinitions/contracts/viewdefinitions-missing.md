# Contract: Missing-Resource ViewDefinitions (MeasureReport + Composition) & Measure Removal

**Feature**: `006-missing-viewdefinitions` | **Date**: 2026-07-06

Conformance contract for the two new `ViewDefinition` resource files and the removal of the
`Measure` view. The publish/materialize **CLI + server-operation** contract is unchanged from 002
(`specs/002-patient-viewdefinition/contracts/publish-materialize-cli.md`) — referenced, not
duplicated. This contract governs the **files**, not a new interface.

## C1 — Both new files are well-formed, discoverable ViewDefinitions

Each of `viewdefinitions/measurereport.ViewDefinition.json` and
`viewdefinitions/composition.ViewDefinition.json` MUST:

- Be valid JSON with `resourceType == "ViewDefinition"` and a unique, stable `id`
  (`measurereport`, `composition`) so `publish_views.discover_viewdefinitions()` picks it up and
  PUTs it to `[base]/ViewDefinition/{id}` (update-in-place).
- Declare `name` (`measurereport_view` / `composition_view`), `status` (`active`), `resource`
  (`MeasureReport` / `Composition`), and a non-empty `select` with at least one `column`.
- Include the resource-key column `{ "name": "id", "path": "getResourceKey()", "type": "string" }`.
- Include the top-level provenance `where` (FR-008) and a single-valued `cms_measure` column
  (FR-009), byte-for-byte consistent with the existing views.
- Contain no row-multiplying `forEach` (FR-011).

**Verification**: the existing directory-driven `tests/test_viewdefinition.py` (green), plus
`python3 -c "import json; json.load(open('viewdefinitions/<f>'))"`.

## C2 — MeasureReport view materializes one row per persisted MeasureReport

Against a server holding the processed fixtures, `[base]/ViewDefinition/measurereport/$materialize`
MUST succeed and `sof.measurereport_view` MUST return exactly one row per persisted first-class
`MeasureReport` bearing this processor's provenance tag, and zero rows for unrelated MeasureReports.
Columns MUST match [data-model.md](../data-model.md) Entity 1; the named population-count columns
(`initial_population`, `denominator`, `numerator`, …) MUST reflect the corresponding
`group.population.count` and be null where that population is absent (FR-010).

## C3 — Composition view materializes one row per promoted Composition, metadata-only

`[base]/ViewDefinition/composition/$materialize` MUST succeed and `sof.composition_view` MUST return
one row per promoted first-class `Composition`, provenance-scoped. Columns MUST match
[data-model.md](../data-model.md) Entity 2 and MUST NOT include any `section`/nested clinical column
(FR-005). Reference columns (`subject`, `encounter`, `author`, `custodian`) MUST be populated via
`getReferenceKey()` and equal the corresponding target views' `id` (research R4).

## C4 — Measure-scoped filtering works on both new views

Filtering either materialized view on `cms_measure = '<CMSxxx>'` MUST return only rows whose source
resource was attributed to that measure (consistent with 003-cms-measure-filter); un-attributed rows
MUST carry the `unknown` sentinel, not a fabricated code.

## C5 — The Measure view is removed and no longer published

`viewdefinitions/measure.ViewDefinition.json` MUST NOT exist after this feature.
`publish_views.py` MUST NOT publish or materialize a `Measure` view from this project's set. Any
pre-existing `sof.measure_view` on the server is orphaned by this change (it is never re-published);
removing it server-side is an operator action outside this file-only feature and MAY be noted in the
quickstart.

## C6 — Idempotent re-run, per-view failure isolation (reused, unchanged)

Re-running the publish/materialize step MUST update each new view in place (no duplicates) and
report success. A publish/materialize failure for either new view MUST be logged with the server's
reason, reflected in exit status, and MUST NOT prevent the other views from being attempted
(FR-013) — the existing behavior from 002/004, unchanged.

## C7 — Closure invariant

The set of `resource` target types across all `viewdefinitions/*.json` MUST equal the set of
resource types the processor persists first-class (SC-004; see data-model.md "Closure invariant").
No checked-in view MUST target a type the processor never persists (FR-003).

## Non-goals

- No change to `publish_views.py`, `fhir_common.py`, `process.py`, config, or the CLI surface.
- No HL7 `validator_cli.jar` gate for these files (ViewDefinitions are outside the eCR/US-Core IG
  set; gate is Aidbox `PUT` + `$materialize`, 004 R5).
- No flattening of Composition `section` content or MeasureReport `evaluatedResource`/`contained`.
- No synthesis of `Measure` resources to keep the old view populated (fabrication; Principle V).
