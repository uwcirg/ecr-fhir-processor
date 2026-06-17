# Phase 0 Research: ViewDefinitions for the Remaining Resource Types

**Feature**: `004-remaining-viewdefinitions` | **Date**: 2026-06-16

Resolves the Technical-Context unknowns for authoring eleven new SQL-on-FHIR `ViewDefinition`
files and delivering them through the existing publish/materialize step. Each item is a
Decision / Rationale / Alternatives record. Builds directly on 002 (`research.md` R1–R6) and 003.

---

## R1 — No production code change: the step already generalizes

**Decision**: Deliver the eleven views as **files only**. Do not modify `publish_views.py`,
`fhir_common.py`, `process.py`, config, or the CLI.

**Rationale**: `publish_views.discover_viewdefinitions()` globs `viewdefinitions/*.json`, accepts
any file with `resourceType == "ViewDefinition"` and an `id`, and the run loop PUTs +
`$materialize`s each independently with per-view failure isolation (002 FR-011, verified in code).
Adding a resource type was explicitly designed to be "drop in a file, no code change" (002 Story 3,
`tests/test_viewdefinition.py::GeneralizationTest`). So the entire feature reduces to authoring
conformant files + asserting their shape.

**Alternatives considered**: A per-type subcommand or generator script — rejected: adds code and a
mechanism the existing discovery already provides; violates the simplicity the constitution favors.

## R2 — Per-view scoping mirrors Patient exactly (provenance `where` + `cms_measure` column)

**Decision**: Every new view carries (a) a top-level `where` filtering to this processor's
provenance tag, and (b) a `cms_measure` column reading the `…/cms-measure` tag — identical in form
to `patient.ViewDefinition.json`.

```
where: meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()
cms_measure: meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()  (type code)
```

**Rationale**: `process.py::stamp_resource` stamps **every** persisted top-level resource (not just
Patient) with the `processed-by`, `processed-on`, `source-file`, and `cms-measure` tags (process.py
line ~558, `stamp()` adds all four). So the provenance filter (002 FR-013) and the CMS-measure
column (003) generalize unchanged to all eleven types. Consistency means a cross-view join stays
within this project's data and keeps the measure dimension on every type.

**Alternatives considered**: Provenance filter only on some types — rejected: inconsistent scoping
breaks joins and SC-002. Omitting `cms_measure` on reference types (Practitioner/Organization/
Location) — rejected: they carry the tag too, and uniform columns make the measure filter total.

## R3 — One row per resource: deterministic single-valued reducers, no `forEach`

**Decision**: Each view is a single top-level `select.column[]` with no row-multiplying `forEach`;
multi-valued elements reduce with `.first()` (and `.coding.first()` for CodeableConcepts), so the
view stays one-row-per-resource (FR-008).

