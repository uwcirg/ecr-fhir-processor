# Phase 1 Data Model: Patient ViewDefinition + Publish/Materialize

**Feature**: `002-patient-viewdefinition` | **Date**: 2026-06-15

Entities are drawn from spec "Key Entities" + Requirements, grounded in research.md decisions.
This feature adds no new persisted FHIR clinical data — it defines a view over already-persisted
first-class Patient resources and a transient per-run outcome record.

---

## 1. ViewDefinition (Patient) — checked-in resource

The analytics contract for Patient demographics. One file per resource type; Patient only now.

**File**: `viewdefinitions/patient.ViewDefinition.json`

**Required fields** (Aidbox/SQL-on-FHIR, FR-001):

| Field | Value | Why |
|-------|-------|-----|
| `resourceType` | `"ViewDefinition"` | resource kind |
| `id` | stable slug, e.g. `"patient"` | stable identifier for PUT-by-id idempotency (FR-004/FR-005) |
| `name` | e.g. `"patient_view"` | becomes the materialized object name `sof.patient_view` |
| `status` | `"active"` (or `"draft"`) | lifecycle status |
| `resource` | `"Patient"` | source resource type — selects first-class `Patient/<id>` only (FR-003, Principle VI) |
| `select` | array (see below) | column definitions |

**Structure rule (one row per Patient)**: a single top-level `select` whose `column` array holds
the demographic columns. **No row-multiplying `forEach`** at the patient level; multi-valued
elements are reduced with `.first()` (FR + edge case: deterministic single-valued selection).

**Columns** (FR-002 default DoH set; FHIRPath verified against fixture — see research.md R6):

| Column name | FHIRPath `path` | Type | Null when |
|-------------|-----------------|------|-----------|
| `id` | `getResourceKey()` | string | never (patient key) |
| `mrn` | `identifier.where(type.coding.exists(code='MR')).value.first()` | string | no MR identifier |
| `name_family` | `name.first().family` | string | no name / no family |
| `name_given` | `name.first().given.first()` | string | no given name |
| `gender` | `gender` | code | absent |
| `birth_date` | `birthDate` | date | absent |
| `deceased` | `deceased.ofType(boolean)` | boolean | absent / non-boolean form |
| `race_code` | `extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-race').extension('ombCategory').value.ofType(Coding).code.first()` | code | no race extension |
| `race_display` | …`us-core-race`…`.display.first()` | string | no race extension |
| `ethnicity_code` | `extension('http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity').extension('ombCategory').value.ofType(Coding).code.first()` | code | no ethnicity ext |
| `ethnicity_display` | …`us-core-ethnicity`…`.display.first()` | string | no ethnicity ext |
| `address_city` | `address.first().city` | string | no address / no city |
| `address_state` | `address.first().state` | string | no address / no state |
| `address_postal_code` | `address.first().postalCode` | string | no address / no postal |

**Validation rules (FR/Principle)**:
- Selects only from first-class Patient resources; never reaches into a Bundle (FR-003, VI).
- Absent backing field → null column; no fabricated values (FR-010, Principle V).
- Multi-valued element → deterministic `.first()` (one row per patient).
- Column set is a **reviewable default**, not a finalized analytics contract (spec Assumptions).

**Materialized Patient view** (server-side, derived — not a repo artifact): the flat table/view
Aidbox produces in the `sof` schema (`sof.patient_view`), one row per first-class Patient, columns
as above. The artifact the analyst queries (SC-001/SC-002).

---

## 2. ViewDefinitionFile (discovered work unit)

Transient, in-memory. The publish/materialize step discovers these from `viewdefinitions/`.

| Field | Source | Notes |
|-------|--------|-------|
| `path` | filesystem | `viewdefinitions/*.json` (or `*.ViewDefinition.json`) |
| `resource` | parsed JSON | must be `resourceType == "ViewDefinition"` |
| `id` | `resource.id` | required for PUT-by-id; missing id → fail this file loudly |
| `name` | `resource.name` | informational in reporting |

**Discovery rule**: every matching file is processed independently; adding a file requires **no
code change** (FR-011, Story 3). A file that is not a valid ViewDefinition JSON, or lacks `id`,
fails *that file* with a clear message and is reflected in exit status — without blocking others.

---

## 3. PublishMaterializeOutcome (per-view run record)

Reuses `FileOutcome` + `RunSummary` (imported from the shared `fhir_common.py`, R1). One record
per ViewDefinition file; the two operations are reported **separately** (FR-009).

| Field | Values | Meaning |
|-------|--------|---------|
| `view_id` | string | which ViewDefinition |
| `publish_status` | `ok` \| `failed` | PUT result (FR-009) |
| `publish_detail` | server status + reason | on failure, the server's reason (FR-008) |
| `materialize_status` | `ok` \| `failed` \| `skipped` | `$materialize` result; `skipped` if publish failed |
| `materialize_detail` | server status + reason / `viewName` | success carries `viewName`/`viewType`/`viewSchema`; failure carries the OperationOutcome reason |

**State / transitions**:
1. discover → for each file: PUT.
2. PUT ok → POST `$materialize`. PUT failed → record publish failure, **skip** materialize for
   this view, continue to next view (per-view isolation, FR-008/Principle V).
3. materialize ok → record success (incl. `viewName`); materialize failed → record failure with
   reason (the operator learns the view exists but is not materialized — spec edge case).

**Aggregation / exit code** (FR-008/FR-009, mirrors `RunSummary.exit_code`):
- Exit `0` iff every discovered view both published and materialized successfully.
- Any publish or materialize failure → **non-zero** exit (SC-004), after **all** views attempted.
- Empty Patient set is **not** a failure: materialize succeeds and the step reports success,
  exit `0`. The view returns zero rows when queried; the step reports the materialize outcome
  (`viewName`), not a row count (spec edge case).

---

## Relationships

```text
viewdefinitions/patient.ViewDefinition.json (repo)
      │  PUT [base]/ViewDefinition/<id>           (publish, update-in-place)
      ▼
ViewDefinition/<id> on Aidbox
      │  POST [base]/ViewDefinition/<id>/$materialize {type: view}
      ▼
sof.patient_view (server-side flat view)  ◀── selects ── Patient/<id> (first-class, feature 001)
      │  SQL query
      ▼
DoH analyst (one row per Patient, demographic columns)
```
