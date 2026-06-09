<!--
SYNC IMPACT REPORT
==================
Version change: (template / unversioned) → 1.0.0
Rationale: Initial ratification of a concrete project constitution, replacing the
unfilled template placeholders. MAJOR baseline (1.0.0).

Modified principles (renamed/reframed from the borrowed draft in
constitution.content.tmp.md to fit an eCR *processor* that consumes → validates →
persists, rather than a converter that generates):
  - [PRINCIPLE_1] → I. Zero-Dependency Runtime
  - [PRINCIPLE_2] → II. FHIR Profile Conformance (specific IGs injected)
  - [PRINCIPLE_3] → III. Dual-Gate Validation Testing (Reference Validator + FHIR server)
  - [PRINCIPLE_4] → IV. Multi-Measure / Multi-Population Input Coverage
  - [PRINCIPLE_5] → V. Data Integrity and Defensive Processing

Added sections:
  - "Target Implementation Guides" subsection (concrete IG package list, crosswalked
    from test/input meta.profile values and docs/CDS_TestData_DocumentationFor05252026zip.pdf)
  - Deployment & Security (Configuration over Code, Secret Protection, Clear Output)
  - Development Workflow (CI Pipeline, README as Living Documentation, Single-File Simplicity)
  - Governance (Amendment Process, Versioning, Compliance)

Removed sections: none (template placeholders fully replaced).

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (Constitution Check gate is
    constitution-agnostic; no hard-coded principle references to update)
  - .specify/templates/spec-template.md  ✅ aligned (no principle-specific content)
  - .specify/templates/tasks-template.md ✅ aligned (no principle-specific content)
  - .specify/templates/checklist-template.md ✅ aligned

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
> Reference Validator (CLI) and a target FHIR server, and persists them to that
> FHIR server.

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

**Version**: 1.0.0 | **Ratified**: 2026-06-09 | **Last Amended**: 2026-06-09
