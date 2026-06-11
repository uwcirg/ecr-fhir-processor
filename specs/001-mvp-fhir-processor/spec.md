# Feature Specification: MVP eCR FHIR Processor

**Feature Branch**: `add-constitution`

**Created**: 2026-06-09

**Status**: Draft

**Input**: User description: "MVP for this script. Note that I added a starter config.example.json here. One feature that I haven't mentioned yet: I'd like to add metadata to the FHIR resources before they are persisted to the FHIR server; this should indicate when they were processed, and that this system/software did the processing (I'd like to include a version number that I didn't need to hard-code in the config file, contrary to the example there). Re this metadata: I'd like it to be easy to filter on when I search the FHIR server."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Process and persist eCR test bundles to a FHIR server (Priority: P1)

A data manager places real chronic-disease eCR data (organized by CMS measure and
population outcome) in the root `input/` directory, supplies connection details for a
target FHIR server, and runs the script. The processor reads every FHIR bundle in the
input set, submits it to the FHIR server, and reports what was sent and whether the
server accepted it.

**Why this priority**: This is the core reason the tool exists — getting
surveillance data from local files into the public-health FHIR server. Without it,
nothing else matters.

**Independent Test**: During development, run the processor against the `test/input/`
fixtures pointed at a reachable FHIR server and confirm that the resources from every
scenario appear on the server and that the run reports success/failure per bundle.

**Acceptance Scenarios**:

1. **Given** a directory containing valid eCR scenario bundles and a reachable,
   authenticated FHIR server, **When** the processor runs, **Then** every input
   bundle is submitted to the server and the run reports each submission's outcome.
2. **Given** a standard scenario folder (collection Bundle + MeasureReport + eCR
   message Bundle), **When** the processor runs, **Then** all three bundles are
   submitted to the server.
3. **Given** a not-in-population scenario folder (collection Bundle + MeasureReport),
   **When** the processor runs, **Then** both bundles are submitted to the server.
4. **Given** the FHIR server rejects a submission, **When** that occurs, **Then** the
   processor surfaces the failure (logged and reflected in exit status) and does not
   report it as a success.

---

### User Story 2 - Stamp filterable processing metadata onto resources (Priority: P1)

Before anything is sent to the FHIR server, the processor marks each resource with
metadata recording (a) that this software processed it, (b) the software version,
(c) when it was processed, and (d) the name of the source JSON file it came from.
After submission, the data manager can search the FHIR server and retrieve exactly
the resources this processor wrote, filtering by the processing marker and/or
processing time, and can trace any persisted resource back to its source file.

**Why this priority**: Provenance and retrievability are a hard requirement from the
user. Surveillance servers accumulate data from many sources; being able to isolate
"what this processor sent, and when" is essential for auditing, re-runs, and cleanup.

**Independent Test**: After a processing run, issue a search against the FHIR server
filtering on the processing marker and confirm only the resources this run wrote are
returned; issue a second search filtering on processing time and confirm it narrows
results to the expected run.

**Acceptance Scenarios**:

1. **Given** a resource about to be persisted, **When** the processor prepares it,
   **Then** the resource carries a marker identifying this software as the processor,
   the software version, the processing timestamp, and the source JSON filename.
2. **Given** resources persisted by a processing run, **When** the data manager
   searches the FHIR server filtering on the processing marker, **Then** the search
   returns the resources this processor wrote and excludes unrelated resources.
3. **Given** resources persisted across different runs, **When** the data manager
   filters by processing time, **Then** results are scoped to the matching run(s).
4. **Given** the software version is not configured in the config file, **When** a
   resource is stamped, **Then** the version recorded reflects the actual running
   version of the software (not a value copied from configuration).
5. **Given** a persisted resource, **When** the data manager inspects or searches its
   metadata, **Then** they can identify the source JSON filename it was processed
   from.

---

### User Story 3 - Configure the run without editing code (Priority: P2)

An operator copies `config.example.json` to a real config file, fills in the FHIR
server URL and OAuth2 credentials, and runs the processor against their chosen input
and output locations — without modifying any source code.

**Why this priority**: Deployment-specific data must live in configuration, not code
(constitution: Configuration over Code). It is required for any real deployment but
the processing/metadata behavior (P1) can be demonstrated against a test server
first.

**Independent Test**: Copy the example config, populate it, run the processor, and
confirm it authenticates and connects to the configured server using only config
values.

**Acceptance Scenarios**:

