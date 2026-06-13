# Feature Specification: MVP eCR FHIR Processor

**Feature Branch**: `indi-resources` (feature dir `specs/001-mvp-fhir-processor`; earlier work on `add-constitution` / `mvp-impl`)

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

### User Story 4 - Make persisted eCR content queryable for downstream analytics (Priority: P1)

A state Department of Health analytics team consumes the persisted data by authoring
SQL-on-FHIR `ViewDefinition`s that flatten stored resources into analytic tables. Their
tooling can flatten only **first-class, individually-addressable** resources on the FHIR
server — it cannot reach into a resource stored opaquely inside a Bundle. They need each
clinical resource from a scenario, and the eICR **Composition** for in-population cases, to
be retrievable on its own so it is analyzable.

**Why this priority**: This is the reason the persistence-granularity decision exists.
Storing each scenario as one opaque Bundle would put the clinical content out of reach of
the downstream analytics, defeating the purpose of persisting it. What is persisted as a
first-class resource is what is analyzable downstream.

**Independent Test**: After a processing run, query the server for an individual contained
resource (e.g., a specific Patient or Observation from a scenario) and, for an in-population
scenario, for the eICR Composition by its id; confirm each returns as a standalone resource,
not only as part of a stored Bundle.

**Acceptance Scenarios**:

1. **Given** a collection Bundle has been persisted, **When** the analytics consumer queries
   for a contained resource type (e.g., all Observations this run wrote), **Then** each
   contained resource is returned individually as a first-class resource, not only nested
   inside a stored Bundle.
2. **Given** an in-population scenario (with an eCR message Bundle) has been persisted,
   **When** the consumer retrieves the eICR Composition by its id, **Then** it is returned
   as a standalone, first-class resource.
3. **Given** the eICR's nested clinical resources are lower-fidelity duplicates of the
   collection Bundle's resources, **When** the consumer queries those clinical resources,
   **Then** the results reflect the authoritative (higher-fidelity) collection-Bundle
   content, never overwritten by the eICR's degraded copies.
4. **Given** one resource type was rejected by the server during a run, **When** the consumer
   queries the other resource types from that run, **Then** they are present and queryable —
   the rejection of one type did not block persistence of the others.

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
- **Server rejects one resource type while accepting the rest** (e.g., it rejects the test
  MeasureReports on validation): The rejected resources are reported failed and are **not**
  counted as persisted, but every other resource type still persists — there is no
  all-or-nothing transaction that lets one rejected type undo or block the others. The exit
  status reflects the failure.
- **Operator persists resource types in separate runs**: When the operator chooses to
  persist only a subset of resource types in a run (e.g., everything except a type the
  server currently rejects), the excluded resources are reported **skipped** (not failed),
  and a later run for just that type — after the server's validation rules are relaxed —
  persists it without creating duplicates or disturbing the resources already persisted.
- **Promoted eICR Composition references an unresolved resource**: If the eICR Composition
  references a resource that was not persisted, the processor logs a WARNING (it does not
  fabricate or mutate the reference); the Composition is still persisted as a first-class
  resource.
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
- **FR-003**: By default, the system MUST process all bundle files present in each scenario
  folder as-is — the collection Bundle, the MeasureReport, and (when present) the eCR message
  Bundle — without selectively dropping any of them. (An operator MAY deliberately scope a run
  to a subset of resource types per FR-023; excluded resources are reported skipped, not
  dropped silently.)
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
- **FR-020**: The system MUST persist the resources contained in each collection Bundle as
  **independent, individually-addressable** resources on the FHIR server — each retrievable
  and searchable on its own — rather than storing the collection Bundle as a single opaque
  artifact. (This resolves OQ-2: persistence granularity is the contained resources, not the
  whole Bundle.)
- **FR-021**: For in-population scenarios that include an eCR message Bundle, the system MUST
  additionally persist the eICR **Composition** contained within it as an independent,
  individually-addressable resource, **in addition to** persisting the eCR message Bundle
  itself. The system MUST promote **only** the Composition from the eCR message Bundle; it
  MUST NOT re-persist the eCR's other nested clinical resources (which are lower-fidelity
  duplicates) over the authoritative resources already persisted from the collection Bundle.
- **FR-022**: The system MUST persist resources **without wrapping them in a single
  all-or-nothing transaction**. A validation or acceptance failure affecting one resource
  type MUST NOT block, undo, or roll back the persistence of the other resource types; each
  failure MUST be isolated to its own resource(s), surfaced (logged and reflected in exit
  status), while the unaffected resources still persist.
- **FR-023**: The system MUST allow an operator to persist resource types **independently
  across separate runs** — for example, excluding a resource type the server currently
  rejects and persisting it in a later run after the server's validation rules are relaxed.
  Such a per-type re-run MUST be idempotent: it MUST NOT create duplicates of, or roll back,
  resources already persisted by earlier runs. Resource types deliberately excluded from a
  run MUST be reported as **skipped** (distinct from failed).

### Key Entities *(include if data involved)*

- **Input Scenario**: A folder under root `input/` for one reporting case, grouped by
  CMS measure (`poor-diabetic-control`/CMS122, `controllable-bp`/CMS165,
  `depression-screening`/CMS2) and population outcome (Standard vs. Not-In-Population).
  Contains one or more FHIR bundle files. (The parallel structure under `test/input/`
  is development fixtures only.)
- **FHIR Bundle**: The unit read from input — a collection Bundle of clinical resources, a
  MeasureReport, or an eCR message Bundle. Note: a collection Bundle is *unpacked* into its
  contained resources for persistence (FR-020); it is not itself stored as one opaque
  artifact.
