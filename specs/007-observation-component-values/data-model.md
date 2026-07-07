# Phase 1 Data Model: Observation View (updated)

**Feature**: 007-observation-component-values | **Date**: 2026-07-07

This feature edits a single logical model: the materialized `sof.observation_view`, one row per
first-class `Observation` persisted by this project. Below is the **full** target column set —
existing columns (unchanged) plus the **7 new** columns — followed by how each fixture Observation
populates them.

## Entity: `observation_view` (one row per Observation)

Legend: **NEW** = added by this feature. Paths shown are the **primary** (indexer) form; the R2
fallback swaps `component[0]`→`component.first()` and `component[1]`→`component.last()`.

| Column | Path | Type | Notes |
|--------|------|------|-------|
| `id` | `getResourceKey()` | string | key column (required by shape suite) |
| `status` | `status` | code | |
| `category` | `category.first().coding.first().code` | code | |
| `code` | `code.coding.first().code` | code | what was measured |
| `code_system` | `code.coding.first().system` | string | |
| `code_display` | `code.coding.first().display` | string | |
| `value_quantity` | `value.ofType(Quantity).value` | decimal | top-level scalar value (FR-005, unchanged) |
| `value_unit` | `value.ofType(Quantity).unit` | string | top-level scalar unit (FR-005, unchanged) |
| `value_code` | `value.ofType(CodeableConcept).coding.first().code` | code | coded result code (unchanged) |
| **`value_code_display`** | `value.ofType(CodeableConcept).coding.first().display` | string | **NEW** — coded result label (FR-006) |
| `value_string` | `value.ofType(string)` | string | |
| `effective_date_time` | `effective.ofType(dateTime)` | dateTime | |
| **`component1_display`** | `component[0].code.coding.first().display` | string | **NEW** — triad 1 label (FR-001/FR-002) |
| **`component1_value`** | `component[0].value.ofType(Quantity).value` | decimal | **NEW** — triad 1 value |
| **`component1_unit`** | `component[0].value.ofType(Quantity).unit` | string | **NEW** — triad 1 unit |
| **`component2_display`** | `component[1].code.coding.first().display` | string | **NEW** — triad 2 label |
| **`component2_value`** | `component[1].value.ofType(Quantity).value` | decimal | **NEW** — triad 2 value |
| **`component2_unit`** | `component[1].value.ofType(Quantity).unit` | string | **NEW** — triad 2 unit |
| `subject` | `subject.getReferenceKey()` | string | |
| `encounter` | `encounter.getReferenceKey()` | string | |
| `cms_measure` | `meta.tag.where(system = '…/cms-measure').code.first()` | code | measure attribution (003) |

**Placement**: `value_code_display` immediately after `value_code`; the six component columns after
`effective_date_time` (before `subject`), preserving the existing column order otherwise.

## Validation rules (from spec requirements)

- **FR-003 / one row per Observation**: all new columns are single-valued reducers
  (`[0]`/`[1]`/`.first()`); **no `forEach`**. Row count is invariant.
- **FR-004 / never fabricate**: an absent component, absent `value`, or absent `unit`/`display`
  yields **null**, never 0 or a placeholder. Empty triads are expected for non-component
  Observations.
- **FR-005 / no regression**: the top-level `value_quantity`/`value_unit`/`value_code`/`value_string`
  columns are byte-for-byte unchanged.
- **FR-007 / positional**: triad 1 = first component, triad 2 = second; `*_display` disambiguates.
- **FR-008 / scope**: the `where` provenance clause and `cms_measure` column are unchanged; no other
  view is touched.

## Fixture → row projection (expected after the edit)

Distinct Observation shapes present in `test/input/` and how they populate the new columns:

| Observation (code) | value_quantity | value_code / value_code_display | component1_(display,value,unit) | component2_(display,value,unit) |
|--------------------|----------------|----------------------------------|----------------------------------|----------------------------------|
| **Blood pressure panel** (LOINC 85354-9) | null | null / null | ("Systolic blood pressure", 128, "mmHg") | ("Diastolic blood pressure", 88, "mmHg") |
| **Hemoglobin A1c** (LOINC 4548-4) | value present, unit present | null / null | null | null |
| **Depression screening** (LOINC 73831-0 / 73832-8) | null | code present / **display present (NEW)** | null | null |

> BP values shown are the not-in-population controllable-BP example (`CMS165_bulk_nip_late_htn_00500`,
> Systolic 128 / Diastolic 88 mmHg); the standard controllable-BP example carries its own readings.
> Component order in both fixtures is Systolic-then-Diastolic, so the positional mapping lands
> Systolic → triad 1 and Diastolic → triad 2; the `*_display` labels make this self-evident and
> order-tolerant for a reader.

## Source resource shape (reference)

A blood-pressure panel Observation carries no top-level `value`; its readings are in `component[]`:

```jsonc
"component": [
  { "code": { "coding": [{ "system": "http://loinc.org", "code": "8480-6",
      "display": "Systolic blood pressure" }] },
    "valueQuantity": { "value": 128, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]" } },
  { "code": { "coding": [{ "system": "http://loinc.org", "code": "8462-4",
      "display": "Diastolic blood pressure" }] },
    "valueQuantity": { "value": 88, "unit": "mmHg", "system": "http://unitsofmeasure.org", "code": "mm[Hg]" } }
]
```

`component[].value` is a `value[x]` — `valueQuantity` here — hence `value.ofType(Quantity)` inside
each component. `component[].code.coding.first().display` yields the triad label.
