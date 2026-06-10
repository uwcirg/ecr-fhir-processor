---
description: "Task list for MVP eCR FHIR Processor"
---

# Tasks: MVP eCR FHIR Processor

**Input**: Design documents from `specs/001-mvp-fhir-processor/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (cli.md,
fhir-submission.md, provenance-metadata.md), quickstart.md

**Tests**: INCLUDED. The constitution (Principle III — Dual-Gate Validation Testing) and
plan.md ("Targeted stdlib `unittest` for pure logic") mandate testing, so unit tests for
pure logic and the validator/server gates are part of scope.

**Architecture note**: Per the constitution's **Single-File Simplicity** principle, all
runtime logic lives in one entry-point `process.py` at the repository root. Because most
implementation tasks edit that same file, they are **sequential within a story** (no `[P]`).
Tests live in separate `tests/*.py` files and CAN run in parallel (`[P]`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3 (maps to the user stories in spec.md). Setup / Foundational /
  Polish tasks carry no story label.
- All paths are relative to the repository root.

## Path Conventions

- Single-project CLI: `process.py`, `config.example.json` at repo root; `tests/` at repo
  root; real data in `input/`/`output/`/`log/`; dev fixtures in `test/input/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and the reconciled config template.

- [ ] T001 Create the single-file skeleton `process.py` at repo root: module docstring,
  `def main(argv=None) -> int:` returning an exit code, and the
  `if __name__ == "__main__": sys.exit(main())` guard (constitution: Single-File Simplicity).
- [ ] T002 Reconcile `config.example.json` at repo root per research.md D7: remove
  `software.version`, add the `ig_versions{}` block (`hl7.fhir.us.ecr`/`us.core`/
  `davinci-deqm` = `TODO_PIN`, `aphl.chronic-ds` = `0.0.002`) and the
  `paths{input_dir,output_dir,log_dir}` block; keep `software.name`/`identifier_*` and
  `server.*` placeholders (`YOUR_*`).
- [ ] T003 [P] Create `tests/` package at repo root with an empty `tests/__init__.py`; tests
  read fixtures from the existing `test/input/` tree.
- [ ] T004 [P] Verify/extend `.gitignore` at repo root to cover `config.json`, `*.secret*`,
  `.env`, `/output/`, and `/log/` (constitution: Secret Protection MUST-include set).
- [ ] T005 [P] Add lint configuration (`.ruff.toml` or `[tool.ruff]` in `pyproject.toml`) at
  repo root targeting Python 3 stdlib-only style (constitution: Development Workflow).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core scaffolding in `process.py` that EVERY user story depends on (CLI,
logging, constants, config load, discovery/classification, run summary).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. All tasks edit
`process.py` and are sequential.

- [ ] T006 Implement dual logging in `process.py` (Python `logging`): console handler +
  timestamped file handler writing `log/ecr-fhir-processor_{YYYY-MM-DDtHHMMSS}.log`;
  `--verbose` raises console to DEBUG (FR-013, D9).
- [ ] T007 Define canonical constants in `process.py`: provenance base
  `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem` with `processed-by`/`processed-on`/
  `source-file` systems, processor identity `ecr-fhir-processor`, and IG-version constants
  sourced from `config.ig_versions` (Principle II; provenance-metadata contract).
- [ ] T008 Implement `argparse` CLI in `process.py` for all flags in contracts/cli.md
  (`--config`, `--input-dir`, `--measure`, `--output-dir`, `--no-output-mirror`,
  `--dry-run`, `--log-dir`, `--verbose`) with the documented defaults.
- [ ] T009 Implement config loading in `process.py`: read the JSON config into a `RunConfig`
  structure (software/server/ig_versions/paths) with CLI overrides for paths/measure
  (data-model RunConfig; cli contract). NOTE: fail-fast *validation* is US3.
- [ ] T010 Implement input discovery & classification in `process.py`: recursively find
  `*.json` under the input root, build `InputFile`/`ScenarioFolder` with `measure`,
  `population`, and `kind` (`collection-bundle` | `measure-report` | `message-bundle` |
  `unknown`); empty input → exit 0 "nothing processed" (FR-001, data-model, cli contract).
- [ ] T011 Implement the `RunSummary` accumulator in `process.py`: per-file outcomes
  (`filename, kind, action, resource_count, status, detail`), aggregate counts
  (`read/submitted/succeeded/failed/skipped`), final summary report, and exit code
  `0` iff `failed == 0` (FR-014, D8, data-model RunSummary).

**Checkpoint**: Foundation ready — `process.py` can discover/classify input and report a
summary. User stories can now begin.

---

## Phase 3: User Story 1 - Process and persist eCR bundles to a FHIR server (Priority: P1) 🎯 MVP

**Goal**: Read every bundle in the input set and persist its resources to the OAuth2-secured
FHIR server using update-in-place (PUT-by-id) semantics, reporting each outcome.

**Independent Test**: Run `python3 process.py --input-dir test/input` against a reachable
FHIR server; confirm resources from every scenario appear on the server and the RunSummary
reports per-bundle success/failure with the correct exit status.

### Tests for User Story 1 ⚠️

> Write these FIRST and confirm they FAIL before implementing.

- [ ] T012 [P] [US1] Unit test for the collection→transaction transform (each entry gets
  `request = {method:"PUT", url:"<Type>/<id>"}`, `type` becomes `transaction`) in
  `tests/test_transform.py` (D2, fhir-submission contract).
- [ ] T013 [P] [US1] Unit test for the `(resourceType, id)` collision guard: differing
  content → error/raise; identical content → allowed dedup, in `tests/test_collision.py`
  (FR-019, D4b).

### Implementation for User Story 1

- [ ] T014 [US1] Implement OAuth2 client-credentials auth in `process.py`: POST to
  `server.token_endpoint`, cache bearer token in memory, send `Authorization: Bearer` +
  `Accept: application/fhir+json` on FHIR calls, refresh once on 401 (FR-009, D6,
  fhir-submission contract). Uses `urllib` only.
- [ ] T015 [US1] Implement the collection→transaction transform in `process.py`: convert a
  `collection` Bundle to a `transaction` Bundle of `PUT [Type]/<retained-id>` entries (D2,
  data-model transforms). Retain original `resource.id` (D1).
- [ ] T016 [US1] Implement per-kind submission in `process.py`: transaction Bundle → POST
  `[base]`; standalone MeasureReport → PUT `[base]/MeasureReport/<id>`; eCR message Bundle →
  PUT `[base]/Bundle/<id>` (FR-002/003/016, fhir-submission contract). GATE (constitution
  Principle II): real (non-dry-run) submission MUST be preceded by a passing conformance
  validation over the dry-run output — see T032.
- [ ] T017 [US1] Implement the within-run `(resourceType, id)` collision detector in
  `process.py`: the seen-set tracks ONLY top-level persisted resources (transaction
  entries + standalone PUTs), NOT resources nested inside a message Bundle — so the fixed
  `eicr-report-*` document-Bundle id (D4b) never enters the set. Differing content → log
  ERROR + reflect in exit status; identical content → DEBUG/INFO dedup (FR-019, D4b).
- [ ] T018 [US1] Implement reference handling in `process.py`: do NOT rewrite references;
  log WARNING on absolute references to a non-target host; relative refs left intact so
  they resolve via retained ids (FR-017, D3).
- [ ] T019 [US1] Wire submission outcomes into `RunSummary` in `process.py`: non-2xx → log
  ERROR including the server `OperationOutcome`, count `failed` (never `succeeded`); a
  rejected transaction fails all its resources (FR-012, D8, fhir-submission SUB-3).
- [ ] T020 [US1] Implement `--dry-run` and the output mirror in `process.py`: dry-run runs
  all transforms but performs no token request/submission and logs the would-be requests;
  otherwise optionally mirror submitted JSON (pretty-printed / indented) to
  `output/{measure}/{YYYY-MM-DD}/` unless `--no-output-mirror` (D9, constitution Clear
  Output, cli + fhir-submission SUB-5).

**Checkpoint**: US1 is fully functional — bundles persist to the server with update-in-place
semantics and per-bundle reporting. This is the MVP. Before persisting to a *real* server,
run the conformance gate (T032) over dry-run output (quickstart A→B precede C).

---

## Phase 4: User Story 2 - Stamp filterable processing metadata onto resources (Priority: P1)

**Goal**: Before submission, stamp every persisted resource (and message-Bundle `meta`) with
searchable provenance: processor identity, git-derived version, run-constant timestamp, and
source filename — retrievable via FHIR `_tag` search.

**Independent Test**: After a run, `GET [base]/Patient?_tag=<BASE>/processed-by|ecr-fhir-processor`
returns only this processor's resources; a `processed-on` `_tag` filter narrows to one run;
a `source-file` `_tag` traces resources to their origin file.

### Tests for User Story 2 ⚠️

> Write these FIRST and confirm they FAIL before implementing.

- [ ] T021 [P] [US2] Unit test for stamping in `tests/test_provenance.py`: three `meta.tag[]`
  entries (processed-by+version, processed-on, source-file) + `meta.source`; idempotent
  re-stamp replaces own tags by `system` (INV-2); preserves pre-existing tags/`profile`
  (INV-3) (D4, provenance-metadata contract).
- [ ] T022 [P] [US2] Unit test for git version derivation + `unknown` fallback in
  `tests/test_version.py` (D5, FR-006).

### Implementation for User Story 2

- [ ] T023 [US2] Implement git version derivation in `process.py`:
  `git describe --tags --always --dirty` via `subprocess`; fallback literal `unknown` with a
  WARNING when git is unavailable (FR-006, D5).
- [ ] T024 [US2] Implement the run-constant processing timestamp in `process.py`: ISO-8601
  instant with timezone offset, computed once per run and reused for every resource
  (FR-007, INV-1/INV-4).
- [ ] T025 [US2] Implement `stamp(resource_meta)` in `process.py`: add the three `meta.tag[]`
  entries + `meta.source`; additive and idempotent (replace own tags by `system`, never
  append duplicates); never alter clinical content (FR-004/005/015, D4, provenance contract).
- [ ] T026 [US2] Insert stamping into the submission pipeline in `process.py`: stamp each
  transaction entry's resource, the standalone MeasureReport, and the message Bundle's own
  `meta` — before T016 submission (FR-004, integrates with US1 T015/T016).

**Checkpoint**: US1 + US2 both work — persisted resources are searchable by provenance tags.

---

## Phase 5: User Story 3 - Configure the run without editing code (Priority: P2)

**Goal**: An operator copies `config.example.json`, fills in server/credentials, and runs the
processor with no source edits; misconfiguration fails fast and loudly.

**Independent Test**: Copy the example config, populate it, run; confirm it authenticates
using only config values. A config missing a required field, or left at `YOUR_*`
placeholders, fails fast with a message naming the field and a non-zero exit.

### Tests for User Story 3 ⚠️

> Write this FIRST and confirm it FAILS before implementing.

- [ ] T027 [P] [US3] Unit test for config validation in `tests/test_config.py`: missing/empty
  required `server.*` field → error naming the field; values still equal to `YOUR_*`
  placeholders → rejected (FR-010, D7, cli contract).

### Implementation for User Story 3

- [ ] T028 [US3] Implement fail-fast config validation in `process.py`: require non-empty
  `server.base_url`/`token_endpoint`/`client_id`/`client_secret` (except under `--dry-run`);
  reject `YOUR_*` placeholder values; emit a field-specific message and non-zero exit
  (FR-010, US3 scenarios 2 & 3, D7, cli contract).
- [ ] T029 [US3] Implement path/measure precedence in `process.py`: CLI flags override
  `config.paths` defaults (`input`/`output`/`log`); `--measure` restricts to one measure
  folder (cli contract, US3 scenario 1).

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, CI, and the constitution's dual-gate validation.

- [ ] T030 [P] Update `README.md` at repo root: CLI usage, `cp config.example.json
  config.json` setup, provenance/search recipes, and the runtime-derived version note
  (constitution: README as Living Documentation).
- [ ] T031 [P] Add CI workflow `.github/workflows/ci.yml`: lint (ruff/flake8), run
  `python3 -m unittest`, dry-run over `test/input`, and a secret scan (constitution:
  CI Pipeline; Dual-Gate gate prep).
- [ ] T032 Create a concrete conformance-gate script `scripts/validate.sh` invoking
  `java -jar validator_cli.jar "output/**/*.json" -version 4.0.1` with versioned `-ig`
  packages from `config.ig_versions`; zero project-introduced errors = pass. Invoked by CI
  (T031) and by the LLM-validation step, and run over dry-run output BEFORE real submission
  (T016 gate) — constitution Principle II/III gate 1; quickstart Scenario B. Depends on
  pinned IG versions (T036).
