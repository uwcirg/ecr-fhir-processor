# Feature Specification: ViewDefinitions for the Remaining Resource Types

**Feature Branch**: `004-remaining-viewdefinitions`

**Created**: 2026-06-16

**Status**: Draft

**Input**: User description: "Generate ViewDefinitions for the remaining resources (Condition, Encounter, Observation, Practitioner, Organization, Location, Measure, Bundle, Procedure, MedicationRequest, ServiceRequest), and persist them via publish_views.py"

## Clarifications

### Session 2026-06-16

- **Q**: No finalized analytics-team column list was supplied for these eleven resource types.
  How should the column sets be chosen? — **A**: Follow the precedent set by the Patient view
  (002-patient-viewdefinition FR-002 / Assumptions): each view ships an **informed, reviewable
  default column set** drawn from the analytically-relevant fields of that resource type, not a
  finalized contract. This is the demand-driven expansion the constitution's
  `TODO(VIEWDEF_RESOURCE_TYPES)` and 002 FR-012 anticipated; the defaults are settled with the
  analytics team during planning/review, not blocked on them.

- **Q**: Bundle is a container, not a clinical resource — should it get a flattened view? —
  **A**: Yes, because the user explicitly listed it, but the Bundle view is intentionally thin:
  it exposes Bundle-level metadata (type, timestamp, entry count, identifier) so analysts can
  account for the persisted container resources, not clinical content (which lives in the
  promoted first-class resources). Flagged for analytics-team confirmation of whether they want
  it at all.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst queries flattened clinical and reference data across resource types (Priority: P1)

A state Department of Health (DoH) analyst already has the flattened Patient view. They now
need the same flat, columnar access to the rest of the data each processed eCR contributes —
the conditions diagnosed, the encounters, the observations and lab results, the practitioners
and organizations involved, service locations, the quality measures, procedures, medication
requests, and service requests. For each of these resource types they open their SQL-on-FHIR
tooling against the target server and find a view already defined and materialized, exposing
one row per resource with the analytically-relevant columns — without reaching into raw FHIR
resources field by field.

**Why this priority**: This is the deliverable. The Patient view alone answers only "who"; the
remaining resource types answer "what condition, what encounter, what was observed, who
provided care, where, under what measure, what was done, what was ordered." Together they make
the processed eCR data analyzable as flat tables.

**Independent Test**: Persist the test eCR resources to a server, run the publish/materialize
step, then issue a flat SQL query against each new view (e.g. the Condition view) and confirm
one row per persisted resource of that type with the expected columns populated.

**Acceptance Scenarios**:

1. **Given** resources of each listed type persisted as first-class resources on the target
   server, **When** the operator runs the publish/materialize step, **Then** a view exists and
   is materialized for each of the eleven resource types, each returning one row per persisted
   resource of that type.
2. **Given** a materialized view (e.g. Observation), **When** the analyst selects its columns,
   **Then** each column reflects the corresponding field of the source resource (e.g. code,
   value, effective date/time, status, subject reference).
3. **Given** any of the new views, **When** the analyst filters on the CMS-measure column,
   **Then** only rows whose underlying resource was attributed to that measure are returned —
   the same measure-scoping the Patient view already supports (003-cms-measure-filter).

---

### User Story 2 - Operator publishes and materializes all views in one step (Priority: P1)

An operator runs the existing publish/materialize step once and it uploads and materializes
every checked-in ViewDefinition — the existing Patient view plus the eleven new ones — using
only the server location and credentials already in the project configuration, reporting per
view what was published and materialized and isolating any single view's failure.

**Why this priority**: The views are useless until they are on the server and materialized.
The mechanism to do this already exists and auto-discovers ViewDefinition files; this story
confirms the new views are delivered by it with no change to how the operator invokes it.

**Independent Test**: Add the new ViewDefinition files, run the publish/materialize step, and
confirm all twelve views are published and materialized in one invocation, with a per-view
outcome reported and a non-zero exit only if some view fails.

**Acceptance Scenarios**:

1. **Given** the new ViewDefinition files checked in alongside the Patient view, **When** the
   operator runs the publish/materialize step with its usual invocation, **Then** all views
   are uploaded under stable identifiers and materialized, with no change to the command.
2. **Given** the server rejects one view or its materialization, **When** the step runs,
   **Then** that view's failure is logged with the server's reason and reflected in the exit
   status, and every other view is still attempted and reported.
3. **Given** a prior run already created the views, **When** the operator re-runs the step,
   **Then** each view is updated in place (no duplicates) and the result is reported as success.

---

### User Story 3 - Measure-scoped, provenance-scoped rows across every view (Priority: P2)

For every new view, the analyst can both (a) restrict to only the resources this project's
processor persisted and (b) filter by CMS measure — exactly as the Patient view does — so the
same analytic slices (e.g. "CMS165 encounters", "CMS122 conditions") are available for every
resource type, not just Patient.

**Why this priority**: Consistency of scoping across views is what makes cross-resource-type
analysis coherent. Without it, a join across views would mix this project's data with unrelated
server data, or lose the measure dimension on every type but Patient.