1. **Given** a config file with FHIR server base URL and OAuth2 credentials, **When**
   the processor runs, **Then** it authenticates to the server and submits using
   those values.
2. **Given** a config file missing a required field, **When** the processor starts,
   **Then** it fails fast with a clear message naming the missing field.
3. **Given** the example config's placeholder values are left unchanged, **When** the
   processor runs, **Then** it does not silently succeed against an unintended target.

---

### User Story 4 - Deliver records for downstream SQL-on-FHIR analytics (Priority: P2)

A state Department of Health analytics team consumes the persisted data from **Aidbox**
using **SQL-on-FHIR `ViewDefinition`s** to build flat tables. They need **every record**
— in-population cases (whose eCR payload is the message Bundle) **and** not-in-population
cases — represented as **queryable, first-class FHIR resources** so a ViewDefinition can
flatten them. Of particular interest are each case's numerator/denominator membership
(from its MeasureReport) and the eICR **Composition** (the Public Health Case Report).

**Why this priority**: The persisted data's downstream purpose is analytics. If a record
lands in a shape SQL-on-FHIR cannot flatten (e.g., trapped inside an opaque, whole-stored
Bundle), the analytics team cannot consume it — defeating the reason the data was
persisted.

**Independent Test**: After a run against the fixtures, define a `ViewDefinition` over
`MeasureReport` and confirm it yields one row per case — for both in-population and
not-in-population scenarios — carrying the measure and population counts; confirm the
referenced clinical resources are independently queryable and join to that row by patient.

**Acceptance Scenarios**:

1. **Given** records persisted by a run, **When** a `ViewDefinition` selects over
   `MeasureReport`, **Then** every case (in-population and not-in-population) yields a row
   carrying its `measure` and population counts (initial-population/denominator/numerator/
   exclusion).
2. **Given** a not-in-population case (no eCR payload), **When** the analytics team builds
   their tables, **Then** the case is still represented via its zero-count MeasureReport
   and its collection-bundle clinical resources as first-class, queryable resources.
3. **Given** an in-population case, **When** its eCR payload is persisted, **Then** the
   payload is retained whole **and** the eICR `Composition` is additionally persisted as a
   first-class, queryable resource (FR-022), so a `ViewDefinition` over `Composition` can
   flatten it.

---

### Edge Cases

- **Unreachable / unauthenticated server**: The processor fails loudly with a clear
  message and a non-zero exit status; it does not partially "succeed" silently.
- **Malformed or unreadable input file**: The processor logs the problem at WARNING
  or above, skips that file, and reflects the issue in the run summary rather than
  aborting the entire run or silently dropping it.
- **Empty input location** (e.g., a measure folder with no data yet): The processor
  completes without error and reports that nothing was processed.
- **Resource already present on the server** (re-run of the same input): The processor
  updates the existing resource in place (same identity) rather than creating a
  duplicate. With unchanged input, the only fields that change are the metadata this
  processor adds (and the server's own managed metadata such as `lastUpdated` /
  `versionId`).
- **Server accepts some bundles and rejects others**: Each outcome is reported
  individually; overall exit status reflects that at least one failure occurred.
- **Two different resources share the same identity** (e.g., the fixed-id eICR document
  Bundle `eicr-report-ChronicDSDiabetesPoorControl` is reused across different patients
  with different content): The processor MUST NOT silently let one overwrite the other.
  It detects the `(type, id)` collision with differing content and fails loudly; an
  identical-content collision (shared reference resources reused across scenarios) is
  treated as intentional deduplication, not an error.
- **Not running inside a version-control checkout**: The processor still records a
  version value and does not crash when the version cannot be derived from version
  control (it records a clearly-marked fallback).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST read FHIR R4 bundles from the root `input/` directory
  (real data), organized by CMS measure and population outcome (Standard and
  Not-In-Population), processing every bundle file present. The `test/` directory
  (including `test/input/` and `test/output/`) holds development/test fixtures only
  and is not the source or destination for real data.
- **FR-002**: The system MUST submit every input bundle to the configured target FHIR
  server, persisting the resources it contains.
- **FR-003**: The system MUST process all bundle files present in each scenario folder
  as-is — the collection Bundle, the MeasureReport, and (when present) the eCR message
  Bundle — without selectively dropping any of them.
- **FR-004**: Before persistence, the system MUST add metadata to the FHIR resources
  it processes that records: (a) that this software performed the processing,
  (b) the software version, (c) the processing timestamp, and (d) the name of the
  source JSON file the resource was processed from.
