# Phase 1 Data Model: ViewDefinitions for the Remaining Resource Types

**Feature**: `004-remaining-viewdefinitions` | **Date**: 2026-06-16

Eleven new checked-in `ViewDefinition` resources, each flattening one already-persisted
first-class resource type into one analytics row per resource. This feature adds **no new persisted
FHIR data** and **no new code** — it defines views over resources `process.py` already persists, and
reuses the publish/materialize outcome model from 002 unchanged. Column→FHIRPath tables below are
the **informed, reviewable FR-002 defaults** (research.md R7), grounded in the `test/input/`
fixtures — not finalized analytics-team contracts.

---

## 0. Shared structure (every new view)

Each file `viewdefinitions/<type>.ViewDefinition.json` has:

| Field | Value | Why |
|-------|-------|-----|
| `resourceType` | `"ViewDefinition"` | resource kind |
| `id` | stable slug (e.g. `"condition"`) | PUT-by-id idempotency (FR-009) |
| `name` | `"<type>_view"` (e.g. `"condition_view"`) | becomes `sof.<type>_view` |
| `status` | `"active"` | lifecycle status |
| `resource` | the FHIR type (e.g. `"Condition"`) | selects first-class `Type/<id>` only (FR-003, VI) |
| `select` | one entry, `column[]` | columns below; **no row-multiplying `forEach`** (R3) |
| `where` | provenance filter (below) | scopes to this processor's resources (FR-005) |

**Provenance `where` (FR-005, identical to Patient)** — on every view:

```
meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()
```

**Universal columns on every view** (so all types join + filter the same way):

| Column | FHIRPath | Type | Null when |
|--------|----------|------|-----------|
| `id` | `getResourceKey()` | string | never (resource key) |
| `cms_measure` | `meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()` | code | resource has no cms-measure tag (else `unknown` sentinel) |

Per-type tables below list the **additional** columns (the `id` + `cms_measure` pair is implied).
Rules for all: select only first-class resources (FR-003, VI); absent field → null, no fabrication
(FR-007); multi-valued → deterministic `.first()` (FR-008); reference elements expose the reference
string, not the resolved target (R4).

---

## 1. Condition — `condition.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `clinical_status` | `clinicalStatus.coding.first().code` | code |
| `verification_status` | `verificationStatus.coding.first().code` | code |
| `category` | `category.first().coding.first().code` | code |
| `code` | `code.coding.first().code` | code |
| `code_system` | `code.coding.first().system` | string |
| `code_display` | `code.coding.first().display` | string |
| `subject` | `subject.reference` | string |
| `encounter` | `encounter.reference` | string |
| `onset_date_time` | `onset.ofType(dateTime)` | dateTime |
| `recorded_date` | `recordedDate` | dateTime |

## 2. Encounter — `encounter.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `status` | `status` | code |
| `class` | `class.code` | code |
| `type` | `type.first().coding.first().code` | code |
| `type_display` | `type.first().coding.first().display` | string |
| `subject` | `subject.reference` | string |
| `period_start` | `period.start` | dateTime |
| `period_end` | `period.end` | dateTime |
| `service_provider` | `serviceProvider.reference` | string |
| `location` | `location.first().location.reference` | string |

## 3. Observation — `observation.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `status` | `status` | code |
| `category` | `category.first().coding.first().code` | code |
| `code` | `code.coding.first().code` | code |
| `code_system` | `code.coding.first().system` | string |
| `code_display` | `code.coding.first().display` | string |
| `value_quantity` | `value.ofType(Quantity).value` | decimal |
| `value_unit` | `value.ofType(Quantity).unit` | string |
| `value_code` | `value.ofType(CodeableConcept).coding.first().code` | code |
| `value_string` | `value.ofType(string)` | string |
| `effective_date_time` | `effective.ofType(dateTime)` | dateTime |
| `subject` | `subject.reference` | string |
| `encounter` | `encounter.reference` | string |

## 4. Practitioner — `practitioner.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `npi` | `identifier.where(system = 'http://hl7.org/fhir/sid/us-npi').value.first()` | string |
| `identifier` | `identifier.first().value` | string |
| `name_family` | `name.first().family` | string |
| `name_given` | `name.first().given.first()` | string |
| `gender` | `gender` | code |
| `active` | `active` | boolean |

> `npi` falls back to null when no NPI identifier is present; `identifier` carries the first
> identifier of any system as a general-purpose business id.

## 5. Organization — `organization.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `identifier` | `identifier.first().value` | string |
| `name` | `name` | string |
| `type` | `type.first().coding.first().code` | code |
| `active` | `active` | boolean |
| `address_city` | `address.first().city` | string |
| `address_state` | `address.first().state` | string |
| `address_postal_code` | `address.first().postalCode` | string |

