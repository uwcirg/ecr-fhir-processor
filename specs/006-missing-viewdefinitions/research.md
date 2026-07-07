# Phase 0 Research: ViewDefinitions for the Missing Persisted Resource Types

**Feature**: `006-missing-viewdefinitions` | **Date**: 2026-07-06

Resolves the Technical-Context unknowns for adding a `MeasureReport` and a `Composition`
ViewDefinition and removing the mis-targeted `Measure` ViewDefinition. Each item is a
Decision / Rationale / Alternatives record. Builds directly on 002 (R1–R6) and 004 (R1–R8).

---

## R1 — No production code change: the step already generalizes

**Decision**: Deliver the two new views as **files only**, and remove one file. Do not modify
`publish_views.py`, `fhir_common.py`, `process.py`, config, the CLI, or any test.

**Rationale**: `publish_views.discover_viewdefinitions()` globs `viewdefinitions/*.json`, accepts
any file with `resourceType == "ViewDefinition"` and an `id`, and PUTs + `$materialize`s each with
per-view failure isolation (002 FR-011; 004 R1; verified in code). The shape suite in
`tests/test_viewdefinition.py` is directory-driven (004 R8), so the two new files are asserted with
no new test and the removed file simply drops out of iteration. Verified there is **no** test that
references the `measure` view by name, and `tests/test_discovery.py`'s `len(files) == 18` counts eCR
**input** fixtures (via `process.discover_inputs`), not view files — so neither the removal nor the
additions perturb it.

**Alternatives considered**: Editing `measure.ViewDefinition.json` in place to retarget it to
MeasureReport — rejected per the spec clarification (clean delete + new file, so file name matches
target type and git history reads as an intentional retire + add). Adding a generator/subcommand —
rejected: the discovery mechanism already covers "drop in a file."

## R2 — Per-view scoping mirrors the existing views exactly (provenance `where` + `cms_measure`)

**Decision**: Both new views carry (a) a top-level `where` filtering to this processor's provenance
tag, and (b) a `cms_measure` column reading the `…/cms-measure` tag — identical in form to every
existing view.

```
where: meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()
cms_measure: meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()  (type code)
```

**Rationale**: `process.py` stamps **every** persisted top-level resource with the `processed-by`,
`processed-on`, `source-file`, and `cms-measure` tags — including the standalone MeasureReport
(persisted via `KIND_MEASURE_REPORT`) and the promoted Composition (persisted via `KIND_MESSAGE`).
So the provenance filter (002 FR-013 / 004 R2) and the CMS-measure column (003) generalize unchanged
to both new types, keeping cross-view joins within this project's data and preserving the measure
dimension.

**Alternatives considered**: Omitting the provenance filter on MeasureReport/Composition — rejected:
inconsistent scoping breaks joins and SC-005. Omitting `cms_measure` — rejected: both types carry
the tag; uniform columns make the measure filter total across the whole view set.

## R3 — MeasureReport columns: named single-valued reducers over the single group, no `forEach`

**Decision**: `measurereport_view` is a single top-level `select.column[]` (one row per resource,
FR-011) exposing: `getResourceKey()`; `measure` (the canonical URL string); `status`; `type`;
`subject.getReferenceKey()`; `reporter.getReferenceKey()`; `period.start`; `period.end`;
`improvement_notation` (`improvementNotation.coding.first().code`); `measure_score`
(`group.first().measureScore.value`); and **named population-count columns** derived with
`.where(...)` reducers over `group.first().population`:

```
initial_population    : group.first().population.where(code.coding.where(code='initial-population').exists()).count.first()
denominator           : … code='denominator' …
denominator_exclusion : … code='denominator-exclusion' …
denominator_exception : … code='denominator-exception' …
numerator             : … code='numerator' …
numerator_exclusion   : … code='numerator-exclusion' …
```

plus `cms_measure` and the provenance `where`.

**Rationale**: The fixtures' MeasureReports are `type=individual` with a **single** `group` whose
`population[]` holds the CMS proportion-measure populations (`initial-population`, `denominator`,
`numerator`, `denominator-exclusion` observed; the other CQFM populations included defensively so
the column is null, not absent, when a report omits them). Population is inherently multi-valued;
projecting each named population to its **own scalar count column** keeps one row per resource
without a row-multiplying `forEach` (FR-011, mirrors 004 R3), and is exactly the shape an analyst
wants for measure math (numerator/denominator per report). `measureScore` is absent on the observed
proportion-measure fixtures, so that column is null there (FR-010, never fabricate) but present for
score-bearing reports. The pruning of value/component-less strata performed upstream (005) does not
touch `group.population`, so these columns are unaffected by that transform.

**Alternatives considered**: `forEach group.population` to get one row per population — rejected:
row-multiplies the MeasureReport and forces the analyst to re-pivot for numerator/denominator math;
an explicit unnest can be added later if the analytics team wants the long form. A single opaque
`populations` JSON column — rejected: defeats the flat view. Multiple groups (`group[1..]`) — not
present in the fixtures (`type=individual`, one group); `group.first()` is the deterministic reducer,
revisited only if a multi-group `subject-list` report is loaded.

