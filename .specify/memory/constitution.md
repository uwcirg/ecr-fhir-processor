<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 2.0.0
Rationale: Major change of course. The primary purpose shifts from "consume input
Bundles, validate, and emit/persist eCR message Bundles" to "decompose the eCR
Bundle (Bundle_<uuid>.json) into its contained resources and persist each as an
independent, individually-addressable FHIR resource." This redefines two
non-negotiable rules from v1.0.0 (conformance was an absolute pre-persistence gate;
failed-validation resources MUST NOT be persisted) and adds a new primary principle,
so the bump is MAJOR.

Modified principles:
  - II. FHIR Profile Conformance → III. FHIR Conformance — Target, Not Hard Gate
        (conformance/IG tracking retained, but lower-fidelity eCR data is tolerated
         and persistence is no longer hard-gated on the Reference Validator; the
         Reference-Validator gate remains MANDATORY only for the alternative emit mode)
  - III. Dual-Gate Validation Testing → IV. Dual-Gate Validation Testing
        (server acceptance is the authoritative gate for the persistence mode; the
         Reference Validator is authoritative for the alternative emit mode)
  - IV. Multi-Measure / Multi-Population Input Coverage → V. (same name)
        (primary input is now the eCR message Bundle; the collection Bundle and the
         standalone MeasureReport_<uuid>.json are ignored by the primary mode)
  - V. Data Integrity and Defensive Processing → VI. (same name)
        ("a resource that fails validation MUST NOT be persisted" replaced with
         per-resource failure isolation: server-rejected resources are logged and
         surfaced but do not block or roll back sibling resources)

Added sections:
  - "Operating Modes" (defines Mode A — eCR Decomposition & Persistence, primary;
    and Mode B — Legacy Emit/Convert, alternative)
  - II. eCR Bundle Decomposition & Resource-Granular Persistence (new primary
    principle: decompose Bundle_<uuid>.json; persist Composition, Patient, Encounter,
    Observation, MeasureReport, Practitioner, Organization, Location independently;
    no cross-resource transaction; shared resources deduplicated by identity)

Removed sections: none.

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ aligned (Constitution Check gate is
    constitution-agnostic; no hard-coded principle references)
  - .specify/templates/spec-template.md  ✅ aligned (no principle-specific content)
  - .specify/templates/tasks-template.md ✅ aligned (no principle-specific content)
  - .specify/templates/checklist-template.md ✅ aligned

Follow-up TODOs:
  - TODO(ECR_IG_VERSION): pin the exact hl7.fhir.us.ecr package version once the
    target deployment confirms it. Same for hl7.fhir.us.core and
    hl7.fhir.us.davinci-deqm. APHL chronic-ds Measure canonicals ARE pinned (|0.0.002).
  - The downstream spec/plan under specs/001-mvp-fhir-processor/ predates this
    amendment and describes the v1.0.0 emit-first behavior; it MUST be re-planned to
    reflect Mode A as primary before implementation continues.
-->

# eCR FHIR Processor Constitution

> Principles governing the development, testing, and maintenance of a Python
> utility that consumes FHIR R4 electronic Case Reporting (eCR) resources for
> chronic-disease quality measures and persists them to a target FHIR server. Its
> primary job is to **decompose the eCR Bundle into its contained resources and
> persist each as an independent, individually-addressable FHIR resource** so the
> destination server (Aidbox) can expose them to state Department-of-Health
> analytics via SQL-on-FHIR.

## Operating Modes

The processor supports two modes. **Mode A is the primary mode**; Mode B is retained
as an alternative for backward compatibility.

- **Mode A — eCR Decomposition & Persistence (PRIMARY):** Read the eCR message
  Bundle (`Bundle_<uuid>.json`), extract its contained clinical and administrative
  resources, and persist each one to the target FHIR server as an independent
  resource. This is the mode every new feature, test, and plan targets by default.
