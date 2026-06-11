# Implementation Plan: MVP eCR FHIR Processor

**Branch**: `add-constitution` | **Date**: 2026-06-11 (amended for constitution v1.1.0) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-mvp-fhir-processor/spec.md`; constitution
`.specify/memory/constitution.md` **v1.1.0** (Principles VI + amended V).

## Summary

Build a single-file, zero-dependency Python 3 utility (`process.py`) that reads FHIR
R4 eCR bundles from the root `input/` tree (organized by CMS measure and population
outcome), stamps each resource with searchable provenance metadata (processor identity,
git-derived version, processing timestamp, source filename), and persists everything to
an OAuth2-secured target FHIR server using **update-in-place** (`PUT`-by-retained-id)
semantics so re-runs do not create duplicates.

**Persistence model (constitution v1.1.0).** To serve the downstream SQL-on-FHIR analytics
consumer, the resources contained in each `collection` bundle are persisted as **independent,
first-class resources** — one `PUT [base]/Type/<retained-id>` per resource, **not** wrapped
in an atomic `transaction` bundle (a non-atomic `batch` is an allowed optimization; a
`transaction` is not). For in-population scenarios, the eICR **`Composition`** nested in the
`message` bundle is **promoted to a first-class resource** (`PUT [base]/Composition/<id>`) in
addition to persisting the message bundle whole — only the Composition is promoted (no
lower-fidelity overwrite of the authoritative collection-bundle resources). Standalone
MeasureReports are PUT under their retained ids. Because nothing shares a global transaction,
each resource **type** is persistable **independently** (`--only-types`/`--skip-types`): a
type the server currently rejects (the test MeasureReports fail Aidbox validation) can be
landed in a separate run after the Aidbox validation profile is relaxed, without duplicating
or rolling back what already persisted. Outcomes are logged per resource to console + a
timestamped audit file and summarized with a non-zero exit on any failure.

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
per-resource PUT planning from a collection bundle, eICR Composition extraction,
type-filter selection, version derivation, config validation).

**Target Platform**: Linux (developer + GitHub Actions CI). Runs anywhere Python 3 +
network access to the FHIR server exist.

**Project Type**: Single-project CLI utility (constitution: Single-File Simplicity).

**Performance Goals**: Not latency-critical. Batch processing of the fixture-scale
input set (tens of bundles) completes well under a minute excluding network; throughput
is bounded by FHIR server round-trips, not local processing.

**Constraints**: Zero runtime dependencies; secrets never in VCS; deterministic,
human-readable output; loud failure over silent incorrectness; timezone-offset
timestamps; references must stay resolvable after persistence. **No global transaction —
each resource/type persists independently with isolated, re-runnable outcomes (Principle V);
contained resources and the eICR Composition land as first-class, analytics-queryable
resources (Principle VI).**

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
  referenced resource must exist at `[base]/Type/<id>` to resolve. Implemented (per
  constitution v1.1.0) as **independent `PUT [base]/Type/<id>` per resource** — no atomic
  `transaction` bundle, so failures isolate and types persist independently (D2, D10). The
  eICR `Composition` is additionally promoted to first-class (D2b). *(Earlier draft used a
  single transaction bundle; superseded by amended Principles V + VI.)*

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | Runtime uses only Python 3 stdlib (urllib for HTTP/OAuth, json, subprocess for git) | ✅ PASS |
| II. FHIR Profile Conformance | `meta.profile` preserved; references not rewritten in a way that breaks resolution (relative refs resolve because ids are retained); IG versions declared as named constants; provenance metadata is additive | ✅ PASS (IG-version constants added in design) |
| III. Dual-Gate Validation Testing | CI + dev run processor over `test/input/`, validate with `validator_cli.jar` (versioned `-ig`), and confirm server acceptance | ✅ PASS (wired in tasks) |
| IV. Multi-Measure / Multi-Population Coverage | Fixtures exercise CMS122 + CMS165 × {standard, not-in-population}; CMS2 placeholder acknowledged | ✅ PASS |
| V. Data Integrity & Defensive Processing | Warn-and-skip malformed input; never fabricate; rejected resources not counted persisted; non-zero exit. **Independent persistence (no global transaction):** per-resource `PUT`s (or non-atomic `batch`), failures isolated per resource, `--only-types`/`--skip-types` enable separate idempotent per-type runs (D2, D8, D10) | ✅ PASS (persistence reworked to per-resource independence) |
| VI. Analytics-Ready Persistence Granularity | Contained `collection` resources persisted first-class (`PUT [base]/Type/<id>`); eICR `Composition` promoted first-class for in-population scenarios; only the Composition promoted (no fidelity regression over authoritative collection-bundle resources) (D2, D2b) | ✅ PASS (added Composition promotion + first-class contained resources) |
| Deployment & Security | Config-over-code; `config.json`, `*.secret*` already in `.gitignore`; example uses placeholder values; output organized `output/{measure}/{YYYY-MM-DD}/` | ✅ PASS |
| Development Workflow | Single entry-point `process.py`; README updated for CLI/config/metadata; CI checks (lint, validation, secret scan) | ✅ PASS (README + CI in tasks) |

**Result**: No violations (re-checked against constitution v1.1.0). No Complexity Tracking
entries required. **Note:** D2b (Composition promotion) and D2/D10 (independent per-type
persistence) are mandated by the amended constitution but extend beyond the requirements
written in `spec.md` (which stops at FR-019 / OQ-1, OQ-2). Run `/speckit-specify` to formalize
them as explicit FRs so spec and plan re-converge; then re-run `/speckit-tasks` to refresh
`tasks.md` (the existing `tasks.md` still reflects the superseded transaction-based model).

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
│   └── fhir-submission.md         # Independent per-resource PUT + Composition-promotion contract
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
