# Phase 0 Research: Patient ViewDefinition + Publish/Materialize

**Feature**: `002-patient-viewdefinition` | **Date**: 2026-06-15

All Technical-Context unknowns were resolvable from the existing codebase (`process.py`, the
`test/input/**` Patient fixtures) and the Aidbox SQL-on-FHIR docs. No `NEEDS CLARIFICATION`
remains. Decisions below feed Phase 1 (data-model, contracts, quickstart).

---

## R1 — Reuse the existing `FhirClient`, config, and outcome machinery (via a shared module)

**Decision**: Build the publish/materialize step on the existing `process.py` primitives rather
than writing new HTTP/auth/config code — but reach them by **extracting the shared primitives into
a third module** (`fhir_common.py`) that both `process.py` and the new `publish_views.py`
(R4) import. No copy-paste, no new HTTP/auth code.

Primitives to extract from `process.py` into `fhir_common.py`:

- `FhirClient` (`process.py:619`) — OAuth2 client-credentials with token caching, single
  401-refresh retry, the `aidbox-validation-skip` header, and a generic
  `request(method, url, body)`. Exactly what `PUT ViewDefinition` and `POST …/$materialize` need;
  `submit_put` is the model for the publish call.
- `RunConfig`, `load_config` (`:222`), `validate_config` (`:245`) — enforce required
  `server.{base_url,token_endpoint,client_id,client_secret}` and reject `YOUR_*` placeholders
  (FR-006/FR-007) with no new code.
- `setup_logging` (`:149`) — console + timestamped audit file under `log/` (Clear, Predictable
  Output).
- `FileOutcome` / `RunSummary` (`:93`, `:113`) + `RunSummary.exit_code()` — per-item
  success/failure record and non-zero-on-any-failure exit (FR-008/FR-009).
- Supporting constants/exceptions (`REQUIRED_SERVER_FIELDS`, `DEFAULT_PATHS`,
  `PLACEHOLDER_PREFIX`, `SubmissionError`).

`process.py` keeps its behavior unchanged by importing these from `fhir_common.py` (a pure move +
import; the extraction is covered by re-running the feature-001 validation pipeline so it is a
no-op refactor, not a behavior change).

**Rationale**: Principle I (zero new deps) and "reuse over rebuild"; the constitution (VII)
explicitly says the script reuses the existing FHIR client/auth. The shared module is the boundary
the constitution's Single-File Simplicity rule names verbatim ("FHIR client logic, validation
orchestration") and `process.py` is already ~1000 lines (the stated split threshold) — so the
extraction is now justified rather than premature. See R4 for why the step is a separate script.

**Alternatives considered**: Importing the helpers directly from `process.py` into the new script —
rejected: makes `process.py` an import dependency of an unrelated entry point and drags the
processor's CLI/pipeline into the view tool's import graph. A clean `fhir_common.py` boundary is
better. Re-implementing auth/config in the new script — rejected: duplicates logic, drifts.

---

## R2 — Endpoint paths and base URL convention

**Decision**: Publish to `{base}/ViewDefinition/{id}` (PUT) and materialize via
`{base}/ViewDefinition/{id}/$materialize` (POST), using the **same `base` convention as the
existing `submit_put`** (`{base}/{Type}/{id}` with no extra `/fhir` prefix).

- The existing client already treats `server.base_url` as the FHIR API root (`submit_put` →
  `{base}/{resource_type}/{id}`). Aidbox docs show `/fhir/ViewDefinition/[id]/$materialize`; in
  this project the configured `base_url` is the FHIR base, so the relative path is
  `ViewDefinition/{id}` and `ViewDefinition/{id}/$materialize`. No special-casing.

**Rationale**: Keeps one base-URL convention across persist + publish; deployments already point
`base_url` at the Aidbox FHIR root.

**Alternatives considered**: Hardcoding `/fhir/…` — rejected (server-specific, violates
config-over-code; inconsistent with `submit_put`).

---

## R3 — `$materialize` request body and materialization type