- **FR-005**: The processing metadata MUST be expressed using FHIR-native, server-
  searchable mechanisms so that an operator can retrieve resources written by this
  processor using standard FHIR search (filtering by the processing marker and by
  processing time).
- **FR-006**: The software version recorded in the metadata MUST be determined at
  runtime from version control (e.g., the current tag/commit) and MUST NOT require
  being hard-coded in the configuration file. When version control information is
  unavailable, the system MUST record a clearly-marked fallback value rather than
  failing.
- **FR-007**: The processing timestamp recorded in the metadata MUST be precise enough
  to distinguish separate runs and MUST include a timezone offset.
- **FR-008**: Deployment-specific values (FHIR server base URL, OAuth2 token endpoint,
  client credentials) MUST be read from a configuration file and MUST NOT be hard-
  coded in source.
- **FR-009**: The system MUST authenticate to the FHIR server using the OAuth2
  credentials provided in configuration before submitting resources.
- **FR-010**: The system MUST validate required configuration at startup and fail fast
  with a clear, specific message identifying any missing or empty required field.
- **FR-011**: The system MUST NOT silently produce incorrect output or silently drop
  clinical content; every data-quality accommodation MUST be logged at WARNING level
  or above.
- **FR-012**: A bundle/resource that the server rejects MUST NOT be reported as
  successfully persisted; the failure MUST be logged and reflected in the run's exit
  status.
- **FR-013**: The system MUST log to both the console (immediate feedback) and a
  timestamped audit file, recording what was processed, what was submitted, and the
  outcome of each submission.
- **FR-014**: The system MUST report a per-run summary (counts of bundles read,
  submitted, succeeded, failed, and skipped) and exit with a non-zero status if any
  failure occurred.
- **FR-015**: The system MUST NOT alter the clinical meaning of input resources when
  adding processing metadata (metadata is additive provenance, not a content change).
- **FR-016**: The system MUST persist resources using a stable, known identity so that
  re-running the same input updates the existing resource(s) in place rather than
  creating duplicates. With unchanged input, a re-run MUST change only the metadata the
  processor adds (plus server-managed metadata such as `lastUpdated` / `versionId`).
- **FR-017**: The system MUST NOT break reference resolution between resources when
  persisting them: references that resolve in the source data MUST still resolve after
  persistence (the identity strategy chosen for FR-016 must keep references and their
  targets consistent).
- **FR-018**: The identity strategy — specifically whether the system retains each
  source resource's original `resource.id` or assigns new ids at persistence — MUST be
  decided during planning/implementation after inspecting representative data, and MUST
  satisfy FR-016 and FR-017. See Open Questions.
- **FR-019**: When, within a single run, the system encounters two resources that share
  the same `(resourceType, id)` but differ in content, it MUST NOT silently overwrite one
  with the other; it MUST surface the collision (logged at ERROR and reflected in exit
  status). Collisions where the content is identical (e.g., shared reference resources
  reused across scenarios) are expected deduplication and MUST NOT be treated as errors.
  This protects against silent data loss from non-unique/fixed resource ids in the source
  data (e.g., measure-named eICR document Bundle ids reused across patients).
- **FR-020**: The system MUST persist records so that each case's measure-evaluation
  (MeasureReport) and clinical resources land as **first-class, individually queryable
  FHIR resources** on the target server (Aidbox), enabling downstream SQL-on-FHIR
  `ViewDefinition`s to flatten them into analytics tables. This applies to **both**
  in-population and not-in-population cases.
- **FR-021**: Not-in-population cases — which have no eCR message Bundle — MUST still be
  represented for analytics via their (zero-count) MeasureReport and their collection-
  bundle clinical resources; the absence of an eCR payload MUST NOT cause a NIP case to
  be skipped or omitted from what lands on the server.
- **FR-022**: For each in-population eCR message Bundle, in addition to persisting the
  Bundle whole (FR-003), the system MUST extract the nested eICR `Composition` and persist
  it as a first-class, queryable resource under its own id, so SQL-on-FHIR can flatten it
  (US4, OQ-3). The system MUST promote **only** the `Composition` and MUST NOT re-persist
  the message Bundle's other nested resources — the eICR's clinical resources are
  lower-fidelity duplicates sharing `(resourceType, id)` with the collection-bundle
  resources, and re-persisting them would overwrite the clean copies and trip FR-019. (The
  Composition's id is unique and its references resolve to the already-persisted
  collection-bundle resources.)

