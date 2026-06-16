# Contract: CMS-measure provenance tag

**Feature**: `003-cms-measure-filter` | **Producer**: `process.py` `stamp()` | **Consumers**: SQL-on-FHIR ViewDefinitions, `_tag` queries

The persisted, queryable attribution of each processed resource to its CMS quality measure.
This is the data contract downstream analytics rely on to filter by measure (FR-008). Authoritative
derivation and invariants: [../data-model.md](../data-model.md) §1–§2; rationale:
[../research.md](../research.md) R2, R5, R6.

## Tag shape

Added to `meta.tag[]` of **every resource the processor persists** (the same set that already
receives the `source-file` tag — FR-003), by the same `stamp()` call:

```json
{
  "system": "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure",
  "code": "CMS165",
  "display": "controllable-bp"
}
```

For a non-conforming filename:

```json
{
  "system": "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure",
  "code": "unknown",
  "display": "unknown measure"
}
```

## Conformance rules

- **C-1 (system)**: `system` MUST be the constant
  `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure` (`SYSTEM_CMS_MEASURE`),
  distinct from `source-file`/`processed-by`/`processed-on` (FR-002).
- **C-2 (code)**: `code` MUST be a normalized `CMS<digits>` (uppercase) or the sentinel
  `unknown` (FR-001, FR-004, FR-006). Never a raw filename fragment, never mixed case (SC-005).
- **C-3 (derivation)**: `code` MUST be derived solely from the input filename via the
  `^CMS\d+` (case-insensitive) rule; the parent directory MUST NOT be consulted for the value
  (single source of truth, R2).
- **C-4 (breadth)**: present on exactly the resources carrying `source-file` — Patient,
  Encounter, Condition, Observation (and other collection members), the standalone
  MeasureReport, the promoted eICR Composition, and the message/collection Bundles (FR-003).
- **C-5 (exactly one / idempotent)**: a resource MUST carry exactly one cms-measure tag;
  re-stamping replaces it in place (system is in `OWN_TAG_SYSTEMS`), never appends a second
  (FR-005, SC-002). This is what makes US3 re-attribution-on-rename safe.
- **C-6 (additive)**: adding the tag MUST preserve `meta.profile`, tags from other systems, and
  all clinical content; it MUST NOT introduce HL7-validator errors (an unknown-CodeSystem tag
  yields at most warnings — Principle II).
- **C-7 (display, optional but specified)**: `display` SHOULD be the slug for concrete codes and
  `unknown measure` for the sentinel, derived from the `MEASURE_SLUG_BY_CMS` crosswalk; it is
  informational and MUST NOT be used as a filter key (filter on `system`+`code`).

## Downstream filter recipes (informative)

- ViewDefinition column (Patient): see [viewdefinition-cms-column.md](./viewdefinition-cms-column.md).
- FHIR search by tag (any resource type):
  `GET [base]/Condition?_tag=https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure|CMS165`
- "Un-attributed" bucket:
  `…?_tag=https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure|unknown`

## Directory/filename disagreement (FR-007)

When a file's filename code is concrete and the directory slug maps to a *different* concrete
code, `discover_inputs` MUST log one WARNING per file naming both values; the filename code
wins for the tag. Filename `unknown` does not trigger the warning. See data-model §4 / research R3.

## Test expectations

- Unit (`tests/test_cms_measure.py`):
  - `cms_measure_from_filename` returns the table values in data-model §1 (concrete codes,
    case-normalization, `unknown` for non-matches).
  - `stamp()` adds exactly one cms-measure tag with the derived code; a second `stamp()` call
    (re-stamp) leaves exactly one (C-5); other tags and `meta.profile` survive (C-6).
  - the disagreement rule warns only for concrete-vs-different-concrete (C-3/§4).
- Validation (Principle III): re-run the feature-001 pipeline over `test/input/`; zero new
  HL7-validator errors introduced by the added tag (C-6).
