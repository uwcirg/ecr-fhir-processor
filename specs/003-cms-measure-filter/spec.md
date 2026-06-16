# Feature Specification: Filter Analytics by CMS Measure

**Feature Branch**: `003-cms-measure-filter`

**Created**: 2026-06-15

**Status**: Draft

**Input**: User description: "SQL on FHIR. I want to be able to easily filter by CMS measure, e.g. `CMS165` (`controllable-bp`), `CMS122` (`poor-diabetic-control`), `CMS2` (`depression-screening`). Currently we persist filename in the `…/CodeSystem/source-file` tag (the start of each test filename is the CMS measure, e.g. `CMS165_bulk_nip_late_htn_00500.json`). Recommendation requested: persist the CMS measure in a new tag (e.g. `…/CodeSystem/cms-measure` = `CMS165`) for ease of querying in the ViewDefinition and downstream? Prefer the filename (DRY) over a parent-directory name. Production data may lack this info, derived downstream; when the filename does not begin with `CMS[n]`, assign the tag value `unknown` (suggest a more FHIR-friendly alternative if one exists)."

## Clarifications

### Recommendation on the design questions the user raised

- **Q (persist a dedicated tag vs. parse the filename downstream?)** — **A**: Persist a
  dedicated tag. SQL-on-FHIR ViewDefinitions and `_tag` queries filter cleanly on a
  `(system, code)` pair — the same mechanism the existing Patient view already uses for the
  `…/processed-by` provenance tag (002-patient-viewdefinition FR-013). Recovering `CMS165`
  by string-prefix-parsing the `source-file` filename in SQL is brittle (variable digit
  counts, delimiter assumptions) and is not how ViewDefinition `where`/column selection is
  meant to work. A first-class `…/CodeSystem/cms-measure` tag with code `CMS165` is directly
  filterable and self-describing. **Recommended: yes, add the tag.**

- **Q (single source of truth — filename vs. parent directory?)** — **A**: Derive the CMS
  code from the **filename prefix** (the user's DRY preference), not the parent directory.
  The directory slug (`controllable-bp`) and the filename prefix (`CMS165`) carry the same
  fact; the filename is the value the user commits to maintaining by convention before
  running `process.py`, so it is the canonical source. The directory-derived `measure` slug
  still drives the human-facing output path and the `--measure` filter — those are unchanged.

- **Q (is there a more FHIR-friendly value than `unknown`?)** — **A**: Two reasonable
  options. (1) Keep one tag system (`…/CodeSystem/cms-measure`) and declare `unknown` as an
  explicit concept in that project-owned CodeSystem — so every CMS-measure filter targets a
  single system with codes `{CMS2, CMS122, CMS165, unknown}`. (2) Use the HL7 standard
  DataAbsentReason code `unknown`
  (`http://terminology.hl7.org/CodeSystem/data-absent-reason#unknown`). **Recommended:
  option (1)** — a positive `unknown` sentinel in the same system keeps all measure filtering
  against one system, lets analysts *positively* list/count the un-attributed resources (more
  useful than a NOT-EXISTS query over absent tags), and stays consistent with how
  `source-file` is already modeled as a project CodeSystem. The HL7 DataAbsentReason value is
  noted as the standards-purist alternative if cross-system reuse is later preferred.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyst filters analytics to a single CMS measure (Priority: P1)

A state Department of Health (DoH) analyst wants to see flattened analytics for just one
quality measure at a time — e.g. only the Controlling High Blood Pressure (CMS165 /
`controllable-bp`) patients, excluding diabetes and depression-screening patients on the same
server. Against their SQL-on-FHIR tooling they apply a single CMS-measure predicate and get
back only the rows whose underlying resources were attributed to that measure.

**Why this priority**: This is the user-facing goal of the feature — measure-scoped querying
is what the analyst actually asked for. Everything else exists to make this one predicate
possible.

**Independent Test**: Persist resources from files named `CMS165_*` and `CMS122_*`, then
filter the materialized Patient view (or a `_tag` query) to `CMS165` and confirm exactly the
CMS165-sourced patients are returned and the CMS122 ones are excluded.

**Acceptance Scenarios**:

1. **Given** persisted resources sourced from both `CMS165_*` and `CMS122_*` files, **When**
   the analyst filters analytics to the CMS165 measure, **Then** only the resources sourced
   from `CMS165_*` files are returned.
2. **Given** the materialized Patient view, **When** the analyst selects the CMS-measure
   column, **Then** each row shows the CMS measure its source resource was attributed to (one
   of `CMS2`, `CMS122`, `CMS165`, or `unknown`).

---

### User Story 2 - Processor attributes each persisted resource to its CMS measure (Priority: P1)

When the operator runs the processor, every resource it persists is stamped with the CMS
measure derived from its source filename, so the attribution travels with the resource on the
server and is available to any downstream consumer — not just one specific view.

**Why this priority**: The filter in User Story 1 is only possible if the attribution is
persisted onto the resources at processing time. This is the data-production half of the same
deliverable and must ship together with US1.

**Independent Test**: Process a file named `CMS122_*` and inspect the persisted resources;
confirm each carries a single CMS-measure tag with code `CMS122`, alongside the existing
`source-file` and provenance tags.

**Acceptance Scenarios**:

1. **Given** an input file whose name begins with the CMS convention (e.g.
   `CMS165_bulk_nip_late_htn_00500.json`), **When** the processor persists its resources,
   **Then** each persisted resource carries exactly one CMS-measure tag with code `CMS165`.
2. **Given** the same input re-processed, **When** the processor re-stamps, **Then** the
   resource still carries exactly one CMS-measure tag (the prior one is replaced, not
   duplicated), consistent with the existing idempotent provenance stamping.
3. **Given** a file whose name does **not** begin with the CMS convention, **When** the
   processor persists its resources, **Then** each carries a CMS-measure tag with code
   `unknown`.

---

### User Story 3 - Operator re-attributes "unknown" resources later (Priority: P2)

For production data that arrived without a determinable measure, the resources land tagged
`unknown`. Once the operator determines the measure downstream, they rename the source
file(s) to the CMS convention and re-run the processor; the previously-`unknown` resources are
re-attributed in place, and the count of `unknown` resources drops accordingly.

**Why this priority**: Directly supports the user's stated production workflow (measure
determined later, files renamed before re-processing). It depends on US2's idempotent stamping
but is a distinct, separately demonstrable journey; not required for the first MVP slice.