**Rationale**: Matches the Patient view and 002's R6 decision. Where the analytics team later wants
a child element row-multiplied (e.g. all of an Encounter's `location[]`), that is an explicit,
reviewable `forEach` added per-column later — not a default, to avoid surprising row fan-out.

**Alternatives considered**: `forEach` on `code.coding` / `category` by default — rejected: silently
multiplies rows; the analyst expects one row per resource unless they opt in.

## R4 — Choice types and references: typed primary variant + reference string

**Decision**: For `value[x]` / `medication[x]` / `performed[x]` etc., expose the
analytically-primary variant(s) as typed columns (e.g. Observation `value_quantity_value` +
`value_quantity_unit` from `value.ofType(Quantity)`, plus a `value_string` /
`value_codeable_code`); absent variants are null. Reference elements expose the **reference string**
(e.g. `subject.reference`), not the resolved target.

**Rationale**: SQL-on-FHIR columns are scalar; `ofType()` selects the present choice and yields null
otherwise (FR-007, never fabricate). Resolving references server-side is out of scope — the analyst
joins views on the reference key. Grounded in the fixtures: Observations carry `valueQuantity`;
MedicationRequest carries `medicationCodeableConcept`; Procedure carries `performedDateTime`.

**Alternatives considered**: One opaque JSON column per choice — rejected: defeats the point of a
flat view. Resolving references into denormalized columns — rejected: scope creep, brittle.

## R5 — Measure view is authored but empty-until-loaded; conformance gate is server acceptance

**Decision**: Author `measure.ViewDefinition.json` as requested, but document that **no `Measure`
resource is persisted by this project today** — the fixtures contain MeasureReports that only
*reference* APHL chronic-ds `Measure` canonicals. The view will return **zero rows** until Measure
resources are loaded; that is success, not failure. The conformance gate for every view is **Aidbox
accepting the `PUT` and `$materialize` succeeding** (Principle III gate 2), not `validator_cli.jar`.

**Rationale**: Survey of `test/input/` across all fixtures: `Measure` count = 0; `MeasureReport`
references `…/Measure/ControllingHighBloodPressureFHIR|0.0.002` etc. An empty view materializes
fine and the step reports success (spec edge case; 002 data-model §3). Authoring it now satisfies
the user's explicit request and means the view is ready the moment Measure resources arrive.

**Alternatives considered**: Omit the Measure view — rejected: the user explicitly listed it.
Synthesize Measure resources from MeasureReport references — rejected: fabrication (Principle V).

## R6 — Bundle view is metadata-only

**Decision**: `bundle.ViewDefinition.json` exposes only Bundle-level metadata —
`getResourceKey()`, `type`, `timestamp`, `identifier`, and an `entry_count`
(`entry.count()`) — plus provenance/`cms_measure`. It does **not** flatten nested entries (FR-011).

**Rationale**: A Bundle is a container; its clinical content is already promoted to first-class
resources covered by the other views (Principle VI). Flattening `entry[]` would both row-multiply
and duplicate data already viewable elsewhere. The metadata view lets analysts account for the
persisted container resources (how many entries, what type/timestamp) without re-deriving content.

**Alternatives considered**: `forEach entry.resource` — rejected: row fan-out + duplicates the
other views. Omit Bundle entirely — rejected: the user listed it; metadata is a coherent, thin view.

## R7 — Per-type default column sets are informed, reviewable defaults grounded in the fixtures

**Decision**: Derive each view's default columns from the fields actually present on that resource
type in `test/input/` (see [data-model.md](./data-model.md) for the column→FHIRPath tables). Treat
them as reviewable defaults flagged for analytics-team confirmation, exactly as Patient under
FR-002 — not a finalized contract.

**Rationale**: The request named the resource types but not the columns. Grounding defaults in
observed fixture shapes (e.g. Condition: clinicalStatus/verificationStatus/category/code/subject/
onsetDateTime/recordedDate; Encounter: status/class/type/period/serviceProvider/location/subject)
yields immediately useful, non-fabricated views while leaving column refinement to a cheap later
edit. Honors Principle VII's intent without blocking on a column list the request omitted.

**Alternatives considered**: Ship minimal id-only views and wait for the column list — rejected:
delivers little value and still needs the same later edit. Exhaustively expose every element —
rejected: noisy, and many elements are absent on the fixtures (would be all-null columns).

## R8 — Generic, directory-driven unit tests (one assertion suite covers all current and future views)

**Decision**: Extend `tests/test_viewdefinition.py` so the shape assertions iterate over **every**
`viewdefinitions/*.json` file: valid JSON; required fields
(`resourceType`/`id`/`name`/`status`/`resource`/non-empty `select`); a `getResourceKey()`-based key
column; the provenance `where` filter; no row-multiplying `forEach`; and a single-valued
`cms_measure` column for the clinical/reference types. Keep the existing Patient-specific column
assertions.

**Rationale**: A directory-driven suite means the twelfth (and thirteenth…) view is covered with no
new test — consistent with the discovery design (R1) and SC-006. Aidbox-specific FHIRPath validity
is proven by the quickstart e2e (`$materialize` success), not by unit tests (R5 gate).

**Alternatives considered**: One hand-written test per view — rejected: repetitive and forgets new
files. Asserting exact column sets per type in unit tests — rejected: columns are reviewable
defaults expected to change; over-specifying them makes the test brittle. (Per-type columns are
asserted loosely — key column + provenance + cms_measure presence — not pinned exhaustively.)

---

## Summary of decisions

| # | Decision |
|---|----------|
| R1 | Files only — the existing publish step already auto-discovers; no production code change |
| R2 | Every view reuses Patient's provenance `where` + `cms_measure` column (all types are stamped) |
| R3 | One row per resource: `.first()` reducers, no default `forEach` |
| R4 | Choice types → typed primary variant via `ofType()`; references → reference string |
| R5 | Measure view authored but empty-until-loaded; gate = Aidbox `PUT` + `$materialize` |
| R6 | Bundle view is metadata-only (type/timestamp/identifier/entry_count) |
| R7 | Per-type columns are informed, reviewable defaults grounded in the fixtures |
| R8 | Directory-driven unit tests cover every present and future ViewDefinition file |

No `NEEDS CLARIFICATION` remains.