**Independent Test**: On a server that also holds unrelated resources of these types, query
each new view and confirm only processor-persisted resources appear; then filter by a CMS
measure code and confirm only that measure's resources are returned.

**Acceptance Scenarios**:

1. **Given** a server holding both processor-persisted and unrelated resources of a listed
   type, **When** the analyst queries that type's view, **Then** only the processor-persisted
   resources (those bearing the `…/processed-by` = `ecr-fhir-processor` provenance tag) appear.
2. **Given** any new view, **When** the analyst filters on its CMS-measure column, **Then**
   rows resolve to one of the known measure codes (e.g. `CMS2`, `CMS122`, `CMS165`) or the
   `unknown` sentinel, consistent with 003-cms-measure-filter.

---

### Edge Cases

- **No resources of a given type on the server**: materialization still succeeds and the step
  reports success (exit 0) — an empty view is not a failure; the view returns zero rows.
- **A backing field is absent on a given resource** (e.g. an Observation with no value, a
  Condition with no onset, a Practitioner with no qualification): the corresponding column is
  null for that row, not an error; no clinical value is fabricated.
- **A resource has multiple values for a single-valued column** (e.g. multiple identifiers,
  multiple codings, multiple names): a deterministic selection rule (e.g. first / preferred
  coding) keeps the view one-row-per-resource; multi-valued detail that the analytics team
  needs row-multiplied is handled with an explicit `forEach`/unnest, decided in planning.
- **Choice-type fields** (e.g. Observation `value[x]`, MedicationRequest `medication[x]`,
  Procedure `performed[x]`): the view exposes the analytically-primary variant(s) as typed
  columns; absent variants are null.
- **Reference columns** (subject, encounter, requester, performer, etc.): the view exposes the
  referenced resource's key via `getReferenceKey()` (which matches the target view's
  `getResourceKey()` `id`), not the resolved target; cross-view joins are the analyst's to make.
  (A raw `.reference` string column resolves to null under Aidbox's reference normalization — see
  research.md R4.)
- **Bundle as a resource type**: the Bundle view is metadata-only (type, timestamp, entry
  count, identifier); it does not attempt to flatten nested clinical content, which is already
  promoted to its own first-class resources and covered by the other views.
- **Server rejects a view as non-conformant**: the step surfaces the server's validation error
  and exits non-zero for that view; it does not silently skip, and the other views proceed.
- **A persisted resource lacks the CMS-measure or provenance tag**: it is excluded by the
  provenance `where` filter; if present but un-attributed, its CMS-measure column is `unknown`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST include a checked-in, version-controlled ViewDefinition resource
  for each of these eleven resource types: Condition, Encounter, Observation, Practitioner,
  Organization, Location, Measure, Bundle, Procedure, MedicationRequest, and ServiceRequest.
  Each MUST conform to the SQL-on-FHIR ViewDefinition specification as implemented by the
  target server (Aidbox).
- **FR-002**: Each ViewDefinition MUST produce one row per first-class resource of its type and
  MUST expose an informed, reviewable default set of analytically-relevant columns for that
  resource type, including at minimum a stable resource key (see Assumptions for the per-type
  default column sets). The column sets are a reviewable starting point, settled with the
  analytics team, not a finalized contract.
- **FR-003**: Each ViewDefinition MUST select only from first-class,
  individually-addressable resources on the server — never from content nested inside an
  un-promoted Bundle.
- **FR-004**: Each new ViewDefinition MUST be published and materialized by the existing
  publish/materialize step with no change to that step's mechanism or invocation — the step
  already auto-discovers every ViewDefinition file in the views directory (002 FR-011).
- **FR-005**: Each ViewDefinition MUST restrict its rows to resources persisted by this
  project's processor — i.e. those bearing the processor's provenance tag (`meta.tag` system
  `…/processed-by`, code `ecr-fhir-processor`), version-agnostic — so unrelated resources of
  the same type on the same server MUST NOT appear (mirrors 002 FR-013).
- **FR-006**: Each ViewDefinition MUST expose the CMS-measure attribution as a column drawn
  from the `…/CodeSystem/cms-measure` tag, so every view supports the same measure-scoped
  filtering the Patient view supports (mirrors 003-cms-measure-filter).
- **FR-007**: When a field that backs a column is absent on a given resource, that column MUST
  be null for that row; the views MUST NOT fabricate values.
- **FR-008**: Where a resource has multiple values for a column intended to be single-valued,
  each ViewDefinition MUST apply a deterministic selection rule so the view remains
  one-row-per-resource unless an explicit unnest is intentionally chosen for that column.
- **FR-009**: Each ViewDefinition MUST carry a stable identifier and a human-readable
  name/description, consistent with the Patient view, so re-running the publish step updates it
  in place without creating duplicates.
- **FR-010**: The publish/materialize step MUST continue to isolate per-view failure: a publish
  or materialize failure for one of the new views MUST be logged with the server's reason and
  reflected in the exit status, and MUST NOT prevent the remaining views from being attempted.
