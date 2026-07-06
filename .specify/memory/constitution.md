<!--
SYNC IMPACT REPORT
==================
Version change: 1.2.0 → 1.3.0 (latest)
Rationale (1.3.0, MINOR): Adds one new principle (VIII. Input Pre-Processing for Aidbox
Storability). Storing the resources in the target Aidbox server is now an explicit project
goal, so the project MUST pre-process/remediate input resources enough to be *stored*
(a validation surface distinct from the HL7 conformance gate). No existing principle is
removed or redefined — the new principle is deliberately SUBORDINATE to Principle V
(never fabricate clinical values; never silently drop clinical content; log every
accommodation) and to the HL7 validator gate (remediation MUST NOT regress conformance),
so this is MINOR, not MAJOR.

Added principles:
  - VIII. Input Pre-Processing for Aidbox Storability — the project MUST make input
    resources storable in the target Aidbox server, treating Aidbox ingestion as a second
    validation surface separate from the HL7 conformance gate. Non-mutating levers are
    preferred (the per-request `aidbox-validation-skip: reference` header for Cause 1;
    box-side terminology config for Cause 3) before any content transform. Content
    transforms (e.g., for the `mrp-2` base-invariant violation, Cause 2) are permitted
    ONLY when they neither fabricate clinical values nor silently drop clinical content
    (Principle V); where the only "fix" would be fabrication, the resource type MUST be
    isolated/deferred (Principle V independent persistence), never fabricated. Every
    remediation MUST be documented in known-validation-issues.md and logged at runtime,
    MUST NOT edit the immutable test/input fixtures (Principle III), and MUST NOT introduce
    new HL7-validator errors against the committed baseline.

Modified sections:
  - Top summary blockquote — records that the processor also pre-processes input resources
    so they are storable in the target Aidbox server, not only validated and persisted.

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (Constitution Check is a generic gate;
    verified no hard-coded principle references)
  - .specify/templates/spec-template.md  ✅ aligned (no principle-specific content)
  - .specify/templates/tasks-template.md ✅ aligned (no principle-specific content)
  - .specify/templates/checklist-template.md ✅ aligned

Downstream artifacts requiring follow-up (NOT auto-edited by this command):
  - known-validation-issues.md ⚠ PENDING — the "Aidbox ingestion-time validation" section
    currently frames Causes 1–3 as reference-only and says the mrp-2 data fix is "out of
    scope per the gate philosophy." Under Principle VIII, storability remediation is now IN
    scope: for each Cause, record the chosen lever/transform (or, if only fabrication would
    fix it, the decision to isolate/defer that type). The architectural note recommending
    BOX_FHIR_SCHEMA_VALIDATION=false must be reconciled with VIII (that flag is a DO-NOT-USE
    engine selector; storability must come from per-request levers + non-fabricating
    transforms, not from disabling the schema engine).
  - A new feature spec (e.g., specs/00X-aidbox-preprocessing/) ⚠ PENDING — the pre-processing
    pipeline is a distinct feature; run /speckit-specify then /speckit-plan. The spec must
    decide, per Cause, exactly which transform is applied and prove it neither fabricates nor
    drops clinical content (e.g., whether removing a population-only, value-and-component-less
    stratifier is "malformed structure" vs. clinical content).
  - README.md ⚠ PENDING — the "Independent per-type runs" / deferred-MeasureReport notes now
    describe a pre-Principle-VIII stance; update once the pre-processing pipeline lands.

Deferred TODOs:
  - TODO(MRP2_REMEDIATION): the mrp-2 stratifier violation (Cause 2) has no config/header
    lever; the exact non-fabricating transform (or the decision to isolate/defer
    MeasureReports) is to be settled in the pre-processing feature spec, not the constitution.

----- Prior amendment (1.1.1 → 1.2.0, MINOR) -----
Rationale (1.2.0, MINOR): Adds one new principle (VII) and materially expands the rationale
of Principle VI to reflect a new project responsibility: this project now AUTHORS the
SQL-on-FHIR ViewDefinitions and a publish/materialize script (previously the constitution
framed the downstream DoH team as the sole author). No principle was removed or
fundamentally redefined, so this is MINOR, not MAJOR.

