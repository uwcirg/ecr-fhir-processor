# Feature Specification: ViewDefinitions for the Missing Persisted Resource Types

**Feature Branch**: `006-missing-viewdefinitions`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "we are missing ViewDefinitions for at least one resource in viewdefinitions/"

## Clarifications

### Session 2026-07-06

- **Q**: `MeasureReport` is persisted as a first-class resource but has no view, while the
  existing `measure.ViewDefinition.json` targets `Measure` — a resource type that never appears
  in the eCR data and is never persisted, so it materializes to zero rows forever. How should
  this be resolved? — **A**: Remove the misdirected `Measure` view and add a `MeasureReport`
  view in its place. The `Measure` view is dead (it can never return a row from this data) and
  is retired; the real gap — no view over the persisted `MeasureReport` resources — is closed.
- **Q**: `Composition` is also promoted to a first-class resource (one per eICR case) but has no
  view. Should this feature add a `Composition` view too? — **A**: Yes, a metadata-oriented view
  exposing document-level metadata (type, status, subject, encounter, date, title,
  author/custodian references), not flattened section content. This brings every
  persisted-first-class resource type under a view.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst queries measure-result data as a flat table (Priority: P1)

A state Department of Health (DoH) analyst already has flat, columnar views over the clinical
and reference resources (Patient, Condition, Encounter, Observation, etc.). What they cannot yet
query flatly is the **measure result** each processed eCR carries — the `MeasureReport` that
records which measure was evaluated, for which patient/period, the population counts, and the
overall result. Today there is a view pointed at `Measure` (a resource type this pipeline never
produces), so it is always empty, while the `MeasureReport` resources the processor actually
persists have no view at all. The analyst opens their SQL-on-FHIR tooling and finds a
`MeasureReport` view already defined and materialized, one row per persisted MeasureReport, with
the analytically-relevant columns.

**Why this priority**: The MeasureReport is the resource that ties a processed eCR to its CMS
measure outcome. Without a view over it, the single most measure-relevant resource in the
dataset is unqueryable as a flat table — and the slot that should hold it is occupied by a view
that can never return a row. This is the core defect the feature exists to fix.

**Independent Test**: Persist the test eCR resources (which include one MeasureReport per
scenario) to a server, run the publish/materialize step, then issue a flat SQL query against the
MeasureReport view and confirm one row per persisted MeasureReport with the expected columns
populated (measure identifier, status, patient/subject reference, reporting period, measure
score/populations, and the CMS-measure attribution).

**Acceptance Scenarios**:

1. **Given** MeasureReport resources persisted as first-class resources on the target server,
   **When** the operator runs the publish/materialize step, **Then** a MeasureReport view exists
   and is materialized, returning one row per persisted MeasureReport.
2. **Given** the materialized MeasureReport view, **When** the analyst selects its columns,
   **Then** each column reflects the corresponding field of the source MeasureReport (e.g.
   measure reference/canonical, status, subject reference, reporting period start/end,
   population counts, measure score).
3. **Given** the MeasureReport view, **When** the analyst filters on the CMS-measure column,
   **Then** only rows whose underlying MeasureReport was attributed to that measure are returned
   — the same measure-scoping every other view supports (003-cms-measure-filter).
4. **Given** the retired `Measure` view, **When** the operator runs the publish/materialize step,
   **Then** no `Measure` view is published and no empty `Measure` view remains on the server from
   this project's ViewDefinition set.

---

### User Story 2 - Analyst accounts for the source clinical documents (Priority: P2)

The processor promotes the eICR `Composition` (the clinical document header) to a first-class
resource, one per case. The analyst needs to account for those documents — which patient and
encounter each document describes, its type, status, date, title, and the authoring/custodian
organizations — without reaching into the promoted Composition's nested section content (whose
clinical payload is already promoted to its own first-class resources and covered by the other
views). The analyst finds a Composition view exposing that document-level metadata, one row per
persisted Composition.

**Why this priority**: The Composition is the provenance anchor of each eICR — it says "this
document, of this type, about this patient/encounter, from this custodian." A metadata view over
it lets analysts count and attribute source documents and join them to the clinical resources
they describe. It is secondary to the MeasureReport view because it carries no measure-outcome
data and its clinical content is already available through the other views.

