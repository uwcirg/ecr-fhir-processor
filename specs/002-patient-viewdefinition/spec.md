# Feature Specification: Patient ViewDefinition + Publish/Materialize

**Feature Branch**: `002-patient-viewdefinition`

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "Author an Aidbox SQL-on-FHIR-compliant ViewDefinition for the Patient resource type, plus a script that publishes ViewDefinitions to the target FHIR server (Aidbox base_url) and calls ViewDefinition/[id]/$materialize. Start with Patient only; other resource types await analytics-team column requirements."

## Clarifications

### Session 2026-06-15 (post-implementation)

- **Q**: The target server can hold Patient resources unrelated to this eCR project. Should
  the Patient view include them, or only Patients this project persisted? — **A**: Only
  this project's Patients. The view MUST filter on this processor's provenance tag
  (`meta.tag` system `…/processed-by`, code `ecr-fhir-processor`), so unrelated Patients on
  the same server are excluded (added as **FR-013**; **SC-001** retightened accordingly).
  The filter matches the processor identity and is version-agnostic. Consistent with the
  constitution's provenance-stamping intent and the README's `_tag` scoping recipes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst queries flattened Patient demographics (Priority: P1)

A state Department of Health (DoH) analyst needs to query patient demographics across all
processed eCR submissions as flat, columnar rows (one row per patient) rather than reaching
into FHIR Patient resources field by field. They open their SQL-on-FHIR tooling against the
target server and find a Patient view already defined and materialized, exposing the
demographic columns they need (identifiers, name parts, birth date, sex, race, ethnicity,
address locality).

**Why this priority**: This is the entire point of the feature — the flattened Patient view
is the analytics deliverable. Without it, the analyst still has to hand-write extraction
logic against raw FHIR. It is also the simplest resource type and the agreed starting point.

**Independent Test**: Run the publish/materialize step against a server holding the test
Patient resources, then issue a SQL query against the materialized Patient view and confirm
one row per persisted Patient with the expected demographic columns populated.

**Acceptance Scenarios**:

1. **Given** Patient resources persisted as first-class resources on the target server,
   **When** the operator runs the publish/materialize step, **Then** a Patient view exists
   on the server and a query returns exactly one row per persisted Patient.
2. **Given** the materialized Patient view, **When** the analyst selects the demographic
   columns, **Then** each column reflects the corresponding field of the source Patient
   resource (e.g., birth date, administrative sex, race/ethnicity, address locality).

---

### User Story 2 - Operator publishes and materializes the view (Priority: P1)

An operator (hospital IT / project maintainer) runs a single step that uploads the
ViewDefinition(s) to the configured target server and triggers materialization, using only
the server location and credentials already in the project configuration. They get clear
feedback on what was published, what was materialized, and any failure.

**Why this priority**: The view is useless until it is on the server and materialized. This
is the operational mechanism that delivers User Story 1, and it must be safe to re-run.

**Independent Test**: Run the step twice against the same server; confirm the first run
creates/materializes the view and the second run updates in place without creating
duplicates or erroring, and that both runs report their outcome.

**Acceptance Scenarios**:

1. **Given** a valid target-server configuration, **When** the operator runs the step,
   **Then** each ViewDefinition is uploaded under a stable identifier and then materialized,
   and the outcome of each is reported.
2. **Given** a ViewDefinition already present on the server from a prior run, **When** the
   operator re-runs the step, **Then** the view is updated in place (no duplicate) and the
   result is reported as success.
3. **Given** the server rejects a ViewDefinition or its materialization, **When** the step
   runs, **Then** the failure is logged with the server's reason and reflected in the exit
   status, and any other ViewDefinitions are still attempted.

---

### User Story 3 - Maintainer adds the next resource type later (Priority: P3)

Once the analytics team specifies the columns it wants from another resource type (e.g.,
Condition, Observation), a maintainer adds a new ViewDefinition file alongside the Patient
one and the same publish/materialize step picks it up — no change to the mechanism.

**Why this priority**: Confirms the design generalizes, but is explicitly deferred: only
Patient is in scope now. This story protects against a Patient-only design that can't grow.

**Independent Test**: Add a second minimal ViewDefinition file and confirm the
publish/materialize step processes both without code changes to the step itself.

**Acceptance Scenarios**:

1. **Given** a new ViewDefinition file added to the project, **When** the operator runs the
   publish/materialize step, **Then** the new view is published and materialized alongside
   the Patient view with no change to the step's invocation.

---

### Edge Cases

- **No Patient resources on the server**: materialization still succeeds and the step reports
  success (exit 0) — an empty view is not a failure. The view simply returns zero rows when
  queried; the step itself does not count rows.
- **Server rejects the ViewDefinition as non-conformant**: the step surfaces the server's
  validation error and exits non-zero; it does not silently skip.
- **Materialization fails after a successful upload** (e.g., unsupported expression): the
  upload result and the materialization failure are reported separately so the operator
  knows the view exists but is not materialized.
- **Patient field absent on a given resource** (e.g., no race/ethnicity extension, no
  address): the corresponding column is null for that row, not an error, and no clinical
  value is fabricated.
- **A Patient has multiple values for a single-valued column** (e.g., multiple names or
  addresses): the view applies a deterministic selection rule so the row stays one-per-patient.
- **Re-running after the view already exists**: update-in-place, no duplicate view, no
  re-persistence of unrelated resources.
- **Credentials/base URL missing or invalid in configuration**: the step fails loudly at
  startup with a clear message, before contacting the server.
- **Server also holds unrelated Patient resources** (from other projects/loads): the view
  excludes them via the processor's provenance tag (FR-013); only Patients this project
  persisted appear. A Patient that somehow lacks the provenance tag is not in the view.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST include a checked-in, version-controlled Patient
  ViewDefinition resource that conforms to the SQL-on-FHIR ViewDefinition specification as
  implemented by the target server (Aidbox).