Added principles:
  - VII. Analytics View Definitions and Materialization — for each resource type the
    analytics team needs, the project MUST provide an Aidbox SQL-on-FHIR-compliant
    ViewDefinition resource plus a script that PUTs it to the server and invokes
    $materialize. Scope is incremental and demand-driven: Patient is the first and
    currently only required ViewDefinition; other resource types are added only when the
    analytics team specifies the columns they want. The script obeys Principle I
    (stdlib-only), the Deployment & Security section (base URL/creds from config), and
    Principle V (idempotent, re-runnable, per-type failure isolation).

Modified principles:
  - VI. Analytics-Ready Persistence Granularity — rationale expanded so it records that
    this project authors and materializes the ViewDefinitions on the analytics team's
    behalf (cross-links Principle VII). No rule changed.

Modified sections:
  - Top summary blockquote — adds that the processor also publishes SQL-on-FHIR
    ViewDefinitions that flatten the persisted resources for downstream analytics.

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (Constitution Check is a generic gate;
    no hard-coded principle references)
  - .specify/templates/spec-template.md  ✅ aligned
  - .specify/templates/tasks-template.md ✅ aligned
  - .specify/templates/checklist-template.md ✅ aligned

Downstream artifacts requiring follow-up (NOT auto-edited by this command):
  - A new feature spec (e.g., specs/002-viewdefinition-materialize/) ⚠ PENDING — the
    ViewDefinition + $materialize work is a distinct feature; run /speckit-specify then
    /speckit-plan to scope it (start with Patient).
  - README.md ⚠ PENDING — "What it does" should mention the project now authors and
    materializes SQL-on-FHIR ViewDefinitions (Patient first), not only that persisted
    resources are queryable by the downstream team.

Deferred TODOs:
  - TODO(VIEWDEF_RESOURCE_TYPES): only Patient is specified so far; the set of other
    resource-type ViewDefinitions awaits the analytics team's column requirements.

