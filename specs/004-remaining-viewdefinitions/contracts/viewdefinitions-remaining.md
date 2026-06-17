# Contract: the eleven remaining ViewDefinition resources

**Feature**: `004-remaining-viewdefinitions`
**Files**: `viewdefinitions/{condition,encounter,observation,practitioner,organization,location,measure,bundle,procedure,medicationrequest,servicerequest}.ViewDefinition.json`

The analytics contract for the remaining resource types: eleven checked-in, version-controlled
SQL-on-FHIR `ViewDefinition`s (as implemented by Aidbox), each flattening first-class resources of
one type to **one row per resource** with the FR-002 default columns. Authoritative column→FHIRPath
mappings and null/selection rules: [../data-model.md](../data-model.md); rationale:
[../research.md](../research.md). The publish/materialize CLI + `PUT`/`$materialize`
server-operation contract is **unchanged** from
[../../002-patient-viewdefinition/contracts/publish-materialize-cli.md](../../002-patient-viewdefinition/contracts/publish-materialize-cli.md)
— this feature adds no CLI surface.

## Conformance (every one of the eleven)

- MUST be valid JSON with `resourceType: "ViewDefinition"` and required fields `id`, `name`,
  `status`, `resource: "<Type>"`, and a non-empty `select` (FR-001).
- MUST conform to the SQL-on-FHIR `ViewDefinition` spec **as Aidbox implements it**; the
  authoritative gate is Aidbox accepting the `PUT` and `$materialize` succeeding (research.md R5,
  R8). The HL7 `validator_cli.jar` does not apply to this resource.
- MUST select only from first-class `<Type>/<id>` resources (FR-003); MUST NOT depend on content
  nested inside an un-promoted Bundle (Principle VI). The Bundle view reads first-class Bundle
  resources' own metadata only (FR-011).
- MUST include a top-level `where` scoping to this processor's provenance tag
  (`meta.tag` system `…/processed-by`, code `ecr-fhir-processor`), version-agnostic, so unrelated
  resources of the same type on the same server are excluded (FR-005).
- MUST expose a `getResourceKey()` key column named `id` and a single-valued `cms_measure` column
  reading the `…/cms-measure` tag (FR-006) — the latter on every clinical/reference view so the
  measure filter is total across types.
- MUST yield exactly one row per resource: no row-multiplying `forEach`; multi-valued elements
  reduced with `.first()` / `.coding.first()` (FR-008).
- MUST NOT fabricate values: a missing backing field → null column (FR-007).

## Stable identity (idempotency)

- Each `id` is a stable slug (`condition`, `encounter`, …) so the publish step's
  `PUT [base]/ViewDefinition/<id>` updates in place — re-runs never create duplicate views (FR-009,
  SC-006).
- Each `name` (`condition_view`, …) determines the materialized object name in Aidbox's `sof`
  schema (`sof.condition_view`).

## Illustrative skeleton (Condition — others follow the same shape, columns per data-model.md)

```json
{
  "resourceType": "ViewDefinition",
  "id": "condition",
  "name": "condition_view",
  "status": "active",
  "resource": "Condition",
  "select": [
    { "column": [
      { "name": "id",                  "path": "getResourceKey()",                       "type": "string" },
      { "name": "clinical_status",     "path": "clinicalStatus.coding.first().code",     "type": "code" },
      { "name": "verification_status", "path": "verificationStatus.coding.first().code", "type": "code" },
      { "name": "category",            "path": "category.first().coding.first().code",   "type": "code" },
      { "name": "code",                "path": "code.coding.first().code",               "type": "code" },
      { "name": "code_system",         "path": "code.coding.first().system",             "type": "string" },
      { "name": "code_display",        "path": "code.coding.first().display",            "type": "string" },
      { "name": "subject",             "path": "subject.reference",                      "type": "string" },
      { "name": "encounter",           "path": "encounter.reference",                    "type": "string" },
      { "name": "onset_date_time",     "path": "onset.ofType(dateTime)",                 "type": "dateTime" },
      { "name": "recorded_date",       "path": "recordedDate",                           "type": "dateTime" },
      { "name": "cms_measure",         "path": "meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()", "type": "code" }
    ] }
  ],
  "where": [
    { "path": "meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by' and code = 'ecr-fhir-processor').exists()" }
  ]
}
```

> The exact FHIRPath dialect details (e.g. `getResourceKey()`, `ofType()`, `.count()`) are settled
> against Aidbox during the quickstart e2e (`$materialize` success). The column **names** above and
> in data-model.md are the stable contract.

## Per-view special cases

- **Measure** (`measure.ViewDefinition.json`): conformant and published/materialized like the rest,
  but expected to return **zero rows until Measure resources are loaded** — no Measure resource is
  persisted today (research.md R5). An empty view is success, not failure.
- **Bundle** (`bundle.ViewDefinition.json`): metadata-only (`type`, `timestamp`, `identifier`,
  `entry_count`); does not flatten nested entries (FR-011, research.md R6).

## Default-but-reviewable

Every column set is an FR-002 informed default (spec Assumptions; data-model.md; checklist note),
not a finalized analytics-team contract. Adjusting one later is an edit to that file + a re-run of
the publish step — no change to the mechanism.

## Test expectations

- **Unit** (`tests/test_viewdefinition.py`, extended generically over `viewdefinitions/*.json`,
  research.md R8): every file parses as JSON and carries the required fields
  (`resourceType`/`id`/`name`/`status`/`resource`/non-empty `select`), an `id` column using
  `getResourceKey()`, the provenance `where` filter, no row-multiplying `forEach`, and a
  single-valued `cms_measure` column (clinical/reference views).
- **E2E** (quickstart): after publish + `$materialize` against a server holding the processed
  fixtures, each `sof.<type>_view` returns one row per persisted resource of that type, columns
  populated from the source or null where absent, only processor-persisted rows present (SC-002),
  and `cms_measure` filterable (SC-005). The Measure view materializes and returns zero rows.
