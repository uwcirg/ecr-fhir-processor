# Contract: Observation ViewDefinition — Component & Coded Measurement Columns

**Feature**: 007-observation-component-values | **Date**: 2026-07-07

This contract governs the edited `viewdefinitions/observation.ViewDefinition.json`. It adds columns;
it changes no CLI surface. The publish/materialize server-operation contract is **unchanged** from
002 (`specs/002-patient-viewdefinition/contracts/publish-materialize-cli.md`) — referenced, not
duplicated.

## Resource-level invariants (must remain true)

The edited file MUST continue to satisfy the directory-driven shape suite
(`tests/test_viewdefinition.py`), i.e.:

- `resourceType` = `ViewDefinition`; stable `id` = `observation`; `name` = `observation_view`;
  `status` = `active`; `resource` = `Observation`.
- Non-empty `select[].column`; a key column using `getResourceKey()` (`id`).
- The provenance `where` clause unchanged:
  `meta.tag.where(system = '…/processed-by' and code = 'ecr-fhir-processor').exists()`.
- Exactly one `cms_measure` column, single-valued, unchanged.
- Valid JSON; SQL-on-FHIR-conformant as implemented by Aidbox.

## Added columns (contract)

Seven columns, in the placement from [data-model.md](../data-model.md):

1. `value_code_display` (string) — `value.ofType(CodeableConcept).coding.first().display`
2. `component1_display` (string) — `component[0].code.coding.first().display`
3. `component1_value` (decimal) — `component[0].value.ofType(Quantity).value`
4. `component1_unit` (string) — `component[0].value.ofType(Quantity).unit`
5. `component2_display` (string) — `component[1].code.coding.first().display`
6. `component2_value` (decimal) — `component[1].value.ofType(Quantity).value`
7. `component2_unit` (string) — `component[1].value.ofType(Quantity).unit`

**Fallback form** (apply only if Aidbox rejects/nulls the indexer at `PUT`/`$materialize`, per
research R2): replace `component[0]`→`component.first()` and `component[1]`→`component.last()`; all
suffixes and types unchanged.

## Behavioral guarantees

- **One row per Observation** — all added columns are single-valued reducers; no `forEach`
  (FR-003). Materialized row count for `sof.observation_view` is unchanged.
- **Never fabricate** — absent component / value / unit / display → SQL `NULL` (FR-004). Empty
  triads for non-component Observations are conformant, not a defect.
- **No regression** — the pre-existing columns (`value_quantity`, `value_unit`, `value_code`,
  `value_string`, `code*`, `subject`, `encounter`, `cms_measure`, `status`, `category`,
  `effective_date_time`) are byte-for-byte unchanged (FR-005).
- **Scope** — no other ViewDefinition file is modified; no code/config change (FR-008).

## Acceptance (authoritative gate — Principle III gate 2)

Against an Aidbox server holding the processed fixtures:

1. `PUT viewdefinitions/observation.ViewDefinition.json` is accepted.
2. `$materialize` on the Observation view succeeds.
3. Querying `sof.observation_view`:
   - Each blood-pressure panel row shows two populated triads (e.g. `component1 = ("Systolic blood
     pressure", 128, "mmHg")`, `component2 = ("Diastolic blood pressure", 88, "mmHg")`).
   - Each depression-screening row shows a non-null `value_code_display`.
   - The Hemoglobin A1c row shows unchanged `value_quantity`/`value_unit`; all four component
     columns null.
   - Total row count equals the pre-edit count.

If step 1 or 2 fails on the indexer, apply the fallback form and re-run — that failure is the
signal, not a defect in the design.
