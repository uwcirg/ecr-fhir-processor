# Implementation Plan: MVP eCR FHIR Processor

**Branch**: `add-constitution` | **Date**: 2026-06-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-mvp-fhir-processor/spec.md`

## Summary

Build a single-file, zero-dependency Python 3 utility (`process.py`) that reads FHIR
R4 eCR bundles from the root `input/` tree (organized by CMS measure and population
outcome), stamps each resource with searchable provenance metadata (processor identity,
git-derived version, processing timestamp, source filename), and persists everything to
an OAuth2-secured target FHIR server using **update-in-place** semantics so re-runs do
not create duplicates. Collection bundles are persisted by converting them to FHIR
**transaction** bundles (each entry `PUT [base]/Type/<retained-id>`); standalone
MeasureReports and eCR `message` bundles are PUT under their retained ids. Outcomes are
logged to console + a timestamped audit file and summarized with a non-zero exit on any
failure.

## Technical Context

**Language/Version**: Python 3 (standard library only — `json`, `urllib`, `uuid`,
`datetime`, `logging`, `argparse`, `os`, `sys`, `subprocess` for git, `pathlib`)

**Primary Dependencies**: None at runtime (constitution Principle I). Dev/CI only: a
linter (`ruff`/`flake8`), the HL7 FHIR Reference Validator (`validator_cli.jar` + Java).

**Storage**: Target FHIR R4 server (remote, OAuth2 client-credentials). Local
filesystem for input (`input/`), output mirror (`output/`), and audit logs (`log/`).

**Testing**: End-to-end conformance + integration. Dual-gate per constitution
Principle III: (1) HL7 Reference Validator against processed/emitted bundles, (2) FHIR
server acceptance. Targeted stdlib `unittest` for pure logic (metadata stamping,
collection→transaction conversion, version derivation, config validation).

**Target Platform**: Linux (developer + GitHub Actions CI). Runs anywhere Python 3 +
network access to the FHIR server exist.

**Project Type**: Single-project CLI utility (constitution: Single-File Simplicity).

**Performance Goals**: Not latency-critical. Batch processing of the fixture-scale
input set (tens of bundles) completes well under a minute excluding network; throughput
is bounded by FHIR server round-trips, not local processing.

**Constraints**: Zero runtime dependencies; secrets never in VCS; deterministic,
human-readable output; loud failure over silent incorrectness; timezone-offset
timestamps; references must stay resolvable after persistence.

**Scale/Scope**: 3 CMS measures (CMS122, CMS165, CMS2), 2 population outcomes
(Standard, Not-In-Population). Currently 2 measures have fixtures; CMS2 is a placeholder.
3–7 resources per collection bundle; standard scenarios add a MeasureReport + eCR
message bundle.

### Resolved Open Questions (from spec OQ-1 / OQ-2)

A data-inspection spike over `test/input/**` settled both deferred questions with
evidence (details in [research.md](./research.md)):

- **OQ-1 — Identity**: **Retain** original `resource.id`. All ids are GUIDs (globally
  unique); shared resources (Practitioner/Organization/Location) reuse identical GUIDs
  across scenarios, so retaining ids + PUT yields correct update-in-place with no
  duplicates.
- **OQ-2 — Granularity**: **Persist the contained resources** (not the opaque
  collection Bundle). Inter-resource references are **relative** (`Type/<id>`), so each
  referenced resource must exist at `[base]/Type/<id>` to resolve. Implemented by
  converting each collection Bundle to a **transaction** Bundle of `PUT` entries.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | Runtime uses only Python 3 stdlib (urllib for HTTP/OAuth, json, subprocess for git) | ✅ PASS |
| II. FHIR Profile Conformance | `meta.profile` preserved; references not rewritten in a way that breaks resolution (relative refs resolve because ids are retained); IG versions declared as named constants; provenance metadata is additive | ✅ PASS (IG-version constants added in design) |
| III. Dual-Gate Validation Testing | CI + dev run processor over `test/input/`, validate with `validator_cli.jar` (versioned `-ig`), and confirm server acceptance | ✅ PASS (wired in tasks) |
| IV. Multi-Measure / Multi-Population Coverage | Fixtures exercise CMS122 + CMS165 × {standard, not-in-population}; CMS2 placeholder acknowledged | ✅ PASS |
| V. Data Integrity & Defensive Processing | Warn-and-skip malformed input; never fabricate; rejected resources not counted persisted; non-zero exit | ✅ PASS |
| Deployment & Security | Config-over-code; `config.json`, `*.secret*` already in `.gitignore`; example uses placeholder values; output organized `output/{measure}/{YYYY-MM-DD}/` | ✅ PASS |
| Development Workflow | Single entry-point `process.py`; README updated for CLI/config/metadata; CI checks (lint, validation, secret scan) | ✅ PASS (README + CI in tasks) |

**Result**: No violations. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-mvp-fhir-processor/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output — OQ-1/OQ-2 spike + key decisions
├── data-model.md        # Phase 1 output — entities, metadata model, transforms
├── quickstart.md        # Phase 1 output — runnable validation guide
├── contracts/           # Phase 1 output
│   ├── cli.md                     # CLI invocation + config contract
│   ├── provenance-metadata.md     # Searchable meta.tag contract
│   └── fhir-submission.md         # Bundle→transaction + PUT submission contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
process.py               # Single entry-point CLI (constitution: Single-File Simplicity)
config.example.json      # Committed template (server + IG versions; NO software.version)
config.json              # Real config with secrets — git-ignored (already covered)

input/                   # Real input data (mirrors test/input layout)
└── {measure}/{standard|not-in-population}/{scenario}/*.json
output/                  # Optional local mirror of submitted bundles, by measure/date
└── {measure}/{YYYY-MM-DD}/
log/                     # Timestamped audit logs
└── ecr-fhir-processor_{YYYY-MM-DDtHHMMSS}.log

test/                    # DEV/TEST FIXTURES ONLY (never real data)
├── input/  {measure}/{standard|not-in-population}/{scenario}/*.json
└── output/ {measure}/{standard|not-in-population}/
tests/                   # Targeted stdlib unittest for pure logic
validator_cli.jar        # HL7 FHIR Reference Validator (dev/CI gate)
```

**Structure Decision**: Single-project CLI. One entry-point `process.py` per the
constitution's Single-File Simplicity principle (extract modules only past ~1000 lines).
Real data flows through root `input/`/`output/`/`log/`; the `test/` tree is exclusively
development fixtures.

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