**Decision**: POST a FHIR `Parameters` body with a single `type` parameter; default the type to
**`view`**, overridable via optional config `server.materialize_type`.

```json
{ "resourceType": "Parameters",
  "parameter": [ { "name": "type", "valueCode": "view" } ] }
```

- Aidbox `$materialize` (≥ 2508) requires `type` ∈ {`table`, `view`, `materialized-view`} and
  returns a `Parameters` with `viewName`/`viewType`/`viewSchema` on success, or an
  `OperationOutcome` on failure.
- **`view`** is an always-current SQL view: it reflects the live Patient set on every read, so
  SC-001 ("exactly N rows") holds without any manual refresh step. `materialized-view`/`table`
  are point-in-time snapshots that Aidbox does **not** auto-refresh (refresh is manual via
  Postgres), which would let the row count drift from the live data between runs.
- Type is configurable so a deployment that wants a frozen snapshot can choose
  `materialized-view`/`table`; the default optimizes for correctness-without-extra-steps.

**Rationale**: Matches the spec's success criteria (deterministic row count, idempotent re-run)
with the least operational surface. The id is taken from the URL path, so `viewReference`/
`viewResource` parameters are unnecessary.

**Alternatives considered**: Defaulting to `materialized-view` — rejected as default: requires a
documented manual refresh to stay correct, complicating SC-001/SC-003; offered as an opt-in
instead.

---

## R4 — Separate script vs subcommand

**Decision**: Ship the step as its **own top-level entry point `publish_views.py`** — not a
subcommand of `process.py` — with shared primitives imported from `fhir_common.py` (R1).

- **Different trigger, not just different cadence.** Persistence (`process.py`) runs on every
  ingest, whenever new eCR data arrives. Publishing/materializing the view is a rare,
  schema-change activity: with the default `view` materialization type (R3) the view reflects live
  data automatically, so it is re-run **only to change the ViewDefinition** (columns/queries) or to
  first establish it — not when new Patients land. (A re-run *would* also be needed to refresh data
  **only** if a deployment opts into a snapshot `materialized-view`/`table` type, which Aidbox does
  not auto-refresh.) The two operations are driven by entirely different events; folding them into
  one entry point would mean either pointlessly re-publishing the view on every ingest or adding an
  awkward conditional. A separate script keeps each tool triggered by its own event and its CLI
  focused.