- **Mode B — Legacy Emit/Convert (ALTERNATIVE):** The v1.0.0 behavior — consume the
  per-scenario input Bundle, validate, and emit/persist whole eCR Bundles organized
  by measure and date. Preserved but not the focus of new work. Where a principle
  says "in Mode B," it applies only to this alternative path.

When a rule is mode-specific it says so; otherwise the rule applies to both modes.

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

### II. eCR Bundle Decomposition & Resource-Granular Persistence

In Mode A the processor's primary job is to take the eCR Bundle
(`Bundle_<uuid>.json`) and persist the resources contained within it as
**independent, individually-addressable resources** on the target FHIR server.

**Rationale:** The downstream consumer is an Aidbox FHIR server that exposes data to
state Department-of-Health analytics through SQL-on-FHIR. Independent, first-class
resources (not resources buried inside a Bundle) are what make those analytic
queries possible. Persisting each resource type independently also lets operators
run the script in stages — e.g., load the clinical resources now, and load resource
types the server is not yet configured to accept (MeasureReports, see Principle VI)
in a later run once server validation has been relaxed.

**Rules:**

- **Source of truth:** Mode A reads the eCR Bundle (`Bundle_<uuid>.json`) only. The
  per-scenario collection Bundle (`<scenario_id>.json`) and the standalone
  `MeasureReport_<uuid>.json` files are NOT inputs to Mode A (they remain Mode B
  inputs).
- **Resources persisted independently from the eCR Bundle:** `Composition`,
  `Patient`, `Encounter`, `Observation`, `MeasureReport`, `Practitioner`,
  `Organization`, and `Location`.
- **MessageHeader is NOT persisted independently.** It is the message envelope, not a
  standalone resource of analytic interest.
- **No cross-resource transaction.** The processor MUST NOT wrap the persistence of
  these resources in a single FHIR transaction or batch that succeeds or fails as a
  unit. Each resource type MUST be persistable on its own so that a rejection of one
  type (e.g., MeasureReport) neither rolls back nor blocks the others.
- **Shared resources are deduplicated by identity.** `Practitioner`, `Organization`,
  and `Location` are shared across Patients. The processor MUST persist them such
  that the same logical resource appearing in multiple eCR Bundles resolves to a
  single server resource (e.g., upsert by stable identity / conditional update),
  rather than creating duplicates.
- **References MUST remain resolvable.** After decomposition, references between the
  persisted resources (e.g., Composition → Patient/Encounter, Observation → Patient)
  MUST still resolve on the server. The processor MUST NOT break reference resolution
  while moving resources out of the Bundle.
- **Lower fidelity is tolerated.** The clinical resources inside the eCR Bundle carry
  lower fidelity for some data elements than the same resources in the collection
  Bundle. For Mode A this is acceptable; the processor MUST NOT fabricate higher-
  fidelity data to compensate (see Principle VI).

### III. FHIR Conformance — Target, Not Hard Gate

IG profile conformance remains the north star, and the processor MUST track which IG
versions it targets. However, conformance is **no longer an absolute pre-persistence
gate** in Mode A: enforcement is delegated to the target server's own (configurable)
validation, and persistence proceeds resource-by-resource.

**Rationale:** The eCR Bundle's resources are known to be lower-fidelity, and the
target Aidbox server's validation can be tuned per deployment. Treating the HL7
Reference Validator as an unconditional barrier would block the project's actual
goal — getting these resources into the analytics server. Conformance is therefore a
quality target we measure and report, while the authoritative accept/reject decision
in Mode A belongs to the destination server.

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
  at version `0.0.002`.

**Rules:**

- **Mode A enforcement:** The target FHIR server is the authoritative validator.
  Persistence proceeds per resource (Principle II); a server rejection of one
  resource is recorded and surfaced (Principle VI) but does not stop the others.
  Running the HL7 Reference Validator over Mode A resources for reporting/diagnostics
  is encouraged, but its errors are NOT an automatic blocker.