### Key Entities *(include if data involved)*

- **Input Scenario**: A folder under root `input/` for one reporting case, grouped by
  CMS measure (`poor-diabetic-control`/CMS122, `controllable-bp`/CMS165,
  `depression-screening`/CMS2) and population outcome (Standard vs. Not-In-Population).
  Contains one or more FHIR bundle files. (The parallel structure under `test/input/`
  is development fixtures only.)
- **FHIR Bundle**: The unit read from input and submitted to the server — a collection
  Bundle of clinical resources, a MeasureReport, or an eCR message Bundle.
- **Processing Metadata**: Additive provenance attached to resources before
  persistence — identifies this software as processor, its runtime-derived version,
  the processing timestamp, and the source JSON filename; designed to be searchable on
  the FHIR server.
- **Run Configuration**: Deployment-specific settings (FHIR server base URL, OAuth2
  token endpoint, client id/secret) supplied via a config file derived from
  `config.example.json`.
- **Run Summary / Audit Log**: The console + file record of one execution, including
  per-bundle outcomes and the aggregate counts and exit status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the processor against an input set (the `test/input/` fixtures
  during development, the root `input/` directory in real use) results in 100% of
  present bundles being submitted to the target FHIR server, with each submission's
  success/failure reported.
- **SC-002**: After a run, an operator can retrieve exactly the set of resources that
  the processor wrote — and no unrelated resources — using a single FHIR search that
  filters on the processing marker.
- **SC-003**: An operator can narrow a FHIR search to a specific processing run using
  the processing-time metadata, returning only resources from that run.
- **SC-004**: 100% of resources persisted by the processor carry all four metadata
  facts (processor identity, software version, processing timestamp, source filename);
  none are missing.
- **SC-008**: Re-running the same unchanged input twice results in the same number of
  resources on the server after the second run as after the first (no duplicates), and
  the only resource fields that change are the processor-added metadata and the
  server's own managed metadata.
- **SC-005**: The recorded software version matches the actual running version with no
  configuration edit required between two different checked-out versions.
- **SC-006**: A run against a misconfigured setup (missing required field, unreachable
  server, or rejected submission) never reports false success: every such case yields
  a clear message and a non-zero exit status.
- **SC-007**: A new operator can go from `config.example.json` to a successful run by
  editing only the configuration file (no source-code edits).

## Assumptions

- **Input/output locations**: Real data lives in the root `input/` directory and real
  output/logs go to root-level destinations (e.g., `output/`, `log/`). The `test/`
  directory (`test/input/`, `test/output/`) is exclusively for development/test
  fixtures. The MVP reads from a directory tree shaped like
  `input/{measure}/{standard,not-in-population}/{scenario}/`. The exact way locations
  are supplied (CLI argument and/or config) is a plan-level detail, since
  `config.example.json` currently carries only server and software-identity fields.
- **Persistence scope (which bundles)**: Per the user's decision, the MVP persists
  **all input bundles** (collection Bundle, MeasureReport, and eCR message Bundle when
  present) and does not selectively drop any. Whether each bundle is persisted whole or
  unpacked into its constituent resources is an Open Question (see below).
- **Version source**: Per the user's decision, the software version is **derived from
  git** at runtime (e.g., tag and/or short commit). A clearly-marked fallback is used
  when git metadata is unavailable.
- **Filterable metadata mechanism**: "Easy to filter on" is satisfied using FHIR's
  standard searchable resource metadata (resource-level tags and source/processing
  timestamp), so existing FHIR search parameters can isolate this processor's output.
  The processor identity, version, processing timestamp, and source filename are all
  carried in this searchable metadata. The exact tag system/code and field choices are
  an implementation/plan decision constrained by FR-004 and FR-005.
- **Submission semantics**: Submissions are **idempotent updates** — re-running the
  same input updates the existing resources in place rather than creating duplicates
  (FR-016). This requires submitting each resource under a stable, known identity
  (an update against a known id, not a blind create). With unchanged input, only the
  processor-added metadata and server-managed metadata change on a re-run.
- **Authentication**: The target FHIR server uses OAuth2 client-credentials matching
  the fields in `config.example.json` (`token_endpoint`, `client_id`,
  `client_secret`).
- **Runtime constraints (from constitution)**: Implementation uses the Python 3
  standard library only (zero runtime dependencies), a single entry-point script,
  config-over-code, and secret protection (real `config.json` is git-ignored).