- [ ] T033 [P] Add `tests/test_discovery.py` exercising input discovery & classification over
  `test/input/` (foundational coverage for T010).
- [ ] T034 Run quickstart.md Scenario A (`python3 process.py --input-dir test/input
  --dry-run --verbose`) and confirm every fixture is classified, `failed = 0`, exit `0`.
- [ ] T035 [P] Create `known-validation-issues.md` at repo root (stub if no issues yet) and
  wire CI (T031) / `scripts/validate.sh` (T032) to filter ONLY its specific documented error
  patterns — never broad wildcards; any unmatched error fails the build (constitution
  Principle III: Known Upstream Validation Issues).
- [ ] T036 Pin the `TODO_PIN` IG versions in `config.example.json` (`hl7.fhir.us.ecr`,
  `hl7.fhir.us.core`, `hl7.fhir.us.davinci-deqm`) to the versions the target deployment
  confirms; `aphl.chronic-ds` stays `0.0.002` (fixtures). BLOCKS a green conformance gate
  (T032) — constitution Principle II IG Version Tracking + deferred TODO(ECR_IG_VERSION).
  If versions are not yet confirmable, record the blocker and keep `TODO_PIN` explicit.
- [ ] T037 Add an SC-008 re-run verification (quickstart Scenario D): run the processor
  twice over the same input against a test FHIR server and assert the server resource count
  is identical after run 2, with only provenance tags + server-managed
  `meta.lastUpdated`/`versionId` changed (FR-016, SC-008).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phase 3–5)**: All depend on Foundational.
  - US1 (P1) and US2 (P1) are both MVP-priority. US2's stamping integrates into US1's
    submission pipeline (T026 calls into T015/T016), so if built by one developer, do US1
    then US2. They remain independently testable.
  - US3 (P2) depends only on Foundational (extends config load T009); independent of US1/US2.