- **Mode B enforcement:** The HL7 Reference Validator gate is MANDATORY — Mode B
  resources MUST pass with zero project-introduced errors before they are persisted.
- **IG Version Tracking:** The code MUST declare which IG versions it targets as
  named constants or configuration values (not buried in comments), so the
  declaration is programmatically accessible.
- **Reference style:** Internal references use `urn:uuid:` or absolute server URLs
  consistent with the source eCR Bundle; the processor MUST NOT silently rewrite
  reference styles in a way that breaks resolution.
- **Timestamps:** Period/instant timestamps MUST include timezone offsets (e.g.,
  `+00:00`).
- **Accommodating IG Changes:** Updating a target IG version MUST be a deliberate,
  reviewable change (constant/config update + a validation pass), not an automatic or
  silent upgrade.

### IV. Dual-Gate Validation Testing

The test strategy validates the resources the processor persists or emits through two
independent gates — (1) the HL7 FHIR Reference Validator (`validator_cli.jar`), and
(2) the target FHIR server's own validation (resource acceptance and/or `$validate`).
Which gate is authoritative depends on the mode.

**Rationale:** For a data-handling tool targeting a formal specification, the most
valuable test is "will the destination server accept it, and how far is it from
conformance?" In Mode A the server is the authoritative arbiter of acceptance; the
Reference Validator provides a conformance-distance measurement. In Mode B the
Reference Validator is authoritative. Because the IGs evolve, tests MUST record which
IG versions they validated against so results are reproducible.

**Rules:**

- The `test/input/` directory holds the canonical fixtures; these are regression
  inputs and MUST NOT be edited to make a failing test pass.
- **Mode A tests:** For each fixture eCR Bundle, tests MUST assert that the expected
  set of independent resources (Principle II) is produced and accepted by the target
  server **per resource type**, and that no global transaction is used. A rejection
  of one resource type MUST NOT fail the persistence of the others in the test.
- **Mode B tests:** Every supported input shape MUST have at least one canonical
  fixture validated by the HL7 Reference Validator with zero project-introduced
  errors.
- **IG Version in Validation:** The HL7 FHIR Validator MUST be invoked with IG
  packages versioned (e.g., `-ig hl7.fhir.us.ecr#<ECR_IG_VERSION>`), and CI output /
  test artifacts MUST record which IG versions were used.
- Supplement conformance tests with targeted unit tests for any computation or
  transformation logic where correctness is not fully captured by profile validation
  alone (e.g., resource extraction, reference handling, shared-resource dedup,
  identity derivation).
- **LLM Development Validation:** When an LLM agent (Claude Code, Copilot, etc.)
  performs development work that could affect FHIR handling or persistence, it MUST
  exercise the relevant gate before considering the work complete: for Mode A, run
  the decomposition against the fixtures and confirm per-resource persistence
  behavior against the configured server (or a documented stand-in); for Mode B, run
  the HL7 Reference Validator as in v1.0.0. The LLM MUST NOT silently skip
  validation. If `validator_cli.jar`/Java or a target server is unavailable locally,
  the LLM MUST inform the user and request environment setup rather than skipping.
- **Known Upstream Validation Issues:** Validation errors originating in upstream IG
  dependencies (e.g., DEQM cross-version extension resolution, eCR package dependency
  gaps) MUST be documented in `known-validation-issues.md` at the repository root.
  Each entry MUST include the exact validator error message, affected resource type,
  root-cause analysis, responsible upstream package and HL7 working group,
  reproduction steps proving the error exists in the IG's own published examples, and
  the environment tested. CI filtering MUST match only the specific documented error
  patterns — never broad wildcards. When an upstream fix ships, the entry MUST be
  retested and removed if resolved.

### V. Multi-Measure / Multi-Population Input Coverage

The processor handles chronic-disease eCR test data organized by CMS quality measure
and by population outcome, as described in
`docs/CDS_TestData_DocumentationFor05252026zip.pdf`.

**Input shapes:**