**Independent Test**: Process a non-conforming filename (resources tagged `unknown`), then
rename it to `CMS2_*`, re-process, and confirm the same resources now carry code `CMS2` with
no duplicate tag and no duplicate resource.

**Acceptance Scenarios**:

1. **Given** resources previously persisted with CMS-measure `unknown`, **When** their source
   file is renamed to the CMS convention and re-processed, **Then** those same resources
   (same ids) carry the corresponding CMS code and no longer count as `unknown`.

---

### Edge Cases

- **Variable digit count**: the CMS number varies in length (`CMS2`, `CMS122`, `CMS165`). The
  derivation MUST accept `CMS` followed by one or more digits as the leading token, not a
  fixed width.
- **Case / formatting**: a filename like `cms165_…` or `CMS165-…` — the derivation rule for
  what counts as the CMS token and how the code is normalized (e.g. uppercased to `CMS165`)
  MUST be deterministic and documented (see Assumptions).
- **CMS-like but non-numeric prefix** (e.g. `CMSX_…`, `CMSReport_…`): does NOT match the
  convention → tagged `unknown` (only `CMS` + digits qualifies).
- **Directory/filename disagreement**: a `CMS122_*` file located under a `controllable-bp/`
  (CMS165) directory. The filename wins for the CMS-measure tag (single source of truth), but
  the disagreement is a data-quality signal and MUST be logged as a warning (constitution
  Principle V), not silently reconciled.
- **No CMS token at all** (production data): tagged `unknown`; the resource is still persisted
  and analyzable — it simply filters into the `unknown` bucket.
- **Resources persisted before this feature existed**: they carry no CMS-measure tag until
  re-processed; re-running the processor backfills the tag idempotently (US3 mechanism).
- **Mixed-measure content in one file** (not expected per the fixtures, but possible): the
  measure is attributed at the file level from the filename, so all resources from that file
  share the file's CMS code; if a single file ever legitimately spans measures, that is out of
  scope and would be flagged for follow-up rather than silently mis-attributed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The processor MUST derive a CMS measure code from the source file's name,
  recognizing a leading token of the form `CMS` immediately followed by one or more digits
  (e.g. `CMS2`, `CMS122`, `CMS165`).
- **FR-002**: The processor MUST stamp the derived CMS measure onto each resource it persists,
  as a dedicated, queryable tag in a project-owned system (proposed
  `…/CodeSystem/cms-measure`), distinct from the existing `source-file` tag.
- **FR-003**: The CMS-measure tag MUST be applied to exactly the same set of resources the
  processor already stamps with `source-file` provenance — i.e. every resource it persists —
  so attribution is uniform across resource types (Patient, Encounter, Condition,
  Observation, MeasureReport, the promoted Composition, etc.).