- **Polish (Phase 6)**: Depends on the desired user stories being complete.
  - T032 (conformance gate) depends on T036 (pinned IG versions).
  - T016 real (non-dry-run) submission depends on a passing T032.
  - T035 (known-issues filtering) extends T031 (CI) and T032 (validate script).
  - T037 (re-run/SC-008 check) depends on US1 + US2 being complete.

### User Story Dependencies

- **US1 (P1)**: Foundational only. No dependency on other stories.
- **US2 (P1)**: Foundational only to be testable; its T026 integration step touches the US1
  pipeline. Pure-logic stamping (T023–T025) is independent.
- **US3 (P2)**: Foundational only. Independent of US1/US2.

### Within Each User Story

- Tests (T012/T013, T021/T022, T027) written first and FAIL before implementation.
- Auth/transform before submission (US1: T014/T015 → T016).
- Version/timestamp/stamp before pipeline insertion (US2: T023/T024/T025 → T026).
- Validation before path-precedence (US3: T028 → T029).

### Parallel Opportunities

- Setup: T003, T004, T005 in parallel (different files).
- Foundational: all touch `process.py` → sequential (T006 → T011).
- Tests within a story run in parallel: [T012, T013] · [T021, T022] · [T027].
- Implementation tasks within a story edit `process.py` → sequential.
- Polish: T030, T031, T033 in parallel (different files); T032/T034 after a runnable processor.

