# Contract: `cms_measure` column on the Patient ViewDefinition

**Feature**: `003-cms-measure-filter` | **File**: `viewdefinitions/patient.ViewDefinition.json`

Adds one analyst-facing column so the flattened Patient view can be filtered to a single CMS
measure with one predicate (FR-009, SC-003). This is an **addendum** to the
[002 Patient ViewDefinition contract](../../002-patient-viewdefinition/contracts/viewdefinition-patient.md);
all of that contract's rules (one row per patient, first-class only, provenance `where` filter,
never fabricate, stable `id` for idempotent PUT) remain in force unchanged.

## The added column

Appended to `select[0].column[]`:

```json
{
  "name": "cms_measure",
  "path": "meta.tag.where(system = 'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()",
  "type": "code"
}
```

## Conformance rules

- **VC-1 (column present)**: the published Patient ViewDefinition MUST include a column named
  `cms_measure` reading the cms-measure tag's `code` via the system in
  [cms-measure-tag.md](./cms-measure-tag.md) (C-1).
- **VC-2 (one row per patient preserved)**: the path MUST end in `.first()` (single-valued
  reducer) so the column does not multiply rows — a resource carries exactly one cms-measure
  tag (tag contract C-5), so `.first()` is exact, not lossy. No `forEach`.
- **VC-3 (no measure `where` filter)**: the ViewDefinition MUST NOT add a `where` clause that
  restricts to one measure — filtering to a measure is the analyst's predicate on this column;
  the view stays single and measure-agnostic (R7). (The existing provenance `where` from 002
  FR-013 is retained as-is.)
- **VC-4 (null when absent)**: a Patient without the tag (e.g. persisted before this feature and
  not yet re-processed) yields `null` in this column, not an error — consistent with the view's
  never-fabricate rule (002 FR-010).
- **VC-5 (open-ended values)**: the column surfaces whatever concrete `CMS<n>` or `unknown` the
  resource carries; it does not gate on the enumerated set, so a future measure appears without
  a view edit.

## Query the contract enables (the point of the feature)

```sql
-- one measure
SELECT * FROM patient_view WHERE cms_measure = 'CMS165';
-- the un-attributed bucket
SELECT * FROM patient_view WHERE cms_measure = 'unknown';
-- distribution across measures
SELECT cms_measure, count(*) FROM patient_view GROUP BY cms_measure;
```

## Test expectations

- Unit (extend `tests/test_viewdefinition.py`): the file parses as JSON and `select[0].column[]`
  contains a `cms_measure` column whose `path` references the cms-measure `system` and ends in
  `.code.first()`; `type` is `code`.
- E2E (quickstart): after re-processing fixtures and re-publishing the view, a query filtering
  `cms_measure = 'CMS165'` returns exactly the CMS165-sourced patients and excludes CMS122
  (SC-001, SC-003).