- **First-Class Persisted Resource**: An individual resource that lands on the FHIR server
  under its own identity and is independently retrievable/searchable — the contained
  resources of a collection Bundle (FR-020) and the promoted eICR Composition (FR-021).
  This is the unit the downstream analytics consumer can flatten.
- **Promoted eICR Composition**: The Composition extracted from an in-population eCR message
  Bundle and persisted as its own first-class resource (FR-021). Only the Composition is
  promoted; the eICR's other nested clinical copies (lower-fidelity duplicates) are not.
- **Downstream Analytics Consumer**: A state Department of Health analytics team that queries
  the FHIR server with SQL-on-FHIR `ViewDefinition`s to flatten stored resources into tables.
  It can flatten only first-class resources, which is why persistence granularity (FR-020/
  FR-021) is a requirement rather than an implementation detail.
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
- **SC-009**: After a run, the analytics consumer can retrieve any individual contained
  clinical resource (e.g., a specific Patient, Observation, or Condition from a scenario) as
  a standalone resource via a single query — none are reachable only inside an opaque stored
  Bundle.
- **SC-010**: After persisting an in-population scenario, the eICR Composition is retrievable
  as a standalone resource, and the authoritative collection-Bundle clinical resources are
  byte-for-byte unchanged by that promotion (no lower-fidelity overwrite).
- **SC-011**: In a run where the server rejects one resource type, 100% of the accepted
  types are still persisted; only the rejected resources are reported failed; and persisting
  the rejected type in a later run leaves the previously-persisted resource count unchanged
  (no duplicates).

## Assumptions

- **Input/output locations**: Real data lives in the root `input/` directory and real
  output/logs go to root-level destinations (e.g., `output/`, `log/`). The `test/`
  directory (`test/input/`, `test/output/`) is exclusively for development/test
  fixtures. The MVP reads from a directory tree shaped like
  `input/{measure}/{standard,not-in-population}/{scenario}/`. The exact way locations
  are supplied (CLI argument and/or config) is a plan-level detail, since
  `config.example.json` currently carries only server and software-identity fields.
- **Persistence scope (which bundles)**: Per the user's decision, the MVP persists
  **all input content** (collection Bundle, MeasureReport, and eCR message Bundle when
  present) and does not selectively drop any. The **granularity** is now settled (OQ-2
  RESOLVED): a collection Bundle is unpacked into its contained resources, each persisted as
  a first-class resource (FR-020); the eCR message Bundle is persisted whole **and** its
  eICR Composition is promoted to first-class (FR-021). The operator may persist different
  resource types in different runs (FR-023), but the default run persists everything.
- **Downstream analytics consumer (granularity driver)**: The primary consumer of the
  persisted data is a state Department of Health analytics team authoring SQL-on-FHIR
  `ViewDefinition`s over the target server (Aidbox). Because that tooling can flatten only
  first-class resources, persistence granularity (FR-020/FR-021) is treated as a correctness
  requirement, not an implementation detail. (Authoring the ViewDefinitions themselves is out
  of scope for this feature.)
- **No global transaction; isolated, re-runnable per type**: Persistence is **not** wrapped
  in a single all-or-nothing transaction (FR-022). Each resource type persists independently
  so one type's rejection cannot block the others, and a deferred type can be persisted in a
  separate, idempotent later run (FR-023). Known driver: the test MeasureReports currently
  fail the target Aidbox server's validation and may be persisted in a separate run after the
  server's validation rules are relaxed (which may require a server restart).
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
- **Out of scope for MVP**: Generating or transforming eCR content, computing
  MeasureReports, depression-screening (CMS2) fixtures (folders are empty
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
- **OQ-2 — Persistence granularity (whole bundle vs. contained resources)** — **RESOLVED
  (2026-06-11, constitution v1.1.0):** Persist the **individual resources contained in each
  collection Bundle** as first-class resources (FR-020), **not** the opaque Bundle.
  Additionally, promote the eICR **Composition** from in-population eCR message Bundles to a
  first-class resource (FR-021). The driver is the downstream SQL-on-FHIR analytics consumer,
  which can flatten only first-class resources. **This supersedes the earlier MVP draft that
  packed each collection Bundle into a single atomic `transaction` Bundle** — that approach
  is replaced by independent, per-resource persistence with no global transaction (FR-022),
  so a rejected resource type cannot roll back the others.

> Note: OQ-1 and OQ-2 were settled in `/speckit-plan` (data-inspection spike + constitution
> v1.1.0). See `research.md` D1 (identity), D2/D2b (granularity + Composition promotion), and
> D10 (independent per-type persistence). No open questions remain blocking implementation.

## Dependencies

- A reachable target FHIR R4 server with OAuth2 client-credentials authentication.
- The canonical input fixtures under `test/input/` (and the input-shape definitions in
  `docs/CDS_TestData_DocumentationFor05252026zip.pdf`).
- The project constitution (`.specify/memory/constitution.md`, **v1.1.0**), whose principles
  (zero-dependency runtime, profile conformance, defensive processing, config-over-
  code, secret protection, clear output, **Principle V independent persistence /
  no global transaction, and Principle VI analytics-ready persistence granularity**)
  constrain this feature.
- The downstream **SQL-on-FHIR analytics workflow** (state DoH `ViewDefinition`s over the
  target Aidbox server), whose requirement that resources be first-class drives FR-020/FR-021.