---

## Parallel Example: User Story 1

```bash
# Launch US1's unit tests together (different files, no dependencies):
Task: "Unit test for collection→transaction transform in tests/test_transform.py"
Task: "Unit test for (resourceType,id) collision guard in tests/test_collision.py"

# Implementation then proceeds sequentially in process.py:
#   T014 auth → T015 transform → T016 submission → T017 collision → T018 refs
#   → T019 outcomes → T020 dry-run/mirror
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL — blocks all stories)
3. Phase 3 US1 → **STOP and VALIDATE**: run against `test/input` pointed at a test FHIR
   server; confirm resources persist and the summary/exit status are correct.
4. Demo: bundles flow from local files to the server (the core reason the tool exists).

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → persistence works (MVP).
3. US2 → provenance tags make runs searchable/auditable (the user's hard requirement).
4. US3 → safe, code-free configuration for real deployments.
5. Polish → README, CI, and the dual-gate conformance + server validation.

### Parallel Team Strategy

After Foundational, US1 and US3 can be built by different developers immediately; US2's
pure-logic functions (T023–T025) in parallel too, with T026 integrated once US1's pipeline
(T015/T016) exists.

---

## Notes

- [P] = different files, no dependencies. Most `process.py` tasks are NOT [P] (same file).
- Verify each story's tests fail before implementing it.
- Commit after each task or logical group; keep `config.json` and secrets out of VCS.
- Stop at any checkpoint to validate a story independently against `test/input/`.