## 6. Location — `location.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `identifier` | `identifier.first().value` | string |
| `name` | `name` | string |
| `status` | `status` | code |
| `type` | `type.first().coding.first().code` | code |
| `address_city` | `address.first().city` | string |
| `address_state` | `address.first().state` | string |
| `address_postal_code` | `address.first().postalCode` | string |
| `managing_organization` | `managingOrganization.reference` | string |

## 7. Measure — `measure.ViewDefinition.json`  *(empty-until-loaded, research.md R5)*

| Column | FHIRPath | Type |
|--------|----------|------|
| `url` | `url` | string |
| `version` | `version` | string |
| `name` | `name` | string |
| `title` | `title` | string |
| `status` | `status` | code |
| `scoring` | `scoring.coding.first().code` | code |
| `identifier` | `identifier.first().value` | string |

> **No `Measure` resource is persisted by this project today** (fixtures only *reference* APHL
> Measure canonicals). This view materializes and returns **zero rows** until Measure resources are
> loaded — success, not failure (spec edge case). Authored now so it is ready when they arrive.

## 8. Bundle — `bundle.ViewDefinition.json`  *(metadata-only, FR-011 / research.md R6)*

| Column | FHIRPath | Type |
|--------|----------|------|
| `type` | `type` | code |
| `timestamp` | `timestamp` | instant |
| `identifier` | `identifier.value` | string |
| `entry_count` | `entry.count()` | integer |

> Container-level metadata only. Nested clinical content is **not** flattened here — it is promoted
> to first-class resources covered by the other views (Principle VI).

## 9. Procedure — `procedure.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `status` | `status` | code |
| `category` | `category.coding.first().code` | code |
| `code` | `code.coding.first().code` | code |
| `code_display` | `code.coding.first().display` | string |
| `subject` | `subject.reference` | string |
| `encounter` | `encounter.reference` | string |
| `performed_date_time` | `performed.ofType(dateTime)` | dateTime |

## 10. MedicationRequest — `medicationrequest.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `status` | `status` | code |
| `intent` | `intent` | code |
| `medication_code` | `medication.ofType(CodeableConcept).coding.first().code` | code |
| `medication_display` | `medication.ofType(CodeableConcept).coding.first().display` | string |
| `medication_reference` | `medication.ofType(Reference).reference` | string |
| `subject` | `subject.reference` | string |
| `encounter` | `encounter.reference` | string |
| `authored_on` | `authoredOn` | dateTime |
| `requester` | `requester.reference` | string |

## 11. ServiceRequest — `servicerequest.ViewDefinition.json`

| Column | FHIRPath | Type |
|--------|----------|------|
| `status` | `status` | code |
| `intent` | `intent` | code |
| `category` | `category.first().coding.first().code` | code |
| `code` | `code.coding.first().code` | code |
| `code_display` | `code.coding.first().display` | string |
| `subject` | `subject.reference` | string |
| `encounter` | `encounter.reference` | string |
| `authored_on` | `authoredOn` | dateTime |
| `requester` | `requester.reference` | string |

---

## 12. Reused: discovered work unit + per-view outcome (unchanged from 002)

The publish/materialize step's data model is **unchanged** — these eleven files are discovered and
processed exactly like Patient:

- **`ViewDefinitionFile`** (`publish_views.py`): `path`, `resource`, `view_id`, `name` — every
  `viewdefinitions/*.json` with `resourceType == "ViewDefinition"` + `id` becomes a unit; malformed
  / id-less files fail *that file* without blocking others (002 data-model §2).
- **`ViewOutcome` → `RunSummary`** (`fhir_common.py`): publish and materialize reported separately
  per view; exit `0` iff every view both published and materialized; any failure → non-zero, after
  all twelve attempted; an empty view (incl. Measure) is success (002 data-model §3).

No fields are added or changed; this section is a pointer, not a redefinition.

---

## Relationships

```text
viewdefinitions/<type>.ViewDefinition.json (repo, ×11 new + Patient)
      │  PUT [base]/ViewDefinition/<id>            (publish, update-in-place)
      ▼
ViewDefinition/<id> on Aidbox
      │  POST [base]/ViewDefinition/<id>/$materialize {type: view}
      ▼
sof.<type>_view (server-side flat view)  ◀── selects ── Type/<id> (first-class, provenance-tagged)
      │  SQL query (joinable across views on reference columns; filterable by cms_measure)
      ▼
DoH analyst (one row per resource, default columns, measure-scoped, provenance-scoped)
```