- **FR-011**: The Bundle ViewDefinition MUST be limited to Bundle-level metadata (e.g. type,
  timestamp, entry count, identifier) and MUST NOT attempt to flatten nested clinical content.

### Key Entities *(include if feature involves data)*

- **ViewDefinition (per resource type)**: The definition of a flattened view for one resource
  type — its stable identifier, the source resource type, the provenance/measure scoping, and
  the ordered set of output columns with the source field each draws from. Eleven new such
  definitions, alongside the existing Patient one.
- **Materialized view (per resource type)**: The server-side flattened table produced from each
  ViewDefinition — one row per resource of that type, columns as defined. The artifacts the
  analyst queries and joins.
- **Publish/materialize outcome**: The existing per-view record of upload result and
  materialization result (success/failure + reason), now spanning twelve views, surfaced to the
  operator and reflected in exit status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running the publish/materialize step against a server holding the processed
  test resources, a materialized view exists for each of the eleven listed resource types (plus
  the pre-existing Patient view) — twelve views total.
- **SC-002**: For each new view, a query returns exactly one row per first-class resource of
  that type that this project's processor persisted, and zero rows for unrelated resources of
  that type on the same server.
- **SC-003**: An analyst can retrieve the defined columns for any resource of a listed type
  from its materialized view using a single flat query, with no per-resource FHIR navigation.
- **SC-004**: Every column value in each materialized view either matches the corresponding
  source field or is null where the source field is absent — zero fabricated values.
- **SC-005**: For each new view, filtering on the CMS-measure column returns only the resources
  attributed to that measure, consistent with the Patient view's behavior.
- **SC-006**: Running the publish/materialize step delivers all eleven new views in a single
  invocation with no change to the operator's command, and re-running it results in exactly one
  copy of each view (no duplicates).
- **SC-007**: A single view's rejection by the server is reported with its reason and a
  non-zero exit, while every other view is still published and materialized.

## Assumptions

- **Demand-driven expansion, default column sets**: No finalized analytics-team column list was
  supplied for these resource types. Following the Patient precedent (002 FR-002 / Assumptions
  and 002 FR-012), each view ships an informed, reviewable default column set; the exact
  columns are confirmed with the analytics team during planning/review. This feature is the
  demand-driven addition the constitution's `TODO(VIEWDEF_RESOURCE_TYPES)` anticipated.
- **Per-type default columns (reviewable starting point)**:
  - **Condition**: resource key, clinical status, verification status, category, code
    (code + display), body site, subject reference, encounter reference, onset, recorded date.
  - **Encounter**: resource key, status, class, type, subject reference, period start/end,
    reason code, service provider reference, location reference.
  - **Observation**: resource key, status, category, code (code + display), value (quantity
    value + unit, and code/string variants), effective date/time, subject reference, encounter
    reference.
  - **Practitioner**: resource key, identifier (e.g. NPI), name (family, given), qualification
    code, gender.
  - **Organization**: resource key, identifier, name, type, address locality (city, state,
    postal code).
  - **Location**: resource key, identifier, name, type, physical type, address locality,
    managing organization reference.
  - **Measure**: resource key, url, identifier, name/title, status, the measure scoring,
    and the CMS-measure attribution column.
  - **Bundle**: resource key, type, timestamp, entry count, identifier (metadata-only per
    FR-011).
  - **Procedure**: resource key, status, code (code + display), category, subject reference,
    encounter reference, performed date/time, performer reference.
  - **MedicationRequest**: resource key, status, intent, medication (code + display or
    reference), subject reference, encounter reference, authored-on, requester reference.
  - **ServiceRequest**: resource key, status, intent, category, code (code + display), subject
    reference, encounter reference, authored-on, requester reference.
- **Uniform provenance + measure scoping**: Every persisted top-level resource carries this
  processor's `…/processed-by` and `…/cms-measure` tags (stamped per resource by the existing
  processor), so the provenance `where` filter (FR-005) and the CMS-measure column (FR-006)
  apply uniformly to all eleven types, exactly as for Patient.
- **Resources already persisted as first-class resources**: This feature consumes the
  first-class resources the existing processor produces (per the analytics-ready persistence
  granularity principle); it does not change how any resource is persisted.
- **Existing publish mechanism is reused unchanged**: The publish/materialize step already
  discovers and processes every ViewDefinition file in the views directory; delivering these
  views requires adding the files, not changing the step. Existing target-server configuration
  and OAuth2 authentication are reused; no new mechanism is introduced.
- **Single-valued column selection**: Where a resource has multiple values for a single-valued
  column (e.g. multiple identifiers or codings), a deterministic rule (e.g. first / preferred)
  is applied to keep one row per resource; the exact rule per column is settled in planning.
- **Target server is Aidbox**: "SQL-on-FHIR compliant" is interpreted as compliant with the
  ViewDefinition support in the configured Aidbox server, including its `$materialize`
  operation, consistent with the Patient view.
- **Zero-dependency runtime retained**: No runtime code change is expected for the publish
  step; if any helper is touched it stays within the project's stdlib-only constraint.