- **FR-002**: The Patient ViewDefinition MUST produce one row per Patient resource and MUST
  expose, at minimum, the demographic columns required for DoH analytics: a stable patient
  key, business identifier(s) (e.g., MRN), name parts (family, given), administrative sex,
  birth date, deceased indicator, race, ethnicity, and address locality (city, state, postal
  code). (See Assumptions for the default column set; it is reviewable with the analytics
  team.)
- **FR-003**: The Patient ViewDefinition MUST select only from first-class,
  individually-addressable Patient resources on the server — never from Patient content
  nested inside an un-promoted Bundle.
- **FR-004**: The project MUST provide a publish/materialize step that uploads each
  ViewDefinition to the target server under a stable identifier and then triggers
  materialization of that view.
- **FR-005**: The publish/materialize step MUST be idempotently re-runnable: re-running
  updates each view in place without creating duplicates and without re-persisting or
  rolling back unrelated resources.
- **FR-006**: The publish/materialize step MUST obtain the target server location and
  credentials from project configuration only; no server-specific values may be hardcoded.
- **FR-007**: The publish/materialize step MUST validate required configuration at startup
  and fail with a clear message before contacting the server if it is missing or invalid.
- **FR-008**: The publish/materialize step MUST process each ViewDefinition independently:
  a publish or materialize failure for one view MUST be logged with the server's reason and
  reflected in the exit status, and MUST NOT prevent the remaining views from being attempted.
- **FR-009**: The publish/materialize step MUST report, per view, whether upload succeeded
  and whether materialization succeeded, distinguishing the two outcomes.
- **FR-010**: When a Patient field that backs a column is absent, the column MUST be null
  for that row; the step MUST NOT fabricate values to fill columns.
- **FR-011**: Adding a new resource-type ViewDefinition file MUST NOT require changes to the
  publish/materialize step's mechanism or invocation.
- **FR-012**: Scope is limited to Patient for now. Additional resource-type ViewDefinitions
  MUST NOT be authored speculatively; each is added only once the analytics team specifies
  its required columns. The absence of other views is intentional, not incomplete work.
- **FR-013**: The Patient ViewDefinition MUST include only Patient resources persisted by
  this project's processor — i.e. those bearing this processor's provenance tag
  (`meta.tag` system `…/processed-by`, code `ecr-fhir-processor`, stamped per the
  feature-001 provenance contract). Unrelated Patient resources that happen to exist on the
  same target server (e.g. from other projects) MUST NOT appear in the view. The filter is
  version-agnostic (it matches the processor identity, not a specific version).

### Key Entities *(include if feature involves data)*

- **ViewDefinition (Patient)**: The definition of the flattened Patient view — its stable
  identifier, the source resource type (Patient), and the ordered set of output columns with
  the source field each column draws from. The analytics contract for Patient demographics.
- **Materialized Patient view**: The server-side flattened table produced from the
  ViewDefinition — one row per Patient, columns as defined. The artifact the analyst queries.
- **Publish/materialize outcome**: Per-view record of upload result and materialization
  result (success/failure + reason), surfaced to the operator and reflected in exit status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running the publish/materialize step against a server holding N
  first-class Patient resources **persisted by this project's processor** (i.e. carrying
  its provenance tag, FR-013), a query against the materialized Patient view returns exactly
  N rows — regardless of how many unrelated Patient resources from other sources also exist
  on that server.
- **SC-002**: An analyst can retrieve the defined demographic columns for any patient from
  the materialized view using a single flat query, with no per-resource FHIR navigation.
- **SC-003**: Running the publish/materialize step twice in a row results in exactly one
  Patient view on the server (no duplicates) and the second run reports success.
- **SC-004**: When the server rejects a view or its materialization, the operator can
  identify which view failed and why from the step's output, and the step's exit status is
  non-zero.
- **SC-005**: Every column value in the materialized view either matches the corresponding
  source Patient field or is null where the source field is absent — zero fabricated values.
- **SC-006**: A maintainer can add a second resource-type ViewDefinition file and have it
  published and materialized by re-running the same step, with no change to the step itself.

## Assumptions

- **Default Patient column set**: In the absence of a finalized analytics-team column list,
  the Patient view defaults to standard DoH demographic columns — patient key, MRN-style
  identifier, family/given name, administrative sex, birth date, deceased flag, race,
  ethnicity, and address city/state/postal. This set is a reviewable starting point and may
  be adjusted once the analytics team confirms its requirements.
- **Race/ethnicity sourcing**: Race and ethnicity are drawn from the US Core
  race/ethnicity extensions present on the eCR Patient resources; when absent, those columns
  are null.
- **Patients already persisted as first-class resources**: This feature consumes the
  first-class Patient resources produced by the existing processor (per the analytics-ready
  persistence granularity principle); it does not change how Patients are persisted.
- **Existing configuration and authentication are reused**: The publish/materialize step
  uses the project's existing target-server base URL and OAuth2 credentials configuration;
  no new auth mechanism is introduced.
- **Zero-dependency runtime is retained**: The publish/materialize step is expected to run
  within the project's existing stdlib-only runtime constraint, reusing the existing server
  client where possible.
- **Single-valued column selection**: Where a Patient has multiple values for a
  single-valued column (e.g., multiple addresses), a deterministic rule (e.g., first / use
  = official) is applied to keep one row per patient; the exact rule is settled in planning.
- **Target server is Aidbox**: "SQL-on-FHIR compliant" is interpreted as compliant with the
  ViewDefinition support in the configured Aidbox server, including its `$materialize`
  operation.