- **Constitution fit.** Single-File Simplicity keeps `process.py` as *the processor's* entry
  point; it does not forbid a second tool with a distinct responsibility. The shared logic is
  extracted to `fhir_common.py` — the exact boundary the principle names ("FHIR client logic,
  validation orchestration") — and `process.py` is already at the ~1000-line threshold, so the
  split is warranted, not premature.
- Implementation: `publish_views.py` has its own small `argparse` parser (see CLI contract);
  `process.py`'s invocation is unchanged.

**Rationale**: Separation of concerns and independent run cadence (operator's stated reason),
achieved without code duplication thanks to the shared module.

**Alternatives considered**: A `publish-views` subcommand on `process.py` — rejected: couples two
independently-scheduled operations and bloats one entry point. A third-party CLI framework —
rejected (Principle I).

---

## R5 — Conformance gate for a ViewDefinition (Principle III)

**Decision**: The authoritative conformance gate for the ViewDefinition is **Aidbox acceptance**:
`PUT` returns 200/201 and `$materialize` succeeds. The HL7 `validator_cli.jar` is **not** used for
this resource.

- `validator_cli.jar` validates FHIR R4 against the eCR/US-Core/DEQM/APHL IG set (constitution
  Principle II). A SQL-on-FHIR `ViewDefinition` is a logical-model resource from the SQL-on-FHIR
  IG, outside that set, and Aidbox is the implementation that defines what it accepts — so server
  acceptance (Principle III "gate 2") is the right and sufficient gate.
- Pre-flight cheap checks still apply: a `unittest` asserts the checked-in file is valid JSON and
  carries the required fields (`resourceType: ViewDefinition`, `resource`, `status`, `select`),
  catching typos before any network call.

**Rationale**: Principle III explicitly admits the FHIR server's own validation as a gate; using
the eCR validator on a non-eCR resource would produce meaningless errors.

**Alternatives considered**: Adding the SQL-on-FHIR IG to `validator_cli.jar` — rejected: not in
the project's IG conformance scope, adds a dev gate with no real signal over server acceptance.

---

## R6 — Column set, single-valued selection, and absent-field handling

**Decision**: Use the FR-002 default DoH column set, mapped to SQL-on-FHIR FHIRPath, with a
**deterministic `.first()`** selection for multi-valued elements and **no `forEach`** at the row
level so the view stays one-row-per-Patient. Absent source fields yield `null` columns (FR-010) —
SQL-on-FHIR already returns null when a path matches nothing; we never fabricate.

Confirmed against the fixture `Patient` (`CMS122_NOT_IP_AgeUnder18.json`):

| Column | Source (FHIRPath in ViewDefinition) | Notes |
|--------|--------------------------------------|-------|
| `id` | `getResourceKey()` | stable patient key (SQL-on-FHIR canonical key fn) |
| `mrn` | `identifier.where(type.coding.exists(code='MR')).value.first()` | MR-typed business id; fixture has `type.coding.code = MR` |
| `name_family` | `name.first().family` | first name entry (fixture has no `use`) |
| `name_given` | `name.first().given.first()` | first given of first name |
| `gender` | `gender` | administrative sex |
| `birth_date` | `birthDate` | |
| `deceased` | `deceased.ofType(boolean)` | fixture uses `deceasedBoolean` |
| `race_code` | `extension('…/us-core-race').extension('ombCategory').value.ofType(Coding).code.first()` | US Core race ext; null when absent |
| `race_display` | `extension('…/us-core-race').extension('ombCategory').value.ofType(Coding).display.first()` | |
| `ethnicity_code` | `extension('…/us-core-ethnicity').extension('ombCategory').value.ofType(Coding).code.first()` | US Core ethnicity ext |
| `ethnicity_display` | `extension('…/us-core-ethnicity').extension('ombCategory').value.ofType(Coding).display.first()` | |
| `address_city` | `address.first().city` | address locality |
| `address_state` | `address.first().state` | |
| `address_postal_code` | `address.first().postalCode` | |

Full extension URLs: `http://hl7.org/fhir/us/core/StructureDefinition/us-core-race` and
`…/us-core-ethnicity` (confirmed in fixtures).

**Single-valued rule**: `.first()` after an optional `where(...)` filter — deterministic and keeps
one row per patient (edge case in spec). Where a clinical "official/usual" use exists it could be
preferred later; the fixtures don't set `use`, so `.first()` is the documented default rule.

**Rationale**: Matches FR-002's default column set and the spec's deterministic-selection and
no-fabrication edge cases; verified field-by-field against a real fixture so the paths resolve.

**Alternatives considered**: `forEach` over name/address (would multiply rows — rejected, breaks
one-row-per-patient); inventing values for absent race/ethnicity (rejected — Principle V, FR-010).

**Open (non-blocking)**: The exact column list is a reviewable default, not a finalized
analytics-team contract (spec Assumptions + checklist note). Adjusting it later is editing the
checked-in ViewDefinition + re-running the step — no mechanism change.

---

## Sources

- Aidbox `$materialize` operation — request/response, `type` param, version ≥ 2508, manual
  refresh: <https://www.health-samurai.io/docs/aidbox/modules/sql-on-fhir/operation-materialize>
- Aidbox SQL on FHIR module overview:
  <https://www.health-samurai.io/docs/aidbox/modules/sql-on-fhir>
- Existing implementation: `process.py` (`FhirClient` :619, `load_config` :222,
  `validate_config` :245, `FileOutcome`/`RunSummary` :93/:113, `setup_logging` :149).
- Fixture: `test/input/poor-diabetic-control/not-in-population/CMS122_NOT_IP_AgeUnder18/CMS122_NOT_IP_AgeUnder18.json`.
