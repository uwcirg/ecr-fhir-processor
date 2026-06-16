# Implementation Plan: Patient ViewDefinition + Publish/Materialize

**Branch**: `002-patient-viewdefinition` | **Date**: 2026-06-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-patient-viewdefinition/spec.md`; constitution
`.specify/memory/constitution.md` **v1.2.0** (Principle VII new; VI expanded).

## Summary

Author a checked-in, version-controlled **Patient `ViewDefinition`** (SQL-on-FHIR, as
implemented by Aidbox) that flattens first-class Patient resources into one analytics row per
patient with the default DoH demographic columns (patient key, MRN, name parts, administrative
sex, birth date, deceased flag, race, ethnicity, address city/state/postal). Add a **stdlib-only
publish/materialize step as its own entry point `publish_views.py`** that, for every
ViewDefinition file in a checked-in directory, `PUT`s it to `[base]/ViewDefinition/<id>`
(update-in-place) and then `POST`s `[base]/ViewDefinition/<id>/$materialize`, reporting upload and
materialization outcomes **separately and per view**, isolating failures, and reflecting any
failure in the exit status.

**Separate entry point, shared code.** Publishing/materializing views is triggered by a different
event than ingestion — it is a rare schema-change activity (re-run only to change the
ViewDefinition; with the default `view` materialization type the view reflects live data
automatically), whereas `process.py` runs on every ingest. So this ships as its own script
`publish_views.py`, not a `process.py` subcommand (research.md R4).

**Reuse, not rebuild.** The shared primitives are **extracted from `process.py` into a third
module `fhir_common.py`** that both scripts import — `RunConfig` / `load_config` /
`validate_config`, the OAuth2 client-credentials `FhirClient` (token caching + 401 refresh +
`aidbox-validation-skip` header), `setup_logging`, and the per-item outcome/summary/exit-code
pattern (`FileOutcome` / `RunSummary`), plus supporting constants/exceptions. `process.py` keeps
its behavior unchanged (pure move + import; verified by re-running the feature-001 validation
pipeline). No new dependency, no new auth, no hardcoded server values, no copy-paste (research.md
R1). The mechanism is **resource-type-agnostic**: it discovers ViewDefinition files from a
directory, so adding the next resource type later (Story 3) is dropping in a file — no code
change.

**Materialization type.** `$materialize` requires a `type` (`view` | `materialized-view` |
`table`). Default to **`view`** (an always-current SQL view → SC-001 "exactly N rows" holds on
every read with no manual refresh), with the type **configurable** so a deployment can choose a
snapshot `materialized-view`/`table` if it prefers. See [research.md](./research.md) R3.

## Technical Context

**Language/Version**: Python 3 (standard library only — `json`, `urllib`, `argparse`,
`logging`, `os`, `sys`, `pathlib`, `glob`). `publish_views.py` imports shared primitives from the
new `fhir_common.py` (extracted from `process.py`).

**Primary Dependencies**: None at runtime (constitution Principle I). Dev/CI only: linter
(`ruff`), stdlib `unittest`. The HL7 `validator_cli.jar` does **not** apply here — a SQL-on-FHIR
`ViewDefinition` is a logical-model resource outside the eCR/US-Core IG set; its conformance
gate is **Aidbox acceptance on `PUT` + `$materialize` success** (Principle III gate 2), not the
reference validator (gate 1). See research.md R5.

**Storage**: Target Aidbox FHIR server (remote, OAuth2 client-credentials). The ViewDefinition
files live in the repo; the materialized view lives server-side in Aidbox's `sof` schema.

**Testing**: (1) **End-to-end against Aidbox** — publish + materialize the Patient view against a
server holding the fixture Patients, then query the view and assert one row per Patient with
expected columns (quickstart). (2) **Targeted stdlib `unittest`** for pure logic: ViewDefinition
file discovery, the `$materialize` `Parameters` body builder, per-view outcome/exit-code
aggregation, config validation reuse, and a JSON well-formedness + required-field check on the
checked-in ViewDefinition (`resourceType`/`resource`/`status`/`select`).

**Target Platform**: Linux (developer + GitHub Actions CI). Anywhere Python 3 + network to
Aidbox exist.

**Project Type**: Single-project CLI utility. Two entry points (`process.py`,
`publish_views.py`) over a shared `fhir_common.py` module — the boundary the constitution's
Single-File Simplicity rule explicitly names ("FHIR client logic, validation orchestration"),
warranted now that `process.py` is at the ~1000-line threshold (research.md R4).

**Performance Goals**: Not latency-critical. One ViewDefinition today; bounded by a handful of
server round-trips (PUT + materialize per view). Completes in seconds excluding network.

**Constraints**: Zero runtime dependencies; secrets never in VCS; base URL + credentials from
config only; fail-fast config validation before any network call; per-view failure isolation
(no view's failure blocks another); idempotent re-run (PUT-by-id + `$materialize` update-in-place
→ no duplicate views); select only first-class resources (Principle VI); never fabricate column
values (absent field → null, FR-010).

**Scale/Scope**: **Patient only** (FR-012). One checked-in ViewDefinition; the step handles N
files generically. Other resource types are explicitly out of scope until the analytics team
specifies their columns.

### Resolved unknowns

All Technical-Context unknowns were resolvable from the existing codebase + Aidbox docs; details
and decisions are in [research.md](./research.md) (R1–R6). No `NEEDS CLARIFICATION` remains. The
default column set (FR-002) is an informed, reviewable default, not a finalized analytics-team
contract — it is captured in the contract and flagged for confirmation, not treated as a blocker.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Zero-Dependency Runtime | Step uses only stdlib + reuses `FhirClient`/config/logging via the shared `fhir_common.py`; no new package | ✅ PASS |
| II. FHIR Profile Conformance | ViewDefinition conforms to SQL-on-FHIR as Aidbox implements it; it is not an eCR/US-Core profiled resource, so `meta.profile` + the HL7 validator don't apply. Aidbox version target recorded as an assumption (≥ 2508). IG-version config untouched | ✅ PASS |
| III. Dual-Gate Validation Testing | The authoritative gate for a ViewDefinition is **server acceptance** (gate 2): `PUT` accepted + `$materialize` succeeds. Gate 1 (`validator_cli.jar`) is N/A for this resource (research.md R5). Pure logic covered by `unittest`; e2e covered by quickstart | ✅ PASS |
| IV. Multi-Measure / Multi-Population Coverage | N/A — this feature is about flattening persisted Patients, not measure/population input shapes. Patient fixtures already exercised by feature 001 supply the rows | ✅ PASS (N/A) |
| V. Data Integrity & Defensive Processing | Per-view failure isolation (one view's publish/materialize failure logged + reflected in exit, does not block others); idempotent re-run via PUT-by-id; never fabricate (absent field → null column, FR-010); rejection surfaced not swallowed | ✅ PASS |
| VI. Analytics-Ready Persistence Granularity | The Patient ViewDefinition selects only from first-class `Patient/<id>` resources (FR-003); it never reaches into an un-promoted Bundle | ✅ PASS |
| VII. Analytics View Definitions & Materialization | **Directly satisfied**: checked-in conformant Patient ViewDefinition + stdlib publish/materialize script (PUT then `$materialize`), idempotent, config-driven, per-type isolation; Patient-only, demand-driven | ✅ PASS |
| Deployment & Security | base URL/creds from `config.json` only (reuses `validate_config`); fail-fast before network; no new config secret; `config.example.json` extended only if a new optional field (materialize type) is added | ✅ PASS |
| Development Workflow | Separate `publish_views.py` entry point over shared `fhir_common.py`; `process.py` stays the processor's entry point; the module split is the constitution's named boundary at the ~1000-line threshold (R4), not premature modularization; README updated for the new script/usage; CI lint + the new e2e/unit checks | ✅ PASS |

**Result**: No violations. No Complexity Tracking entries required. This plan stays within
constitution v1.2.0; it formalizes Principle VII for Patient.

## Project Structure

### Documentation (this feature)

```text
specs/002-patient-viewdefinition/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — R1–R6 decisions (reuse, column mapping, materialize type, etc.)
├── data-model.md        # Phase 1 — ViewDefinition entity, column→FHIRPath map, outcome model
├── quickstart.md        # Phase 1 — runnable publish→materialize→query validation guide
├── contracts/           # Phase 1
│   ├── viewdefinition-patient.md   # The Patient ViewDefinition resource + column/FHIRPath contract
│   └── publish-materialize-cli.md  # publish_views.py CLI + PUT/$materialize server-operation contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created here)
```

### Source Code (repository root)

```text
fhir_common.py                   # NEW — shared primitives extracted from process.py:
                                 #   FhirClient, RunConfig, load_config/validate_config,
                                 #   setup_logging, FileOutcome/RunSummary, constants/exceptions