----- Prior amendment (1.1.0 → 1.1.1, PATCH) -----
Clarifying note only — Principle II now records that the APHL chronic-ds IG
(cqf.aphl.chronic-ds#0.0.002) is an unpublished draft not resolvable from packages.fhir.org
and is intentionally excluded from the validator -ig set (its Measure canonicals resolve to
warnings, not errors). No principle added, removed, or redefined; intent unchanged.
Authoritative rationale lives in known-validation-issues.md.

----- Prior amendment (1.0.0 → 1.1.0) -----
Rationale: MINOR amendment. Adds one new principle and materially expands one
existing principle to accommodate a downstream SQL-on-FHIR analytics workflow that
requires contained resources to be stored as independent, first-class resources and
each resource type to be persistable independently (no all-encompassing transaction).
No principle was removed or fundamentally redefined, so this is MINOR, not MAJOR.

Modified principles:
  - V. Data Integrity and Defensive Processing — materially expanded: added the
    "Independent persistence (no global transaction)" rule so a validation/acceptance
    failure in one resource type (e.g., server-rejected MeasureReports) does not block
    or roll back the others, and persistence is idempotently re-runnable per type.

Added principles:
  - VI. Analytics-Ready Persistence Granularity — contained resources of collection
    Bundles, and the eICR Composition within in-population eCR document Bundles, MUST
    be persisted as independent, first-class, individually-addressable resources so a
    downstream SQL-on-FHIR consumer (Aidbox ViewDefinitions) can flatten them. Promotion
    must not overwrite higher-fidelity copies.

Added sections: none beyond Principle VI.
Removed sections: none.

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (Constitution Check gate is
    constitution-agnostic; no hard-coded principle references)
  - .specify/templates/spec-template.md  ✅ aligned (no principle-specific content)
  - .specify/templates/tasks-template.md ✅ aligned (no principle-specific content)
  - .specify/templates/checklist-template.md ✅ aligned

Downstream artifacts requiring follow-up (NOT auto-edited by this command):
  - specs/001-mvp-fhir-processor/plan.md ⚠ PENDING — Summary + Constitution Check still
    describe collection→single-transaction persistence. Under amended V + new VI, replace
    the atomic-transaction model with per-resource-type independent persistence (batch/
    individual PUTs, runnable per type), and add Composition promotion. Re-run /speckit-plan.
  - specs/001-mvp-fhir-processor/spec.md ⚠ PENDING — confirm FR-020/021/022 + OQ-2/OQ-3
    reflect independent first-class persistence and per-type failure isolation.
  - README.md ⚠ PENDING — "What it does" (transaction Bundle per collection) describes the
    current code; update when the implementation moves to per-type independent persistence.

Deferred TODOs:
  - TODO(ECR_IG_VERSION): pin the exact hl7.fhir.us.ecr package version once the
    target deployment confirms it; the test fixtures carry unversioned us/ecr
    canonicals. Same for hl7.fhir.us.core and hl7.fhir.us.davinci-deqm.
    The APHL chronic-ds Measure canonicals ARE pinned in the fixtures (|0.0.002).
-->

# eCR FHIR Processor Constitution

> Principles governing the development, testing, and maintenance of a Python
> utility that consumes FHIR R4 electronic Case Reporting (eCR) resources for
> chronic-disease quality measures, validates them against both the HL7 FHIR
> Reference Validator (CLI) and a target FHIR server, pre-processes them so they
> are storable in the target Aidbox server, persists them to that FHIR server,
> and publishes SQL-on-FHIR ViewDefinitions that flatten the persisted resources
> for downstream analytics.

## Core Principles

### I. Zero-Dependency Runtime

The processor MUST run on the Python 3 standard library only. No third-party
packages may be added as runtime dependencies.

**Rules:**

- All runtime functionality uses only Python 3 built-in modules (`json`, `uuid`,
  `urllib`, `datetime`, `logging`, `argparse`, `os`, `sys`, etc.).
- Dev/test dependencies (linters, validators, test frameworks) are permitted but
  MUST NOT be required to run the processor itself.
- If a capability cannot be achieved with the stdlib, prefer a simpler design over
  adding a dependency.

### II. FHIR Profile Conformance

Every FHIR resource the processor reads, transforms, or submits MUST conform to
the appropriate Implementation Guide (IG) profiles and pass the HL7 FHIR Reference
Validator with zero errors before it is persisted to a FHIR server.

**Rationale:** The output is consumed by state and federal public-health FHIR
servers that enforce profile validation. A non-conformant Bundle is a rejected
submission. Profile conformance is a correctness requirement, not a nice-to-have.

The processor MUST track which version of each IG it targets and accommodate
version changes without ad-hoc code edits.

**Target Implementation Guides** (crosswalked from `meta.profile` declarations in
`test/input/` and `docs/CDS_TestData_DocumentationFor05252026zip.pdf`):

- **US Electronic Case Reporting (eCR) FHIR IG** — `hl7.fhir.us.ecr` — the primary
  content and packaging IG. Profiles exercised by the fixtures include
  `eicr-document-bundle`, `eicr-measurereport-bundle`, `eicr-composition`,
  `eicr-encounter`, `eicr-observation`, `eicr-procedure`, `us-ph-patient`,
  `us-ph-condition`, `us-ph-location`, and `us-ph-organization`.
- **US Core** — `hl7.fhir.us.core` — `us-core-race`, `us-core-ethnicity`,
  `us-core-practitioner`, `us-core-vital-signs`.
- **Da Vinci DEQM** — `hl7.fhir.us.davinci-deqm` — `extension-criteriaReference`
  on MeasureReport populations; MeasureReport conformance.
- **APHL Chronic Disease Surveillance IG** — `fhir.org/guides/cqf/aphl/chronic-ds`
  — the `Measure` canonicals referenced by MeasureReports, pinned in the fixtures
  at version `0.0.002` (e.g.
  `…/Measure/DiabetesHemoglobinA1cHbA1cPoorControl9FHIR|0.0.002`,
  `…/Measure/ControllingHighBloodPressureFHIR|0.0.002`).
  **Note (validator set):** `cqf.aphl.chronic-ds#0.0.002` is an unpublished draft available
  only as a `build.fhir.org` CI tarball — it is **not** resolvable from `packages.fhir.org`,
  and the test-data supplier does not validate against it. It is therefore **intentionally
  excluded** from the validator `-ig` set; the fixtures' `…|0.0.002` Measure canonicals
  resolve to **warnings, not errors** without it (acceptable per this principle). See
  `known-validation-issues.md` → "Pinned IG set" for the authoritative rationale.

**Rules:**

- All internal references use `urn:uuid:` or absolute server URLs consistent with
  the source eCR Bundle; the processor MUST NOT silently rewrite reference styles
  in a way that breaks resolution.
- Period/instant timestamps MUST include timezone offsets (e.g., `+00:00`).
- Warnings from the HL7 validator are acceptable; errors are not.
- When a referenced IG publishes a new version, validate against the latest and
  update profile/Measure canonical URLs accordingly.
- **IG Version Tracking:** The code MUST declare which versions of the IGs it was
  built to conform to. This declaration MUST be maintained as named constants or
  configuration values (not buried in comments) so it is programmatically
  accessible.
- **IG Versions in Output:** Resources the processor emits SHOULD carry the target
  IG versions in profile/Measure canonical URLs where the IG specifies versioned
  canonicals (the APHL chronic-ds Measure canonicals are versioned; eCR/US Core
  profile canonicals in the fixtures are unversioned).
- **Accommodating IG Changes:** Updating a target version MUST be a deliberate,
  reviewable change (constant/config update + validation pass), not an automatic
  or silent upgrade.

### III. Dual-Gate Validation Testing

The primary test strategy is **end-to-end conformance testing**: run the processor
against the canonical input fixtures in `test/input/` and validate the resources it
processes/emits through two independent gates — (1) the HL7 FHIR Reference
Validator (`validator_cli.jar`), and (2) the target FHIR server's own validation
(transaction acceptance and/or `$validate`).

**Rationale:** For a data-handling tool targeting a formal specification, the most
valuable test is "does this conform and will the destination server accept it?" The
HL7 Reference Validator is the authoritative arbiter of FHIR conformance; the FHIR
server is the authoritative arbiter of whether a submission is actually accepted.
Unit tests on internal functions are secondary to these. Because the IGs evolve,
tests MUST record which IG versions they validated against so results are
reproducible and regressions from version changes are detectable.

**Rules:**

- The `test/input/` directory holds the canonical fixtures; these are regression
  inputs and MUST NOT be edited to make a failing test pass.
- Every supported input shape (see Principle IV) MUST have at least one canonical
  fixture exercised by CI's validation pipeline. Adding a new measure or input
  shape without a corresponding fixture is incomplete work.
- CI MUST validate every processed/emitted Bundle with the HL7 FHIR Validator.
  Zero project-introduced errors = pass.
- Developers SHOULD run FHIR validation locally during development, not only in CI.
  LLM agents MUST do so (see LLM Development Validation below).
- Supplement conformance tests with targeted unit tests for any computation or
  transformation logic where correctness is not fully captured by profile
  validation alone (e.g., reference rewriting, identifier handling,
  output-path derivation).
- **IG Version in Validation:** The HL7 FHIR Validator MUST be invoked with IG
  packages versioned (e.g., `-ig hl7.fhir.us.ecr#<ECR_IG_VERSION>`) rather than
  unversioned references, so validation results are reproducible.
- **Recording the IG Version:** CI output and test artifacts MUST record which IG
  versions were used for validation (e.g., by logging the `-ig` arguments or
  storing them in CI configuration variables).
- **Version Change as a Test Event:** When a target IG version is updated, a full
  validation pass against the new version MUST be performed and reviewed before the
  change is merged.
- **LLM Development Validation:** When an LLM agent (Claude Code, Copilot, etc.)
  performs development work that could affect FHIR handling or output, it MUST run
  the same validation pipeline as GitHub CI before considering the work complete.
  Specifically:
  1. Run the processor against all fixtures in `test/input/`.
  2. Run the HL7 FHIR Validator against every processed/emitted Bundle, e.g.:
     `java -jar validator_cli.jar output/**/*.json -version 4.0.1 -ig hl7.fhir.us.ecr#$ECR_IG_VERSION -ig hl7.fhir.us.core#$US_CORE_VERSION -ig hl7.fhir.us.davinci-deqm#$DEQM_VERSION -ig <aphl-chronic-ds-package>`
  3. Zero errors required; warnings are acceptable.
  The LLM MUST NOT skip validation to save time or defer it to CI. If
  `validator_cli.jar` or Java is not available locally, the LLM MUST inform the
  user and request that the environment be set up before proceeding, rather than
  silently skipping validation.
- **Known Upstream Validation Issues:** Some validation errors originate in upstream
  IG dependencies (e.g., DEQM cross-version extension resolution failures, eCR
  package dependency gaps) rather than in this project's handling. These MUST be
  documented in `known-validation-issues.md` at the repository root and filtered in
  CI so the build stays green while they remain unresolved upstream.
  - Each entry MUST include: the exact validator error message, the affected
    resource type, root-cause analysis, the responsible upstream package and HL7
    working group, reproduction steps proving the error exists in the IG's own
    published examples, and the environment tested.
  - Known issues MUST NOT be silently ignored — they are tracked so the project can
    report them to the responsible HL7 working groups (e.g., Da Vinci CQI for DEQM,
    the eCR/CSTE/CDC stewards for us/ecr) and advocate for upstream fixes.
  - When an upstream fix ships (new IG version, validator update), the entry MUST be
    retested and removed if resolved.
  - CI filtering logic MUST match only the specific documented error patterns —
    never broad wildcards that could mask new, legitimate errors.
  - LLM agents performing local validation SHOULD apply the same known-issue
    filtering as CI. Errors matching documented known issues SHOULD be noted but are
    not blockers; errors not matching a documented known issue remain blockers.

### IV. Multi-Measure / Multi-Population Input Coverage

The processor handles chronic-disease eCR test data organized by CMS quality
measure and by population outcome, as described in
`docs/CDS_TestData_DocumentationFor05252026zip.pdf`.

**Input shape (per the test-data documentation):**

- Input is a FHIR R4 `Bundle` (type `collection`) of 3–7 resources: always
  `Patient`, `Encounter`, `Condition`; usually `Observation`; sometimes
  `MedicationRequest`, `ServiceRequest`, `Procedure`. Each scenario also ships a
  `MeasureReport` (expected evaluation result) and, for in-population scenarios, an
  eCR reporting `Bundle` (type `message`): a `MessageHeader` referencing a nested
  content Bundle that combines the input resources with the MeasureReport.
- Scenarios are grouped per measure into a **Standard** folder (patient in the
  Initial Population — input Bundle + MeasureReport + eCR message Bundle) and a
  **Not-In-Population** folder (patient outside IP — input Bundle + MeasureReport
  only, all population counts zero, no eCR generated).

**Supported scope:**

- Target CMS measures: **CMS122** (Diabetes HbA1c Poor Control ≥9% —
  `poor-diabetic-control`), **CMS165** (Controlling High Blood Pressure —
  `controllable-bp`), and **CMS2** (Depression screening — `depression-screening`).
- Currently only **2 of 3** measures have sample data and are exercised by tests
  (`poor-diabetic-control` and `controllable-bp`). `depression-screening` (CMS2) is
  in scope but has **no fixtures yet**; its `test/input/depression-screening/`
  folders are empty placeholders.
- Per the documentation, the represented fixtures cover 3 JSON resources per
  Standard scenario and 2 per Not-In-Population scenario.

**Rules:**

- When sample data for a new measure (e.g., CMS2 depression screening) or a new
  resource type arrives, add corresponding fixtures under `test/input/<measure>/`
  that exercise it, and wire them into the validation pipeline (Principle III).
- Adding support for a measure or input shape without a corresponding fixture is
  incomplete work.

### V. Data Integrity and Defensive Processing

The processor MUST handle real-world data-quality issues gracefully, never
producing silently incorrect output and never silently dropping clinical content.

**Rationale:** Hospital-reported source data are messy — fields can be empty or
malformed. The processor must be robust to these realities, because a subtle data
error in a public-health report is worse than a loud failure.

**Rules:**

- Every data-quality accommodation MUST be logged at WARNING level or above.
- The processor MUST NOT fabricate clinical values to satisfy a profile; if input
  is missing required data, it fails loudly rather than inventing content.
- A resource that fails validation MUST NOT be persisted to the FHIR server; the
  failure MUST be surfaced (logged and reflected in exit status), not swallowed.
- **Independent persistence (no global transaction):** Persistence MUST NOT be wrapped
  in a single atomic transaction spanning all resource types. Each resource type MUST be
  persistable independently, so that a validation or server-acceptance failure in one
  type (e.g., MeasureReports the target server currently rejects) does not block, undo,
  or roll back the persistence of the others.

  **Rationale:** Resource types reach the server with different conformance maturity.
  Forcing them through one all-or-nothing transaction means one rejected type defeats the
  whole submission. Isolating persistence by type keeps the conformant majority landed
  while a problem type is worked separately.

  - Failures MUST be isolated and surfaced per resource type (logged + reflected in exit
    status), never silently swallowed (consistent with the rule above).
  - Persistence MUST be idempotently re-runnable per resource type — including a later,
    separate run (e.g., after the target server's validation rules are relaxed for a type)
    — without re-persisting, duplicating, or rolling back resources that already succeeded.
    Retained-id PUT semantics (update-in-place) make this safe.

### VI. Analytics-Ready Persistence Granularity

The processor MUST persist clinical and reporting content at a granularity that makes it
directly queryable by the downstream SQL-on-FHIR analytics workflow. That workflow can
flatten only **first-class, individually-addressable** resources at `[base]/Type/<id>` —
it cannot reach into a resource stored opaquely inside a Bundle.

**Rationale:** The primary downstream consumer is a state Department of Health analytics
team that runs SQL-on-FHIR `ViewDefinition`s against the target FHIR server (Aidbox); this
project authors and materializes those `ViewDefinition`s on the team's behalf (Principle
VII). A `ViewDefinition` cannot select fields out of a whole-stored Bundle; only resources that
exist independently on the server are analyzable. Persistence granularity therefore decides
**what is analyzable downstream**, not merely how a submission is packaged — making it a
correctness requirement for this project's purpose, not an implementation detail.

**Rules:**

- The resources contained in each `collection` input Bundle (`<scenario_id>.json`) MUST be
  persisted as independent, first-class resources (`PUT [base]/Type/<retained-id>`) so each
  is individually addressable, in addition to whatever Bundle-level persistence the project
  retains for provenance.
- For in-population scenarios that carry an eCR reporting Bundle (`Bundle_<uuid>.json`), the
  eICR **`Composition`** MUST be extracted from the nested document Bundle and persisted as a
  first-class resource (`PUT [base]/Composition/<id>`), in addition to persisting the eCR
  Bundle itself. The Composition is the artifact the downstream team cares about most.
- **No fidelity regression on promotion:** Promoting a nested resource to first-class MUST
  NOT overwrite a higher-fidelity copy already persisted. Only the eICR `Composition` is
  promoted from the message Bundle; the eICR's lower-fidelity duplicate clinical resources
  MUST NOT be re-persisted over the authoritative `collection`-Bundle resources (see
  Principle V — never produce silently incorrect output).
- First-class persistence relies on retained resource ids (GUIDs) for idempotent
  update-in-place, so re-runs neither duplicate nor diverge (see Principle V — independent,
  re-runnable persistence).
- This granularity requirement composes with Principle V's independent-persistence rule:
  the contained resources, the eCR Bundle, the promoted Composition, and standalone
  MeasureReports are each persistable as their own unit of work.

### VII. Analytics View Definitions and Materialization

For each resource type the downstream analytics team needs, the project MUST provide an
Aidbox SQL-on-FHIR–compliant `ViewDefinition` resource, plus a script that publishes those
ViewDefinitions to the target FHIR server and materializes them.

**Rationale:** Principle VI guarantees the underlying resources are first-class and
flattenable; the actual analytics deliverable is the flattened view itself. The DoH
analytics team specifies *which* columns and resource types it needs; this project owns
authoring conformant ViewDefinitions and driving their materialization so the views exist
and stay current on the server. ViewDefinition authoring is therefore a project
responsibility, not a downstream-only concern.

**Rules:**

- Each `ViewDefinition` MUST conform to the SQL-on-FHIR `ViewDefinition` specification as
  implemented by Aidbox, and MUST be a checked-in, version-controlled resource file — not
  generated ad hoc at runtime.
- **Incremental, demand-driven scope:** `Patient` is the first and currently the only
  required ViewDefinition. Additional resource-type ViewDefinitions MUST NOT be added
  speculatively; add one only once the analytics team specifies the fields/columns it wants
  from that resource type. Until then, the absence of other ViewDefinitions is intentional,
  not incomplete work.
- The publish/materialize script MUST (a) `PUT` each ViewDefinition to
  `[base]/ViewDefinition/<id>` and (b) invoke `[base]/ViewDefinition/<id>/$materialize`. It
  MUST be idempotently re-runnable (retained ids, update-in-place) so re-runs neither
  duplicate nor diverge views (consistent with Principle V).
- The script MUST obey Principle I (Python stdlib only; reuse the existing FHIR
  client/auth) and the Deployment & Security section (server base URL and credentials come
  from configuration, never hardcoded).
- A ViewDefinition the server rejects — on publish or on `$materialize` — MUST surface the
  failure (logged and reflected in exit status), never swallowed (Principle V).
  Per-resource-type isolation applies: one view's failure MUST NOT block publishing or
  materializing the others.
- ViewDefinitions MUST select only from first-class, individually-addressable resources
  (Principle VI); a view MUST NOT depend on content that exists only inside an un-promoted
  Bundle.

### VIII. Input Pre-Processing for Aidbox Storability

Storing the processed resources in the target Aidbox server is an explicit project goal.
The processor MUST pre-process input resources enough that the target Aidbox server will
**store** them, treating Aidbox ingestion-time validation as a **second, distinct
validation surface** from the HL7 FHIR Reference Validator gate. Storability remediation
targets that Aidbox surface; it MUST NOT be conflated with, or allowed to regress, HL7
conformance (Principles II–III).

**Rationale:** Aidbox enforces as hard HTTP 422s several things the HL7 validator gate only
warns about or that the committed baseline already tolerates (see
`known-validation-issues.md` → "Aidbox ingestion-time validation"). A resource that the HL7
gate accepts but Aidbox rejects is unstored — and an unstored resource is invisible to the
SQL-on-FHIR analytics workflow this project exists to feed (Principles VI–VII). Making the
resources storable is therefore a correctness requirement for the project's purpose, not an
optional convenience. This principle is deliberately **subordinate to Principle V**: the goal
is storability, never storability bought with fabricated or dropped clinical content.

**Rules:**

- **Prefer non-mutating levers over content transforms.** Where the target server exposes a
  per-request or box-side lever that makes a resource storable without altering its content,
  that lever MUST be used before any content transform. Specifically: the per-request
  `aidbox-validation-skip` header (driven by `config.server.validation_skip`) for
  target-profile reference-conformance rejections (Cause 1), and box-side terminology
  configuration for terminology-binding rejections (Cause 3). Content is transformed only
  when no non-mutating lever exists (e.g., the base-FHIR `mrp-2` invariant, Cause 2).
- **Content transforms are bounded by Principle V.** A pre-processing transform MUST NOT
  fabricate clinical values to satisfy a constraint, and MUST NOT silently drop clinical
  content. Removing a structurally malformed element that carries **no** clinical meaning
  (e.g., a stratifier stratum with a `population` only and neither `value` nor `component`)
  is permitted only when it is demonstrably empty of clinical content; the determination and
  its justification belong in the feature spec, not in ad-hoc code.
- **No fabrication as an escape hatch.** Where the only way to make a resource storable would
  be to fabricate clinical data or drop clinical content, the processor MUST NOT do so.
  Instead it MUST isolate/defer that resource type (Principle V — independent persistence,
  per-type failure isolation) so the storable majority still lands, and surface the deferral
  (logged + reflected in exit status).
- **Every remediation is documented and logged.** Each pre-processing transform or lever MUST
  be recorded in `known-validation-issues.md` (the exact Aidbox message it addresses, root
  cause, and the transform/lever applied) and logged at WARNING level or above at runtime
  (Principle V). Silent remediation is prohibited.
- **Fixtures stay immutable.** Pre-processing transforms the in-memory / emitted resources on
  the path to the server; it MUST NOT edit the canonical `test/input/` fixtures (Principle
  III). The fixtures remain the pre-transform regression inputs and the conformance baseline.
- **No conformance regression.** A storability remediation MUST NOT introduce any new
  HL7-validator error against the committed baseline (`test/conformance-baseline.sigs`). If a
  transform needed for Aidbox would break HL7 conformance, the conflict MUST be surfaced and
  resolved in review, not silently accepted.
- **`BOX_FHIR_SCHEMA_VALIDATION=false` is not a storability lever.** Disabling the Aidbox FHIR
  Schema engine is a DO-NOT-USE engine selector that breaks the FHIR REST API (every PUT
  404s); storability MUST come from per-request levers plus non-fabricating transforms, never
  from turning the schema engine off (see `known-validation-issues.md`).

## Deployment & Security

### Configuration over Code Changes

Server- and deployment-specific data MUST live in configuration files, never
hardcoded.

**Rationale:** A single script with per-deploy config files is the deployment
model. IT staff edit config; they do not edit Python.

**Rules:**

- `config.example.json` is the canonical template. It MUST stay current with all
  supported configuration fields (FHIR server base URL, OAuth2 endpoints, IG
  versions, etc.).
- `config.json` (the real config with secrets) MUST be `.gitignore`'d. A
  `.gitignore` file MUST exist in the repo and MUST include `config.json`.
- A pre-commit hook or CI check SHOULD reject commits that include `config.json` or
  files matching `*.secret*`.
- Required config sections are validated at startup with clear error messages.

### Secret Protection

OAuth credentials and other secrets MUST NOT enter version control.

**Rationale:** `config.json` contains `client_id` and `client_secret` for FHIR
server OAuth2 authentication. Leaking these credentials could grant unauthorized
access to state health-data systems.

**Rules:**

- `.gitignore` MUST include: `config.json`, `*.secret*`, `.env`.
- CI SHOULD include a secret-scanning step (e.g., `git-secrets`, `trufflehog`, or
  GitHub's built-in secret scanning).
- `config.example.json` MUST use obvious placeholder values (e.g., `YOUR_CLIENT_ID`)
  that would fail authentication if accidentally used.
- Documentation MUST warn users not to commit real configs.

### Clear, Predictable Output

Output files MUST be deterministic, well-named, and organized for human inspection.

**Rationale:** Hospital data managers and state health officials need to find,
review, and troubleshoot submissions. Output structure is part of the user
experience.

**Rules:**

- Output is organized first by CMS measure, then by reporting date:
  `output/{measure name}/{YYYY-MM-DD}/` holds the file(s) for that date — mirroring
  the `test/output/{measure}/{standard,not-in-population}` layout.
- JSON MUST be pretty-printed (indented) for human readability.
- Logging goes to both console (immediate feedback) and a timestamped file (audit
  trail) under `log/`.

## Development Workflow

### CI Pipeline

All pull requests MUST pass automated checks before merge.

**Rationale:** With AI-assisted development and a small team, CI is the safety net
that catches regressions before they reach hospital workstations.

**Required checks:**

- **Lint:** Python linter (e.g., `ruff` or `flake8`) with consistent style rules.
- **FHIR Validation:** Run the processor against the test inputs, then validate the
  processed/emitted output with `validator_cli.jar` against the IGs named in
  Principle II. Zero project-introduced errors required. Known upstream errors
  documented in `known-validation-issues.md` MUST be filtered by matching their
  specific patterns so the build passes while they remain unresolved upstream. Any
  error not matching a documented known issue MUST fail the build.
- **Secret scanning:** Reject commits containing likely credentials.
- Checks run via GitHub Actions.
- The CI pipeline itself is subject to this constitution — changes to CI config
  require the same review as code changes.

### README as Living Documentation

Any change that affects user-facing behavior, project architecture, IG conformance,
or developer workflow MUST be evaluated for a corresponding `README.md` update.

**Rationale:** The README is the first document new contributors, hospital IT staff,
and LLM agents encounter. If it falls out of sync with the code, users make
incorrect assumptions — wrong IG versions, missing configuration steps, or outdated
profile references. Keeping the README current is cheaper than debugging the
confusion it causes.

**Rules:**

- When a feature adds or changes IG references, profile/Measure URLs, CLI flags,
  configuration fields, output structure, supported measures/input shapes, or
  version-tracking constants, the implementer MUST check whether `README.md` needs a
  corresponding update.
- README updates SHOULD be included in the same PR as the code change, not deferred
  to a follow-up.
- LLM agents performing development work SHOULD flag README staleness if they notice
  the code has diverged from what the README describes.

### Single-File Simplicity (Until It Hurts)

Prefer fewer, well-organized files over premature modularization.

**Rules:**

- A single entry-point script (e.g., `process.py`) remains the entry point for the
  processor.
- Extract modules only when a clear boundary emerges (e.g., FHIR client logic,
  validation orchestration, input parsers) AND the single file exceeds ~1000 lines.
- Test files, CI config, and dev tooling live in their own directories and do not
  count toward the single-file threshold.
- Any split MUST preserve the zero-dependency runtime constraint.

## Governance

This constitution supersedes other development practices for this repository. When a
principle conflicts with a practical constraint, document the exception and the
reasoning in the relevant spec or PR — do not silently deviate.

### Amendment Process

1. Propose the change as a pull request modifying this file.
2. The PR description MUST explain why the change is needed and what impact it has on
   existing specs and implementations.
3. At least one team member must approve.
4. Update the version and the Last Amended date in the same PR.

### Versioning

- **MAJOR:** Removing or fundamentally redefining an existing principle.
- **MINOR:** Adding a new principle or materially expanding the scope of an existing
  one.
- **PATCH:** Clarifying language without changing intent.

### Compliance

- All specs and implementation plans MUST reference this constitution.
- AI agents (Claude Code, Copilot, etc.) operating on this repo SHOULD be given this
  constitution as context.
- When a principle conflicts with a practical constraint, document the exception and
  the reasoning in the relevant spec or PR.

**Version**: 1.3.0 | **Ratified**: 2026-06-09 | **Last Amended**: 2026-07-01