- **FR-004**: When the source filename does not match the CMS convention, the processor MUST
  stamp the CMS-measure tag with the sentinel code `unknown` (a declared concept in the
  project's CMS-measure code system) rather than omitting the tag.
- **FR-005**: CMS-measure stamping MUST be idempotent and re-runnable: re-processing a file
  replaces the resource's own prior CMS-measure tag in place (never appends a second), exactly
  as the existing provenance tags behave.
- **FR-006**: The CMS-measure code MUST be normalized to a single canonical form (uppercase
  `CMS<digits>`, e.g. `CMS165`) regardless of incidental filename casing, so downstream
  filters match a single code per measure.
- **FR-007**: When the CMS measure derived from the filename disagrees with the
  directory-derived measure slug for the same file, the processor MUST log a warning recording
  both values; the filename-derived value is authoritative for the tag.
- **FR-008**: Downstream consumers MUST be able to filter persisted resources to a single CMS
  measure (or to `unknown`) using only this tag — without parsing the `source-file` filename.
- **FR-009**: The Patient ViewDefinition MUST expose the CMS measure as a selectable column so
  an analyst can filter the flattened Patient view to a single measure with one predicate.
  (Other resource-type views remain demand-driven per constitution Principle VII; they are not
  added speculatively, but the tag is present on their resources for `_tag` filtering.)
- **FR-010**: The canonical mapping between CMS code and the human-readable measure slug
  (`CMS2` ↔ `depression-screening`, `CMS122` ↔ `poor-diabetic-control`, `CMS165` ↔
  `controllable-bp`) MUST be recorded in a single authoritative place so code and slug cannot
  drift independently.

### Key Entities *(include if feature involves data)*

- **CMS measure code**: The canonical attribution of a resource to a CMS quality measure —
  one of `CMS2`, `CMS122`, `CMS165`, or the sentinel `unknown`. Derived from the source
  filename; maps 1:1 to a human-readable slug (`depression-screening`,
  `poor-diabetic-control`, `controllable-bp`).
- **CMS-measure tag**: The persisted, queryable carrier of the CMS measure code on each
  resource (a `meta.tag` entry in the project-owned CMS-measure system), parallel to and
  independent of the existing `source-file` and `processed-by` tags.
- **CMS-measure column (Patient view)**: The flattened, analyst-facing exposure of the CMS
  measure code in the materialized Patient view, enabling a single-predicate measure filter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After processing files named for two different measures, a query filtered to one
  CMS measure returns exactly the resources sourced from that measure's files and none from
  the other — verifiable without inspecting filenames.
- **SC-002**: 100% of resources the processor persists carry exactly one CMS-measure tag whose
  code is either a canonical `CMS<n>` value or `unknown` (no resource is left un-attributed,
  none carries two).
- **SC-003**: An analyst can restrict the materialized Patient view to a single CMS measure
  with one filter predicate, with no string parsing of any filename.
- **SC-004**: Re-processing a file after renaming it from a non-conforming name to the CMS
  convention changes the affected resources' CMS-measure code in place (no duplicate tag, no
  duplicate resource) and reduces the count of `unknown`-tagged resources accordingly.
- **SC-005**: Every CMS-measure code present on persisted resources is one of the canonical
  values or `unknown` — zero ad-hoc or malformed measure codes appear on the server.
- **SC-006**: When a file's filename-derived measure disagrees with its directory-derived
  slug, the run's logs contain a warning naming both values (the disagreement is never silent).

## Assumptions

- **Derivation rule**: The CMS code is the leading `CMS`+digits token of the filename, matched
  case-insensitively and normalized to uppercase `CMS<digits>` (e.g. `cms165_x.json` →
  `CMS165`). Anything not matching that leading pattern yields `unknown`. This rule is the
  single source of truth; the parent-directory slug is not consulted for the tag value.
- **`unknown` sentinel choice**: `unknown` is modeled as an explicit concept within the
  project-owned `…/CodeSystem/cms-measure` system (recommended over omitting the tag and over
  the HL7 DataAbsentReason `unknown`), so all measure filtering — including "show me the
  un-attributed resources" — targets one system. The HL7 DataAbsentReason value remains an
  available alternative if cross-system standardization is later prioritized.
- **Tag system name**: `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure`
  is the proposed system, mirroring the existing provisional `source-file`/`processed-by`
  hosts; the exact canonical host is confirmed at the same time as the other CodeSystems
  (it only needs to be a stable constant).
- **Tag breadth**: The CMS-measure tag is stamped on the same resource set as `source-file`
  (every persisted resource), added alongside the existing tags by the same idempotent
  stamping mechanism — not a separate pass.
- **Patient view column**: Exposing CMS measure as a Patient-view column is the default way to
  satisfy "ease of querying in the ViewDefinition"; separate per-measure views are explicitly
  NOT created (that would violate the DRY, demand-driven ViewDefinition principle). Other
  resource types rely on `_tag` filtering until the analytics team requests their own views.
- **Canonical measure mapping**: The three supported measures and their slugs are taken from
  constitution Principle IV (`CMS2`=`depression-screening`, `CMS122`=`poor-diabetic-control`,
  `CMS165`=`controllable-bp`). CMS2/`depression-screening` has no fixtures yet but is in
  scope; its files, when they arrive, are expected to follow the same `CMS2_*` convention.
- **No change to persistence granularity or the measure-derived output path**: This feature
  only adds an attribution tag (and a Patient-view column); it does not change which resources
  are persisted, how, or the `output/{measure}/{date}/` mirror path (still directory-derived).