- **Mode A input:** the eCR reporting `Bundle` (type `message`,
  `Bundle_<uuid>.json`): a `MessageHeader` referencing a nested content Bundle that
  combines the scenario's clinical resources with the MeasureReport. Mode A reads
  this file and decomposes its contained resources (Principle II).
- **Mode B input:** the per-scenario collection `Bundle` (`<scenario_id>.json`) of
  3–7 resources (always `Patient`, `Encounter`, `Condition`; usually `Observation`;
  sometimes `MedicationRequest`, `ServiceRequest`, `Procedure`) plus the standalone
  `MeasureReport_<uuid>.json`. These files are **ignored by Mode A.**
- Scenarios are grouped per measure into a **Standard** folder (patient in the
  Initial Population — collection Bundle + MeasureReport + eCR message Bundle) and a
  **Not-In-Population** folder (patient outside IP — collection Bundle + MeasureReport
  only, no eCR generated). Mode A operates only where an eCR message Bundle exists.

**Supported scope:**

- Target CMS measures: **CMS122** (Diabetes HbA1c Poor Control ≥9% —
  `poor-diabetic-control`), **CMS165** (Controlling High Blood Pressure —
  `controllable-bp`), and **CMS2** (Depression screening — `depression-screening`).
- Currently only **2 of 3** measures have sample data exercised by tests
  (`poor-diabetic-control` and `controllable-bp`). `depression-screening` (CMS2) is
  in scope but has **no fixtures yet**.

**Rules:**

- When sample data for a new measure (e.g., CMS2) or a new resource type arrives, add
  fixtures under `test/input/<measure>/` that exercise it and wire them into the
  validation pipeline (Principle IV).
- Adding support for a measure or input shape without a corresponding fixture is
  incomplete work.

### VI. Data Integrity and Defensive Processing

The processor MUST handle real-world data-quality issues gracefully, never producing
silently incorrect output and never silently dropping clinical content.

**Rationale:** Hospital-reported source data are messy. The processor must be robust,
because a subtle data error in a public-health report is worse than a loud failure.
With resource-granular persistence (Principle II), robustness means isolating
failures, not aborting the whole run.

**Rules:**

- Every data-quality accommodation MUST be logged at WARNING level or above.
- The processor MUST NOT fabricate clinical values to satisfy a profile; if input is
  missing data, it fails loudly for that resource rather than inventing content. The
  lower fidelity of eCR-Bundle resources (Principle II) is tolerated, NOT patched.
- **Per-resource failure isolation (Mode A):** A resource the target server rejects
  MUST be logged with the server's error and surfaced in the run summary and exit
  status — but its failure MUST NOT roll back or block the persistence of other
  resources or resource types. This is what enables the staged workflow: persist the
  clinical resources now, and re-run for resource types (e.g., MeasureReport) once the
  server's validation rules have been relaxed.
- **Mode B persistence gate:** In Mode B a resource that fails the Reference Validator
  MUST NOT be persisted; the failure MUST be surfaced (logged and reflected in exit
  status), not swallowed.
- The exit status MUST distinguish "all resources persisted" from "some resources
  rejected" so operators know whether a follow-up run is needed.

## Deployment & Security

### Configuration over Code Changes

Server- and deployment-specific data MUST live in configuration files, never
hardcoded.

**Rationale:** A single script with per-deploy config files is the deployment model.
IT staff edit config; they do not edit Python.

**Rules:**

- `config.example.json` is the canonical template. It MUST stay current with all
  supported configuration fields (FHIR server base URL, OAuth2 endpoints, IG
  versions, operating-mode selection, etc.).
- `config.json` (the real config with secrets) MUST be `.gitignore`'d. A `.gitignore`
  file MUST exist in the repo and MUST include `config.json`.
- A pre-commit hook or CI check SHOULD reject commits that include `config.json` or
  files matching `*.secret*`.
- Required config sections are validated at startup with clear error messages.

### Secret Protection

OAuth credentials and other secrets MUST NOT enter version control.