## R4 — Composition is metadata-only; references via `getReferenceKey()`

**Decision**: `composition_view` exposes **document-level metadata only**: `getResourceKey()`;
`status`; `type` (`type.coding.first().code` + `type.coding.first().system` + `.display`);
`category` (`category.first().coding.first().code`); `subject.getReferenceKey()`;
`encounter.getReferenceKey()`; `date`; `title`; `author.first().getReferenceKey()`;
`custodian.getReferenceKey()`; plus `cms_measure` and the provenance `where`. It does **not** project
`section[]` or any nested clinical content (FR-005).

**Rationale**: The eICR `Composition` is the clinical-document header — its analytic value is
provenance/attribution (which patient, which encounter, which document type, authored/held by whom).
Its nested `section` content is copies of resources already promoted to first-class and covered by
the other views (Principle VI); flattening it would both row-multiply and duplicate. Reference
columns use `getReferenceKey()` (not raw `.reference`) so they equal the target views'
`getResourceKey()` ids and join directly — and because Aidbox normalizes `.reference` to null under
`$materialize` (004 R4 gotcha; see [[aidbox-reference-normalization-gotcha]]). `author` is 0..* so
`.first().getReferenceKey()` is the deterministic single-valued reducer (FR-011); a later `forEach`
can expose all authors if needed.

**Alternatives considered**: Flattening `section` with `forEach` — rejected: row fan-out +
duplicates the other views (FR-005 forbids it). A full-fidelity Composition view — considered in the
spec's clarification and **declined** (metadata-oriented chosen). Raw `.reference` string columns —
rejected: null under Aidbox normalization and carry a `Type/` prefix that breaks the join to
`getResourceKey()` ids.

## R5 — Remove the Measure view (targets a never-persisted type)

**Decision**: Delete `viewdefinitions/measure.ViewDefinition.json`. Do not replace it with an edited
file; add the separate `measurereport.ViewDefinition.json` instead.

**Rationale**: 004 R5 authored the Measure view but documented that **no `Measure` resource is ever
persisted by this project** — the fixtures contain MeasureReports that only *reference* APHL
chronic-ds `Measure` canonicals. Its own `description` says it "materializes and returns zero rows
until Measure resources are loaded." Since Measure resources are never produced by this pipeline, the
view is permanently empty and misleadingly implies Measure data exists on the server. Removing it
makes the checked-in view set satisfy the closure invariant (SC-004): every view targets a type the
processor actually persists. This is not a Principle V "silent drop" — the view held no queryable
rows, and the removal is explicit and documented.

**Alternatives considered**: Keep the empty Measure view alongside a new MeasureReport view (spec
clarification option B) — rejected by the project owner (chose "Remove Measure, add MeasureReport").
Repurpose the file in place (rename target) — rejected: the clarification chose a clean delete + new
file so the filename matches the target type. Load synthetic Measure resources to populate it —
rejected: fabrication (Principle V) and out of scope.

## R6 — Conformance gate is server acceptance; shape covered by the existing directory-driven tests

**Decision**: The conformance gate for the two new views is **Aidbox accepting the `PUT` and
`$materialize` succeeding** (Principle III gate 2), proven by the quickstart e2e. Pure structural
shape (required fields, resource-key column, provenance `where`, single-valued `cms_measure`) is
covered by the **existing** directory-driven `tests/test_viewdefinition.py` with no new test.

**Rationale**: A `ViewDefinition` is a SQL-on-FHIR logical-model resource, not an eCR/US-Core
profiled resource, so `validator_cli.jar` and `meta.profile` do not apply (004 R5). Aidbox-specific
FHIRPath validity (e.g. the `group.first().population.where(...).count` reducers) is only provable by
`$materialize` succeeding against the live server — the quickstart's job. The generic unit suite
guards the invariant shape every view must have; it already iterates the whole directory, so the two
new files are asserted and the removed file drops out automatically.

**Alternatives considered**: Adding hand-written per-view unit tests — rejected: repetitive, and the
directory-driven suite already covers the invariant shape (004 R8). Pinning the exact column sets in
unit tests — rejected: columns are reviewable defaults expected to change; over-specifying is brittle.

---

## Summary of decisions

| # | Decision |
|---|----------|
| R1 | Files only — add two, remove one; the existing publish step + directory-driven tests already cover it; no code/test change |
| R2 | Both new views reuse the standard provenance `where` + `cms_measure` column (both types are stamped) |
| R3 | MeasureReport: named single-valued population-count columns over `group.first()`, no `forEach`; measure_score + improvement_notation; reference keys |
| R4 | Composition: metadata-only (no `section`); references via `getReferenceKey()`; `author.first()` reducer |
| R5 | Remove the `Measure` view — it targets a never-persisted type and is permanently empty (004 R5) |
| R6 | Gate = Aidbox `PUT` + `$materialize`; structural shape covered by the existing directory-driven unit suite |

No `NEEDS CLARIFICATION` remains.