**Independent Test**: Persist the test eCR message bundles (each promotes one Composition), run
the publish/materialize step, then query the Composition view and confirm one row per persisted
Composition with document-level metadata columns populated and no attempt to expand section
content.

**Acceptance Scenarios**:

1. **Given** promoted Composition resources persisted on the target server, **When** the operator
   runs the publish/materialize step, **Then** a Composition view exists and is materialized,
   returning one row per persisted Composition.
2. **Given** the materialized Composition view, **When** the analyst selects its columns, **Then**
   each column reflects a document-level field (e.g. type, status, subject reference, encounter
   reference, date, title, author reference, custodian reference) and no column expands nested
   section/clinical content.
3. **Given** the Composition view, **When** the analyst filters on the CMS-measure column, **Then**
   only Compositions attributed to that measure are returned, consistent with every other view.

---

### User Story 3 - Every persisted first-class resource type has exactly one view (Priority: P2)

An operator or reviewer can enumerate the resource types this processor persists as first-class,
individually-addressable resources and confirm that each has exactly one checked-in
ViewDefinition, and that no checked-in ViewDefinition targets a resource type the processor never
persists. Running the existing publish/materialize step delivers all views in one invocation with
no change to its mechanism or invocation.

**Why this priority**: This is the closure condition for the whole ViewDefinition effort
(002/003/004 plus this feature): the set of views is neither missing a persisted type nor
carrying a view that can never return a row. It guards against the exact class of defect this
feature fixes recurring silently.

**Independent Test**: List the resource types the processor persists first-class (from a full run
over the test corpus) and the target-type of every checked-in ViewDefinition; confirm the two
sets match — no persisted type without a view, no view without a persisted type.

**Acceptance Scenarios**:

1. **Given** the checked-in ViewDefinition set after this feature, **When** the set of their
   target resource types is compared to the set of resource types the processor persists
   first-class, **Then** the two sets are equal.
2. **Given** the new and retired views, **When** the operator runs the publish/materialize step
   with its usual invocation, **Then** the MeasureReport and Composition views are published and
   materialized, the `Measure` view is no longer published, and the operator's command is
   unchanged.

---

### Edge Cases

- **No MeasureReport / Composition of that type on the server**: materialization still succeeds
  and the step reports success (exit 0); an empty view is not a failure and returns zero rows.
- **A backing field is absent** (e.g. a MeasureReport with no measure score, a Composition with no
  title): the corresponding column is null for that row, not an error; no value is fabricated.
- **MeasureReport with multiple population groups / stratifiers**: a deterministic selection or
  unnest rule keeps the view one-row-per-resource unless an explicit `forEach`/unnest is chosen for
  a multi-valued column, decided in planning. (Note: the processor already prunes value/component-less
  strata — see 005 — so the view reflects the post-prune resource.)