**Rationale:** `config.json` contains `client_id` and `client_secret` for FHIR server
OAuth2 authentication. Leaking these credentials could grant unauthorized access to
state health-data systems.

**Rules:**

- `.gitignore` MUST include: `config.json`, `*.secret*`, `.env`.
- CI SHOULD include a secret-scanning step (e.g., `git-secrets`, `trufflehog`, or
  GitHub's built-in secret scanning).
- `config.example.json` MUST use obvious placeholder values (e.g., `YOUR_CLIENT_ID`)
  that would fail authentication if accidentally used.
- Documentation MUST warn users not to commit real configs.

### Clear, Predictable Output

The results of a run MUST be deterministic, well-organized, and easy for a human to
inspect and troubleshoot.

**Rationale:** Hospital data managers and state health officials need to find,
review, and troubleshoot what was persisted. Output structure and run reporting are
part of the user experience.

**Rules:**

- **Mode A (persistence):** The run MUST produce a per-resource, per-resource-type
  summary of what was persisted, updated (dedup), or rejected — including the server's
  response for rejections — so an operator can tell exactly what landed and what needs
  a follow-up run. Any local artifacts (e.g., extracted resources written to disk for
  inspection) MUST be pretty-printed JSON.
- **Mode B (emit):** Output is organized first by CMS measure, then by reporting date:
  `output/{measure}/{YYYY-MM-DD}/`, mirroring the `test/output/{measure}/{standard,
  not-in-population}` layout. Emitted JSON MUST be pretty-printed.
- Logging goes to both console (immediate feedback) and a timestamped file (audit
  trail) under `log/`.

## Development Workflow

### CI Pipeline

All pull requests MUST pass automated checks before merge.

**Rationale:** With AI-assisted development and a small team, CI is the safety net
that catches regressions before they reach hospital workstations.

**Required checks:**

- **Lint:** Python linter (e.g., `ruff` or `flake8`) with consistent style rules.
- **Validation:** For Mode B, validate emitted output with `validator_cli.jar`
  against the IGs in Principle III (zero project-introduced errors). For Mode A,
  exercise decomposition against the fixtures and assert the expected independent
  resource set and per-resource-type persistence behavior against the target server
  (or a documented stand-in). Known upstream errors documented in
  `known-validation-issues.md` MUST be filtered by their specific patterns; any error
  not matching a documented known issue MUST fail the build.
- **Secret scanning:** Reject commits containing likely credentials.
- Checks run via GitHub Actions.
- The CI pipeline itself is subject to this constitution — changes to CI config
  require the same review as code changes.

### README as Living Documentation

Any change that affects user-facing behavior, project architecture, IG conformance,
operating modes, or developer workflow MUST be evaluated for a corresponding
`README.md` update.

**Rationale:** The README is the first document new contributors, hospital IT staff,
and LLM agents encounter. If it falls out of sync with the code, users make incorrect
assumptions. Keeping it current is cheaper than debugging the confusion it causes.

**Rules:**

- When a change adds or alters operating modes, IG references, profile/Measure URLs,
  CLI flags, configuration fields, output/run-summary structure, supported
  measures/input shapes, or version-tracking constants, the implementer MUST check
  whether `README.md` needs a corresponding update.
- README updates SHOULD be included in the same PR as the code change.
- LLM agents performing development work SHOULD flag README staleness when the code
  has diverged from what the README describes.

### Single-File Simplicity (Until It Hurts)

Prefer fewer, well-organized files over premature modularization.

**Rules:**

- A single entry-point script (e.g., `process.py`) remains the entry point; the
  operating mode is selected by flag or config, not by a separate program.
- Extract modules only when a clear boundary emerges (e.g., FHIR client, validation
  orchestration, Bundle decomposition, input parsers) AND the single file exceeds
  ~1000 lines.
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

**Version**: 2.0.0 | **Ratified**: 2026-06-09 | **Last Amended**: 2026-06-11
