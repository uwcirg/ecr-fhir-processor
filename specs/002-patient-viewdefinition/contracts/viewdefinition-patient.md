# Contract: Patient ViewDefinition resource

**Feature**: `002-patient-viewdefinition` | **File**: `viewdefinitions/patient.ViewDefinition.json`

This is the analytics contract for Patient demographics: a checked-in, version-controlled
SQL-on-FHIR `ViewDefinition` (as implemented by Aidbox) that flattens first-class `Patient`
resources to **one row per patient** with the default DoH demographic columns. Authoritative
column→FHIRPath mapping and null/selection rules: [../data-model.md](../data-model.md) §1;
rationale: [../research.md](../research.md) R6.

## Conformance

- MUST be valid JSON with `resourceType: "ViewDefinition"`, and required fields `id`, `name`,
  `status`, `resource: "Patient"`, and a non-empty `select` (FR-001).
- MUST conform to the SQL-on-FHIR `ViewDefinition` spec **as Aidbox implements it**; the
  authoritative gate is Aidbox accepting the `PUT` and `$materialize` succeeding (research.md R5).
  The HL7 `validator_cli.jar` does not apply to this resource.
- MUST select only from first-class `Patient/<id>` resources (FR-003); MUST NOT depend on Bundle
  content (Principle VI).
- MUST yield exactly one row per Patient: no row-multiplying `forEach`; multi-valued elements
  reduced with `.first()` (deterministic single-valued selection).
- MUST NOT fabricate values: a missing backing field → null column (FR-010).

## Stable identity (idempotency)

- `id` MUST be a stable slug (e.g. `"patient"`) so the publish step's `PUT
  [base]/ViewDefinition/<id>` updates in place — re-runs never create a duplicate view
  (FR-005, SC-003).
- `name` (e.g. `"patient_view"`) determines the materialized object name in Aidbox's `sof`
  schema (`sof.patient_view`).

## Shape (illustrative skeleton — not the full resource)

```json
{
  "resourceType": "ViewDefinition",
  "id": "patient",
  "name": "patient_view",
  "status": "active",
  "resource": "Patient",
  "select": [
    {
      "column": [
        { "name": "id",          "path": "getResourceKey()",                      "type": "string" },
        { "name": "mrn",         "path": "identifier.where(type.coding.exists(code='MR')).value.first()", "type": "string" },
        { "name": "name_family", "path": "name.first().family",                   "type": "string" },
        { "name": "name_given",  "path": "name.first().given.first()",            "type": "string" },
        { "name": "gender",      "path": "gender",                                "type": "code" },
        { "name": "birth_date",  "path": "birthDate",                             "type": "date" },
        { "name": "deceased",    "path": "deceased.ofType(boolean)",              "type": "boolean" },
        { "name": "race_code",          "path": "extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-race').extension('ombCategory').value.ofType(Coding).code.first()", "type": "code" },
        { "name": "race_display",       "path": "extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-race').extension('ombCategory').value.ofType(Coding).display.first()", "type": "string" },
        { "name": "ethnicity_code",     "path": "extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity').extension('ombCategory').value.ofType(Coding).code.first()", "type": "code" },
        { "name": "ethnicity_display",  "path": "extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity').extension('ombCategory').value.ofType(Coding).display.first()", "type": "string" },
        { "name": "address_city",        "path": "address.first().city",         "type": "string" },
        { "name": "address_state",       "path": "address.first().state",        "type": "string" },
        { "name": "address_postal_code", "path": "address.first().postalCode",   "type": "string" }
      ]
    }
  ]
}
```

> The exact FHIRPath dialect details (e.g. `getResourceKey()`, `ofType()`) are settled against
> Aidbox during the quickstart e2e; the column **names** above are the stable contract.

## Default-but-reviewable

The column set is the FR-002 informed default, not a finalized analytics-team contract (spec
Assumptions; checklist note). Adjusting it later is an edit to this file + re-running the publish
step — no change to the mechanism.

## Test expectations

- Unit: file parses as JSON and carries the required fields (`resourceType`/`id`/`name`/`status`/
  `resource`/non-empty `select`).
- E2E (quickstart): after publish + `$materialize` against a server holding N Patients, the
  resulting `sof.patient_view` returns exactly N rows, columns populated from the source Patient
  or null where the source field is absent (SC-001, SC-002, SC-005).