- **Reference columns** (MeasureReport `subject`/`reporter`, Composition `subject`/`encounter`/
  `author`/`custodian`): the view exposes the referenced resource's key via `getReferenceKey()`
  (which matches the target view's `getResourceKey()` `id`), not the resolved target or a raw
  `.reference` string (a raw `.reference` resolves to null under Aidbox's reference normalization —
  see 004 Edge Cases / research R4). Cross-view joins are the analyst's to make.
- **Composition section content**: the Composition view is metadata-only; it MUST NOT flatten
  nested section/clinical content, which is already promoted to first-class resources and covered
  by the other views.
- **A promoted Composition whose references don't resolve** (the processor WARNs on these, D2b/D3):
  the reference-key column is still populated from the reference; the view does not attempt to
  verify the target exists — resolution is the analyst's join.
- **A persisted resource lacks the CMS-measure or provenance tag**: it is excluded by the provenance
  `where` filter; if present but un-attributed, its CMS-measure column is the `unknown` sentinel.
- **Server rejects a view as non-conformant**: the step surfaces the server's validation error and
  exits non-zero for that view; it does not silently skip, and the other views proceed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The project MUST include a checked-in, version-controlled ViewDefinition resource
  targeting `MeasureReport`. It MUST conform to the SQL-on-FHIR ViewDefinition specification as
  implemented by the target server (Aidbox) and produce one row per persisted first-class
  MeasureReport resource.
- **FR-002**: The project MUST include a checked-in, version-controlled ViewDefinition resource
  targeting `Composition`, limited to document-level metadata. It MUST conform to the same
  specification and produce one row per persisted first-class Composition resource.
- **FR-003**: The existing `measure.ViewDefinition.json` (target resource type `Measure`) MUST be
  removed from the checked-in ViewDefinition set, because the processor never persists a `Measure`
  resource, so that view can never return a row. After this feature no checked-in ViewDefinition
  MUST target a resource type the processor does not persist.
- **FR-004**: The MeasureReport ViewDefinition MUST expose an informed, reviewable default set of
  analytically-relevant columns, including at minimum a stable resource key and the measure
  attribution, the measure reference/canonical, status, the subject reference, the reporting
  period, and the population/score data (see Assumptions for the default column set). The column
  set is a reviewable starting point settled with the analytics team, not a finalized contract.
- **FR-005**: The Composition ViewDefinition MUST expose an informed, reviewable default set of
  document-level metadata columns (see Assumptions) and MUST NOT flatten nested section or clinical
  content.
- **FR-006**: Each new ViewDefinition MUST select only from first-class, individually-addressable
  resources on the server — never from content nested inside an un-promoted Bundle.
- **FR-007**: Each new ViewDefinition MUST be published and materialized by the existing
  publish/materialize step with no change to that step's mechanism or invocation — the step
  auto-discovers every ViewDefinition file in the views directory (002 FR-011, 004 FR-004).
- **FR-008**: Each new ViewDefinition MUST restrict its rows to resources persisted by this
  project's processor — those bearing the processor's provenance tag (`meta.tag` system
  `…/processed-by`, code `ecr-fhir-processor`), version-agnostic — so unrelated resources of the
  same type on the same server MUST NOT appear (mirrors 002 FR-013 / 004 FR-005).
- **FR-009**: Each new ViewDefinition MUST expose the CMS-measure attribution as a column drawn
  from the `…/CodeSystem/cms-measure` tag, so both views support the same measure-scoped filtering
  every other view supports (mirrors 003-cms-measure-filter / 004 FR-006).
- **FR-010**: When a field that backs a column is absent on a given resource, that column MUST be
  null for that row; the views MUST NOT fabricate values.
- **FR-011**: Where a resource has multiple values for a column intended to be single-valued (e.g.
  a MeasureReport with multiple population groups), each ViewDefinition MUST apply a deterministic
  selection rule so the view remains one-row-per-resource unless an explicit unnest is intentionally
  chosen for that column.
- **FR-012**: Each new ViewDefinition MUST carry a stable identifier and a human-readable
  name/description, consistent with the existing views, so re-running the publish step updates it in
  place without creating duplicates.
- **FR-013**: The publish/materialize step MUST continue to isolate per-view failure: a publish or
  materialize failure for either new view MUST be logged with the server's reason and reflected in
  the exit status, and MUST NOT prevent the remaining views from being attempted.

### Key Entities *(include if feature involves data)*

- **MeasureReport ViewDefinition**: The definition of a flattened view over the persisted
  MeasureReport resources — its stable identifier, the source resource type (`MeasureReport`), the
  provenance/measure scoping, and the ordered output columns (measure attribution, status, subject,
  period, populations/score) with the source field each draws from.
- **Composition ViewDefinition**: The definition of a metadata-only flattened view over the
  promoted Composition resources — stable identifier, source type (`Composition`),
  provenance/measure scoping, and document-level metadata columns.
- **Retired Measure ViewDefinition**: The existing `measure.ViewDefinition.json` targeting a
  never-persisted `Measure` type, removed by this feature.
- **Materialized views**: The server-side flattened tables produced from the two new
  ViewDefinitions — one row per resource of that type — that the analyst queries and joins.
- **Persisted-type ↔ view correspondence**: The invariant that the set of ViewDefinition target
  types equals the set of resource types the processor persists first-class.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running the publish/materialize step against a server holding the processed
  test resources, a materialized MeasureReport view exists and returns one row per persisted
  MeasureReport (one per scenario in the test corpus), with zero rows for unrelated resources.
- **SC-002**: After the same run, a materialized Composition view exists and returns one row per
  persisted (promoted) Composition, with document-level metadata columns populated and no
  section/clinical content expanded.
- **SC-003**: No `Measure` view is published by this project's ViewDefinition set after this
  feature, and no checked-in ViewDefinition targets a resource type the processor never persists.
- **SC-004**: The set of target resource types across all checked-in ViewDefinitions equals the set
  of resource types the processor persists first-class — no persisted type without a view, no view
  without a persisted type.
- **SC-005**: For each new view, filtering on the CMS-measure column returns only the resources
  attributed to that measure, consistent with every other view.
- **SC-006**: Every column value in each new materialized view either matches the corresponding
  source field or is null where the source field is absent — zero fabricated values.
- **SC-007**: Running the publish/materialize step delivers both new views (and drops the retired
  one) in a single invocation with no change to the operator's command, and re-running it results
  in exactly one copy of each view (no duplicates).

## Assumptions

- **The missing types are MeasureReport and Composition**: A full run over the test corpus persists
  these resource types first-class: Patient, Condition, Encounter, Observation, Practitioner,
  Organization, Location, Procedure, MedicationRequest, ServiceRequest, the message Bundle, the
  promoted Composition, and the MeasureReport. Of these, every type had a view except MeasureReport
  and Composition; additionally the `measure.ViewDefinition.json` targeted `Measure`, which is never
  persisted. `MessageHeader` and other resources nested inside the persisted message Bundle are NOT
  individually persisted (they live only inside the Bundle) and therefore correctly need no view.
- **Demand-driven expansion, default column sets**: Following the Patient/004 precedent (002 FR-002,
  004 FR-002), each new view ships an informed, reviewable default column set; the exact columns are
  confirmed with the analytics team during planning/review, not blocked on them.
- **MeasureReport default columns (reviewable starting point)**: resource key, measure
  reference/canonical URL, status, type, subject reference, reporter reference, reporting period
  start/end, per-group measure score and population code + count (single-group selection rule or an
  explicit unnest decided in planning), the improvement notation where present, and the CMS-measure
  attribution column.
- **Composition default columns (metadata-only, reviewable starting point)**: resource key, status,
  type (code + display), category, subject reference, encounter reference, date, title, author
  reference, custodian reference, and the CMS-measure attribution column. No section/entry content.
- **Retire, don't repurpose the file**: Per the clarification, `measure.ViewDefinition.json` is
  removed and a new `measurereport.ViewDefinition.json` is added, rather than editing the existing
  file in place — a clean delete + new file. Any downstream reference to a "Measure" view is
  expected to be none, since the view never returned rows.
- **Uniform provenance + measure scoping**: Every persisted top-level resource carries this
  processor's `…/processed-by` and `…/cms-measure` tags (stamped per resource by the existing
  processor), so the provenance `where` filter (FR-008) and the CMS-measure column (FR-009) apply to
  both new views exactly as for the existing views.
- **Resources already persisted as first-class resources**: This feature consumes the first-class
  MeasureReport and Composition resources the existing processor already produces (per the
  analytics-ready persistence-granularity principle); it does not change how any resource is
  persisted.
- **Existing publish mechanism is reused unchanged**: The publish/materialize step already discovers
  and processes every ViewDefinition file in the views directory; delivering these views requires
  adding two files and removing one, not changing the step. Existing target-server configuration and
  OAuth2 authentication are reused.
- **Target server is Aidbox**: "SQL-on-FHIR compliant" means compliant with the ViewDefinition
  support in the configured Aidbox server, including its `$materialize` operation, consistent with
  the existing views.
- **Zero-dependency runtime retained**: No runtime code change is expected for the publish step; if
  any helper is touched it stays within the project's stdlib-only constraint.
- **Conformance baseline must be regenerated**: Because the checked-in ViewDefinition set changes,
  any test/regression baseline that enumerates the views (e.g. discovery/publish tests) is updated
  in the same change so the gate reflects the intended set rather than falsely flagging the removal
  of the Measure view or the addition of the two new ones.