- **`software.version` in `config.example.json`**: This field is treated as redundant
  for provenance purposes given FR-006; the plan will reconcile the example config
  with the runtime-derived version (the user explicitly does not want the stamped
  version hard-coded there).
- **Target server & downstream analytics**: The target FHIR server is **Aidbox**. The
  persisted data's downstream consumer is a **state Department of Health** analytics team
  that queries it with **SQL-on-FHIR `ViewDefinition`s** (flattening first-class resources
  into tables). This is why the persistence granularity (OQ-2/D2) — first-class resources
  vs. whole Bundles — matters beyond MVP submission: it determines what is analyzable
  downstream (see US4, FR-020/021, OQ-3).
- **Out of scope for MVP**: Generating or transforming eCR content, computing
  MeasureReports, authoring the downstream `ViewDefinition`s themselves (the analytics
  team owns those), depression-screening (CMS2) fixtures (folders are empty
  placeholders), and any non-conformance remediation beyond loud failure are not part
  of this MVP.

## Open Questions

These are to be resolved during planning/implementation, after inspecting
representative data — the user has explicitly noted that the right answer depends on
undocumented patterns in the provider's data that will only surface once a few files
are processed.

- **OQ-1 — Resource identity strategy**: Does the processor **retain each source
  resource's original `resource.id`** when persisting, or **assign new ids**? Retaining
  ids is the natural way to satisfy the update-in-place / no-duplicates requirement
  (FR-016) and keeps existing references resolvable (FR-017). A key unknown is whether
  the data provider already uses globally-unique ids (e.g., GUIDs) for `resource.id`;
  if so, retaining them is straightforward; if ids are not stable/unique across files,
  an identity-mapping strategy is needed. **Investigation:** inspect `resource.id`
  values across several real input files for uniqueness/format before deciding.
- **OQ-2 — Persistence granularity (whole bundle vs. contained resources)**: The user
  may want to persist the **individual resources contained in each Bundle** (Patient,
  Condition, Encounter, etc.) as first-class resources on the server, rather than
  storing the Bundle as a single artifact. This is coupled to OQ-1 (each contained
  resource needs a stable identity and resolvable references). The decision is deferred
  until processing representative files reveals the necessary patterns. The current
  scope decision ("persist all input bundles") fixes *which* inputs are in scope; this
  question is about the *granularity* of what lands on the server.
- **OQ-3 — Expose the eICR `Composition` for SQL-on-FHIR? (refines OQ-2/D2)**: The
  downstream consumer (US4) analyzes data via Aidbox SQL-on-FHIR `ViewDefinition`s, which
  flatten **first-class** resources and **cannot** reach into a whole-stored Bundle. Under
  the current decision (research.md D2) the eCR message Bundle is persisted whole, so its
  nested eICR `Composition` / `MessageHeader` are **not** individually queryable. **Open:**
  should the processor unpack the message Bundle's document Bundle to persist the
  `Composition` (and `MessageHeader`) as first-class resources? **Constraint if yes:**
  promote **only** those genuinely-new, GUID-keyed resources — do **NOT** re-persist the
  eICR's nested clinical resources, which are lower-fidelity duplicates sharing GUIDs with
  the clean collection-bundle copies (re-persisting them would overwrite good data and trip
  FR-019). Resolve after confirming with the consumer whether the Composition is needed as
  a flat table for MVP. **Resolved (2026-06-11): yes** — promote the eICR `Composition` to
  a first-class resource (promote only the Composition; do not re-persist the nested
  clinical duplicates). See FR-022 and research.md **D2b**.

> Note: These open questions do not block writing the spec, but they should be settled
> in `/speckit-plan` (likely via a short data-inspection spike against real/`test`
> input) before implementation locks in an identity and submission approach.

## Dependencies

- A reachable target FHIR R4 server (**Aidbox**) with OAuth2 client-credentials
  authentication, whose SQL-on-FHIR capability the downstream DoH analytics team uses to
  build tables via `ViewDefinition`s (US4).
- The canonical input fixtures under `test/input/` (and the input-shape definitions in
  `docs/CDS_TestData_DocumentationFor05252026zip.pdf`).
- The project constitution (`.specify/memory/constitution.md`), whose principles
  (zero-dependency runtime, profile conformance, defensive processing, config-over-
  code, secret protection, clear output) constrain this feature.
