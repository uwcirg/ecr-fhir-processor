# Phase 1 Data Model: ViewDefinitions for the Missing Persisted Resource Types

**Feature**: `006-missing-viewdefinitions` | **Date**: 2026-07-06

Two new SQL-on-FHIR `ViewDefinition` resources and one removal. The publish/materialize outcome
model, the provenance `where`, and the `cms_measure` column are **reused unchanged** from
002/003/004 — this document specifies only what is new. Column sets are **informed, reviewable
defaults** grounded in the `test/input/` fixtures (FR-004/FR-005), not finalized analytics-team
contracts.

Shared, unchanged conventions (see 004 data-model / research R2–R4):

- **Resource key**: every view's identity column is `{ "name": "id", "path": "getResourceKey()", "type": "string" }`.
- **Provenance `where`** (FR-008): `meta.tag.where(system = '…/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()`.
- **CMS-measure column** (FR-009): `meta.tag.where(system = '…/CodeSystem/cms-measure').code.first()` (type `code`).
- **Reference columns** (FR-006 / research R4): `<ref>.getReferenceKey()` — never raw `.reference`
  (null under Aidbox normalization).
- **One row per resource** (FR-011): single top-level `select.column[]`, no row-multiplying
  `forEach`; multi-valued elements reduced with `.first()` or named `.where(...)`.

---

## Entity 1 — `measurereport.ViewDefinition.json` (NEW)

- **id**: `measurereport` · **name**: `measurereport_view` · **status**: `active` · **resource**: `MeasureReport`
- **Grain**: one row per first-class `MeasureReport` persisted by this project (via `KIND_MEASURE_REPORT`).
- **Source of truth for defaults**: the 7 standalone `MeasureReport_*.json` fixtures — `type=individual`,
  a single `group` with a proportion-measure `population[]`, a `measure` canonical, `subject`, `date`,
  `period`, and `improvementNotation`.

| Column | FHIRPath | Type | Notes |
|--------|----------|------|-------|
| `id` | `getResourceKey()` | string | Resource key |
| `measure` | `measure` | string | Canonical URL (e.g. `…/ControllingHighBloodPressureFHIR\|0.0.002`) |
| `status` | `status` | code | e.g. `complete` |
| `type` | `type` | code | e.g. `individual` |
| `subject` | `subject.getReferenceKey()` | string | → `patient_view.id` |
| `reporter` | `reporter.getReferenceKey()` | string | Null when absent (FR-010) |
| `period_start` | `period.start` | dateTime | |
| `period_end` | `period.end` | dateTime | |
| `improvement_notation` | `improvementNotation.coding.first().code` | code | e.g. `decrease` |
| `measure_score` | `group.first().measureScore.value` | decimal | Null on proportion-measure fixtures (no score) |
| `initial_population` | `group.first().population.where(code.coding.where(code='initial-population').exists()).count.first()` | integer | |
| `denominator` | `group.first().population.where(code.coding.where(code='denominator').exists()).count.first()` | integer | |
| `denominator_exclusion` | `group.first().population.where(code.coding.where(code='denominator-exclusion').exists()).count.first()` | integer | |
| `denominator_exception` | `group.first().population.where(code.coding.where(code='denominator-exception').exists()).count.first()` | integer | Null when the report omits it |
| `numerator` | `group.first().population.where(code.coding.where(code='numerator').exists()).count.first()` | integer | |
| `numerator_exclusion` | `group.first().population.where(code.coding.where(code='numerator-exclusion').exists()).count.first()` | integer | Null when the report omits it |
| `cms_measure` | `meta.tag.where(system='…/cms-measure').code.first()` | code | Measure attribution |

- **`where`**: the standard provenance filter (above).
- **Design note (research R3)**: population is multi-valued; each named population is projected to its
  own scalar count column so the view stays one-row-per-resource and is directly usable for
  numerator/denominator math. A long-form `forEach group.population` view can be added later if the
  analytics team wants one-row-per-population.

## Entity 2 — `composition.ViewDefinition.json` (NEW, metadata-only)

- **id**: `composition` · **name**: `composition_view` · **status**: `active` · **resource**: `Composition`
- **Grain**: one row per promoted first-class `Composition` (via `KIND_MESSAGE` promotion).
- **Source of truth for defaults**: the eICR `Composition` promoted from each `message` Bundle's
  nested document Bundle — `status`, `type` (LOINC `55751-2` Public Health Case Report), `subject`,
  `encounter`, `date`, `author`, `title`, `custodian`.
- **Scope (FR-005)**: document-level metadata **only** — no `section[]` / nested clinical content.

| Column | FHIRPath | Type | Notes |
|--------|----------|------|-------|
| `id` | `getResourceKey()` | string | Resource key |
| `status` | `status` | code | e.g. `final` |
| `type_code` | `type.coding.first().code` | code | e.g. `55751-2` |
| `type_system` | `type.coding.first().system` | string | e.g. `http://loinc.org` |
| `type_display` | `type.coding.first().display` | string | e.g. `Public Health Case Report` |
| `category` | `category.first().coding.first().code` | code | Null when absent (FR-010) |
| `subject` | `subject.getReferenceKey()` | string | → `patient_view.id` |
| `encounter` | `encounter.getReferenceKey()` | string | → `encounter_view.id` |
| `date` | `date` | dateTime | Document date |
| `title` | `title` | string | |
| `author` | `author.first().getReferenceKey()` | string | 0..* → `.first()` reducer; → practitioner/org |
| `custodian` | `custodian.getReferenceKey()` | string | → `organization_view.id` |
| `cms_measure` | `meta.tag.where(system='…/cms-measure').code.first()` | code | Measure attribution |

- **`where`**: the standard provenance filter (above).

## Removal — `measure.ViewDefinition.json` (DELETE)

- Targets `Measure`, a resource type this pipeline never persists (004 R5; the file's own
  `description` documents it as empty-until-loaded). Deleted so the checked-in view set contains no
  view that can never return a row (FR-003, SC-003/SC-004).

## Reused entities (unchanged)

- **Publish/materialize outcome** — per-view `(view_id, publish_result, materialize_result, reason)`
  record surfaced by `publish_views.py` and reflected in exit status; now spans the updated view set
  with `measurereport` and `composition` added and `measure` gone. No change to the mechanism.
- **Materialized view** — server-side flattened table (`sof.measurereport_view`,
  `sof.composition_view`) produced by `$materialize`; one row per resource of its type.

## Closure invariant (SC-004)

After this feature, `{ target resourceType of each viewdefinitions/*.json }` equals `{ resourceType
the processor persists first-class }`:

```
persisted first-class : Patient, Condition, Encounter, Observation, Practitioner, Organization,
                        Location, Procedure, MedicationRequest, ServiceRequest, Bundle,
                        MeasureReport, Composition
view targets (after)  : Patient, Condition, Encounter, Observation, Practitioner, Organization,
                        Location, Procedure, MedicationRequest, ServiceRequest, Bundle,
                        MeasureReport, Composition
```

`MessageHeader` (present in input, never individually persisted — lives only inside the persisted
message Bundle) is correctly on neither side.