process.py                       # Existing entry point — now imports the above from fhir_common
                                 #   (pure move + import; behavior unchanged)
publish_views.py                 # NEW entry point — discover ViewDefinition files, PUT each,
                                 #   POST $materialize, per-view outcome reporting + exit code
viewdefinitions/                 # NEW — checked-in, version-controlled ViewDefinition resources
└── patient.ViewDefinition.json  #   the Patient view (one file per resource type; Patient only now)

config.example.json              # Extend with OPTIONAL server.materialize_type (default "view")
config.json                      # Real config w/ secrets — git-ignored (unchanged mechanism)

tests/                           # Targeted stdlib unittest
└── test_viewdefinition.py       #   discovery, $materialize body, outcome/exit aggregation,
                                 #   ViewDefinition required-field/JSON checks
```

**Structure Decision**: Single-project CLI, consistent with feature 001. The publish/materialize
mechanism is its **own entry point `publish_views.py`** (research.md R4) — view publishing is
triggered by ViewDefinition changes, not by data ingestion, so it stays separate from
`process.py`. Shared client/config/logging/outcome code is extracted into `fhir_common.py`
(imported by both scripts) so there is no duplication — the boundary the constitution's
Single-File Simplicity rule names, warranted at the ~1000-line threshold. ViewDefinitions live in
a new top-level `viewdefinitions/` directory so the step discovers them generically — adding a
resource type later is a new file, no code change (FR-011, Story 3).

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
