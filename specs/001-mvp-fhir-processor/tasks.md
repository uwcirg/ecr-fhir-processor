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

> ## ⚠️ Refresh note (constitution v1.1.0 — re-generated 2026-06-12)
>
> The prior `tasks.md` reflected the **superseded atomic-`transaction` model**. The amended
> constitution (Principles **V** independent persistence / no global transaction, and **VI**
> analytics-ready granularity) and the new spec requirements **FR-020…FR-023** + **User
> Story 4** replace it with:
>
> 1. **Independent per-resource `PUT`s** for collection-Bundle contents — **no** atomic
>    `transaction` Bundle (FR-020, FR-022, research D2). Failures isolate per resource.
> 2. **Promote the nested eICR `Composition`** to a first-class resource (FR-021, D2b).
> 3. **Selectable per-type persistence** via `--only-types` / `--skip-types` so a rejected
>    type (the test MeasureReports) lands in a separate idempotent run (FR-023, D10).
>
> Tasks for work already completed against the old model that **remains valid** stay `[X]`.
> Tasks whose implementation must **change** (the transaction→independent-PUT migration) and
> all **net-new** work (Composition promotion, type filters, US4) are reset to `[ ]`.
> The current `process.py` still contains `transform_collection_to_transaction` /
> `submit_transaction` — those are the migration targets in Phase 3 / Phase 5.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1, US2, US3, US4 (maps to the user stories in spec.md). Setup /
  Foundational / Polish tasks carry no story label.
- All paths are relative to the repository root.

## Path Conventions

- Single-project CLI: `process.py`, `config.example.json` at repo root; `tests/` at repo
  root; real data in `input/`/`output/`/`log/`; dev fixtures in `test/input/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and the reconciled config template.

- [X] T001 Create the single-file skeleton `process.py` at repo root: module docstring,
  `def main(argv=None) -> int:` returning an exit code, and the
  `if __name__ == "__main__": sys.exit(main())` guard (constitution: Single-File Simplicity).
- [X] T002 Reconcile `config.example.json` at repo root per research.md D7: remove
  `software.version`, add the `ig_versions{}` block and the
  `paths{input_dir,output_dir,log_dir}` block; keep `software.name`/`identifier_*` and
  `server.*` placeholders (`YOUR_*`).
- [X] T003 [P] Create `tests/` package at repo root with `tests/__init__.py`; tests read
  fixtures from the existing `test/input/` tree.
- [X] T004 [P] Verify/extend `.gitignore` at repo root to cover `config.json`, `*.secret*`,
  `.env`, `/output/`, and `/log/` (constitution: Secret Protection MUST-include set).
- [X] T005 [P] Add lint configuration (`.ruff.toml`) at repo root targeting Python 3
  stdlib-only style (constitution: Development Workflow).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core scaffolding in `process.py` that EVERY user story depends on (CLI,
logging, constants, config load, discovery/classification, run summary).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. All tasks edit
`process.py` and are sequential.

- [X] T006 Implement dual logging in `process.py` (Python `logging`): console handler +
  timestamped file handler writing `log/ecr-fhir-processor_{YYYY-MM-DDtHHMMSS}.log`;
  `--verbose` raises console to DEBUG (FR-013, D9).
- [X] T007 Define canonical constants in `process.py`: provenance base
  `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem` with `processed-by`/`processed-on`/
  `source-file` systems, processor identity `ecr-fhir-processor`, and IG-version constants
  sourced from `config.ig_versions` (Principle II; provenance-metadata contract).
- [X] T008 Implement the base `argparse` CLI in `process.py` (`--config`, `--input-dir`,
  `--measure`, `--output-dir`, `--no-output-mirror`, `--dry-run`, `--log-dir`, `--verbose`)
  with the documented defaults (cli contract). NOTE: `--only-types`/`--skip-types` are added
  in Phase 5 (US4 / T030).
- [X] T009 Implement config loading in `process.py`: read the JSON config into a `RunConfig`
  structure (software/server/ig_versions/paths) with CLI overrides for paths/measure
  (data-model RunConfig; cli contract). NOTE: fail-fast *validation* is US3.
- [X] T010 Implement input discovery & classification in `process.py`: recursively find
  `*.json` under the input root, build `InputFile`/`ScenarioFolder` with `measure`,
  `population`, and `kind` (`collection-bundle` | `measure-report` | `message-bundle` |
  `unknown`); empty input → exit 0 "nothing processed" (FR-001, data-model, cli contract).
- [X] T011 Implement the `RunSummary` accumulator in `process.py`: per-file/per-resource
  outcomes (`filename, kind, action, resource_count, status, detail`), aggregate counts
  (`read/submitted/succeeded/failed/skipped`), final summary report, and exit code
  `0` iff `failed == 0` (FR-014, D8, data-model RunSummary).

**Checkpoint**: Foundation ready — `process.py` discovers/classifies input and reports a
summary. User stories can now begin.

---

## Phase 3: User Story 1 - Process and persist eCR bundles to a FHIR server (Priority: P1) 🎯 MVP

**Goal**: Read every bundle in the input set and persist its resources to the OAuth2-secured
FHIR server using **independent, update-in-place per-resource `PUT`-by-id** semantics
(**no atomic `transaction`** — research D2/Principle V), reporting each per-resource outcome.

**Independent Test**: Run `python3 process.py --input-dir test/input` against a reachable
FHIR server; confirm each contained resource from every scenario appears on the server under
`[base]/<Type>/<id>`, references still resolve, and the RunSummary reports per-resource
success/failure with the correct exit status.

### Tests for User Story 1 ⚠️

> Write/refresh these FIRST and confirm they FAIL before implementing.

- [X] T012 [P] [US1] **Rewrite** `tests/test_transform.py` for the **independent per-resource
  PUT plan** (replacing the old transaction assertions): a `collection` Bundle yields one
  planned `PUT <Type>/<retained-id>` per contained `entry.resource`, retains original
  `resource.id` (D1), and produces **no** `transaction` Bundle (FR-020, FR-022, D2,
  fhir-submission contract).
- [X] T013 [P] [US1] Unit test for the `(resourceType, id)` collision guard: differing
  content → error/raise; identical content → allowed dedup, in `tests/test_collision.py`
  (FR-019, D4b).

### Implementation for User Story 1

- [X] T014 [US1] Implement OAuth2 client-credentials auth in `process.py`: POST to
  `server.token_endpoint`, cache bearer token in memory, send `Authorization: Bearer` +
  `Accept: application/fhir+json` on FHIR calls, refresh once on 401 (FR-009, D6,
  fhir-submission contract). Uses `urllib` only.
- [X] T015 [US1] **Replace** `transform_collection_to_transaction` in `process.py` with a
  **per-resource PUT planner**: iterate the `collection` Bundle's `entry[].resource`, retain
  each original `resource.id` (D1), and emit one independent `PUT [base]/<Type>/<id>` unit of
  work per resource — **never** a `transaction` Bundle (FR-020, FR-022, D2, data-model
  transforms).
- [X] T016 [US1] **Replace** `submit_transaction` / per-kind submission in `process.py` with
  **independent per-resource `PUT`s**: each contained resource → `PUT [base]/<Type>/<id>` as
  its own request/outcome; standalone MeasureReport → `PUT [base]/MeasureReport/<id>`; eCR
  message Bundle → `PUT [base]/Bundle/<id>`. A non-atomic `batch` Bundle MAY be used as a
  round-trip optimization (per-entry status read individually); a `transaction` Bundle MUST
  NOT (FR-002/003/016/022, fhir-submission contract). GATE (Principle II): real (non-dry-run)
  submission MUST be preceded by a passing conformance validation over dry-run output (T037).
- [X] T017 [US1] Implement the within-run `(resourceType, id)` collision detector in
  `process.py`: the seen-set tracks ONLY top-level persisted resources (the per-resource PUTs
  + standalone PUTs), NOT resources nested inside a message Bundle — so the fixed
  `eicr-report-*` document-Bundle id (D4b) never enters the set. Differing content → log
  ERROR + reflect in exit status; identical content → DEBUG/INFO dedup (FR-019, D4b).
- [X] T018 [US1] Implement reference handling in `process.py`: do NOT rewrite references;
  log WARNING on absolute references to a non-target host; relative refs left intact so
  they resolve via retained ids (FR-017, D3).
- [X] T019 [US1] **Rework** submission-outcome wiring in `process.py` for **per-resource
  isolation**: a non-2xx on any resource's `PUT` → log ERROR including the server
  `OperationOutcome`, count that **resource** `failed` (never `succeeded`), and **continue
  with the siblings** — no transaction whose rejection rolls back or blocks the rest
  (FR-012, FR-022, D8, fhir-submission SUB-3). With a `batch`, read outcomes per entry.
- [X] T020 [US1] **Update** `--dry-run` and the output mirror in `process.py` to the new plan:
  dry-run runs all transforms but performs no token request/submission and logs the would-be
  **per-resource PUTs** (one line per resource, plus the promoted Composition PUT from US4);
  otherwise optionally mirror submitted JSON (pretty-printed) to
  `output/{measure}/{YYYY-MM-DD}/` unless `--no-output-mirror` (D9, cli + fhir-submission
  SUB-5). Replaces the old "would POST transaction" logging.

**Checkpoint**: US1 is fully functional — each contained resource persists independently to
the server with update-in-place semantics and per-resource reporting. This is the MVP. Before
persisting to a *real* server, run the conformance gate (T037) over dry-run output.

---

## Phase 4: User Story 2 - Stamp filterable processing metadata onto resources (Priority: P1)

**Goal**: Before submission, stamp every persisted resource (and message-Bundle `meta`, and
the promoted Composition) with searchable provenance: processor identity, git-derived version,
run-constant timestamp, and source filename — retrievable via FHIR `_tag` search.

**Independent Test**: After a run, `GET [base]/Patient?_tag=<BASE>/processed-by|ecr-fhir-processor`
returns only this processor's resources; a `processed-on` `_tag` filter narrows to one run;
a `source-file` `_tag` traces resources to their origin file.

### Tests for User Story 2 ⚠️

- [X] T021 [P] [US2] Unit test for stamping in `tests/test_provenance.py`: three `meta.tag[]`
  entries (processed-by+version, processed-on, source-file) + `meta.source`; idempotent
  re-stamp replaces own tags by `system` (INV-2); preserves pre-existing tags/`profile`
  (INV-3) (D4, provenance-metadata contract).
- [X] T022 [P] [US2] Unit test for git version derivation + `unknown` fallback in
  `tests/test_version.py` (D5, FR-006).

### Implementation for User Story 2

- [X] T023 [US2] Implement git version derivation in `process.py`:
  `git describe --tags --always --dirty` via `subprocess`; fallback literal `unknown` with a
  WARNING when git is unavailable (FR-006, D5).
- [X] T024 [US2] Implement the run-constant processing timestamp in `process.py`: ISO-8601
  instant with timezone offset, computed once per run and reused for every resource
  (FR-007, INV-1/INV-4).
- [X] T025 [US2] Implement `stamp(resource_meta)` / `stamp_resource(resource)` in
  `process.py`: add the three `meta.tag[]` entries + `meta.source`; additive and idempotent
  (replace own tags by `system`, never append duplicates); never alter clinical content
  (FR-004/005/015, D4, provenance contract).
- [X] T026 [US2] **Re-point** stamping into the new pipeline in `process.py`: stamp **each
  contained resource** (per-resource PUT, US1 T015/T016), the standalone MeasureReport, the
  message Bundle's own `meta`, **and the promoted eICR Composition** (US4 T029) — before
  submission (FR-004; integrates with US1 + US4). Replaces the old "stamp each transaction
  entry" wiring.

**Checkpoint**: US1 + US2 both work — every persisted resource is searchable by provenance tags.

---

## Phase 5: User Story 4 - Make persisted eCR content queryable for downstream analytics (Priority: P1)

**Goal**: Guarantee analytics-ready granularity (constitution Principle VI): each contained
clinical resource is first-class (delivered by US1's per-resource PUTs), the eICR
**Composition** is promoted to first-class, and resource types persist **independently** so a
rejected type never blocks the others and can be landed in a separate idempotent run.

**Independent Test**: After a run, query the server for an individual contained resource
(e.g., a specific Observation) and, for an in-population scenario, the eICR Composition by id
— each returns standalone. Run with `--skip-types MeasureReport`, confirm MeasureReports are
`skipped` (not failed) and every other type persists; a later `--only-types MeasureReport`
run adds them with no duplicates (quickstart Scenarios G & H).

### Tests for User Story 4 ⚠️

> Write these FIRST and confirm they FAIL before implementing.

- [X] T027 [P] [US4] Unit test for **eICR Composition promotion** in
  `tests/test_promotion.py`: from a message Bundle, extract the `Composition` nested in the
  `entry(content Bundle, type=document)`, plan `PUT [base]/Composition/<per-case GUID id>`,
  and assert **only** the Composition is promoted (no other nested clinical resources); a
  Composition reference that does not resolve to a persisted resource is WARNING-logged, not
  mutated (FR-021, D2b, D3, fhir-submission AC-5).
- [X] T028 [P] [US4] Unit test for **TypeFilter selection** in `tests/test_typefilter.py`:
  `--only-types` keeps only the listed FHIR resourceTypes; `--skip-types` excludes them;
  excluded resources are counted `skipped` (not `failed`); the `measure-report` kind alias is
  accepted; `--only-types`/`--skip-types` are mutually exclusive (FR-023, D10, cli contract).

### Implementation for User Story 4

- [X] T029 [US4] Implement **eICR Composition promotion** in `process.py` (FR-021, D2b):
  when processing a message Bundle, locate the nested `type=document` content Bundle, extract
  its `Composition`, stamp it (US2), and `PUT [base]/Composition/<id>` as an independent
  first-class resource **in addition to** persisting the message Bundle whole. Promote **only**
  the Composition — never re-persist the eICR's other lower-fidelity nested clinical copies
  over the authoritative collection-Bundle resources; the `MessageHeader` stays nested. WARN
  on any unresolved Composition reference (D3); do not mutate it.
- [X] T030 [US4] Implement the **TypeFilter** + CLI flags in `process.py` (FR-023, D10):
  add `--only-types` / `--skip-types` (comma-separated FHIR resourceTypes; accept the
  `measure-report` kind alias; mutually exclusive) to the parser (extends T008); gate which
  resourceTypes are PUT this run; resources excluded by the filter are counted `skipped`
  (distinct from `failed`) in the RunSummary (D8). Default (neither flag): persist all.
- [ ] T031 [US4] **Verify analytics queryability & independent-type persistence** (FR-020/021/
  022/023; quickstart Scenarios G & H, fhir-submission AC-4/AC-5): with a runnable processor,
  confirm (a) each contained resource and the promoted Composition are individually
  retrievable as first-class resources; (b) a run that rejects one type still persists the
  others; (c) `--skip-types MeasureReport` then `--only-types MeasureReport` lands the deferred
  type idempotently (no duplicates, no rollback), with collection-Bundle resources unchanged
  by the Composition promotion. Record results (and any external-server blocker) in the run
  notes.
  > **BLOCKED (external server).** The retrieval-from-server assertions need a reachable
  > test FHIR/Aidbox server, which is not available in this environment. The deterministic
  > precursors are verified locally: the dry-run plans one independent `PUT [Type]/<id>` per
  > contained resource **plus** a promoted `PUT /Composition/<id>` for each in-population
  > message bundle (50 PUTs over 13 files, `failed=0`, exit `0`); `--skip-types MeasureReport`
  > counts the 5 MeasureReports `skipped` while persisting the other 45; `--only-types
  > MeasureReport` inverts that (5 submitted / 45 skipped); and the conformance delta gate
  > over the would-be submissions introduces **zero** new validator errors vs. the source
  > baseline. The live GET-by-id / resource-count checks remain to be run once a server is
  > reachable.

**Checkpoint**: US1 + US2 + US4 work — contained resources and the eICR Composition are
first-class & queryable, and types persist independently with isolated failures.

---

## Phase 6: User Story 3 - Configure the run without editing code (Priority: P2)

**Goal**: An operator copies `config.example.json`, fills in server/credentials, and runs the
processor with no source edits; misconfiguration fails fast and loudly.

**Independent Test**: Copy the example config, populate it, run; confirm it authenticates
using only config values. A config missing a required field, or left at `YOUR_*`
placeholders, fails fast with a message naming the field and a non-zero exit.

### Tests for User Story 3 ⚠️

- [X] T032 [P] [US3] Unit test for config validation in `tests/test_config.py`: missing/empty
  required `server.*` field → error naming the field; values still equal to `YOUR_*`
  placeholders → rejected (FR-010, D7, cli contract).

### Implementation for User Story 3

- [X] T033 [US3] Implement fail-fast config validation in `process.py`: require non-empty
  `server.base_url`/`token_endpoint`/`client_id`/`client_secret` (except under `--dry-run`);
  reject `YOUR_*` placeholder values; emit a field-specific message and non-zero exit
  (FR-010, US3 scenarios 2 & 3, D7, cli contract).
- [X] T034 [US3] Implement path/measure precedence in `process.py`: CLI flags override
  `config.paths` defaults (`input`/`output`/`log`); `--measure` restricts to one measure
  folder (cli contract, US3 scenario 1).

**Checkpoint**: All four stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, CI, and the constitution's dual-gate validation.

- [X] T035 [P] **Update** `README.md` at repo root for the v1.1.0 model: independent
  per-resource persistence (no transaction), the promoted eICR Composition, and the new
  `--only-types`/`--skip-types` per-type-run workflow, alongside the existing CLI/setup/
  provenance recipes (constitution: README as Living Documentation).
- [X] T036 [P] **Update** CI workflow `.github/workflows/ci.yml` to run the new/rewritten
  tests (`test_promotion.py`, `test_typefilter.py`, rewritten `test_transform.py`) via
  `python3 -m unittest`, keep lint (ruff), the dry-run over `test/input`, and the secret scan
  (constitution: CI Pipeline; Dual-Gate prep).
- [X] T037 Conformance-gate script `scripts/validate.sh` invoking `java -jar validator_cli.jar`
  with versioned `-ig` packages from `config.ig_versions`; zero project-introduced errors =
  pass; baseline/known-issue filtering. Invoked by CI (T036) and run over dry-run output
  BEFORE real submission (T016 gate) — Principle II/III gate 1; quickstart Scenario B.
  Depends on the committed source baseline (T043).
- [X] T043 Generate & commit the conformance **source baseline** `test/conformance-baseline.sigs`
  via `scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json`
  (the location/UUID-independent error signatures of the *pre-transform* fixtures under the
  pinned IG set + validator version). The delta gate (T037) fails only on signatures **absent**
  from this baseline and unmatched by a `known-validation-issues.md` `PATTERN:` (Principle III).
  Regenerate whenever the fixtures, pinned IG versions (T041), or `FHIR_VALIDATOR_VERSION`
  change. (Artifact present; mechanism in `validate.sh` `--update-baseline`.)
- [X] T038 [P] `tests/test_discovery.py` exercising input discovery & classification over
  `test/input/` (foundational coverage for T010).
- [X] T039 **Re-run** quickstart Scenario A (`python3 process.py --input-dir test/input
  --dry-run --verbose`) after the Phase 3/5 migration and confirm every fixture is classified,
  the dry-run prints **per-resource PUTs** (not a transaction) plus a promoted
  `PUT .../Composition/<id>` for each in-population message bundle, `failed = 0`, exit `0`.
- [X] T040 [P] `known-validation-issues.md` at repo root wired into CI (T036) /
  `scripts/validate.sh` (T037) to filter ONLY its specific documented error patterns — never
  broad wildcards; any unmatched error fails the build (constitution Principle III).
- [X] T041 Pin the `ig_versions` in `config.example.json` to confirmed versions
  (`hl7.fhir.us.core` 6.1.0, `hl7.fhir.us.ecr` 2.1.2, `davinci-deqm` 5.0.0, etc.); BLOCKS a
  green conformance gate (T037) — Principle II IG Version Tracking.
- [X] T042 [US4-adjacent] Extend `tests/test_rerun.py` for the v1.1.0 model: assert
  per-resource PUT targets are identical across two runs, provenance tags do not accumulate,
  and (deferred type) a `--only-types`/`--skip-types` split leaves already-persisted resources
  untouched (FR-016/022/023, SC-008/SC-011). The full live-server resource-count assertion
  (quickstart Scenario D) remains an external-server step.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phase 3–6)**: All depend on Foundational. Priority order is P1 (US1, US2,
  US4) before P2 (US3).
  - **US1 (P1)** delivers the per-resource persistence mechanism (independent PUTs).
  - **US2 (P1)** stamping integrates into the US1 + US4 pipeline (T026).
  - **US4 (P1)** Composition promotion (T029) and stamping depend on US1's pipeline and US2's
    stamp; the TypeFilter (T030) depends on the per-resource outcome accounting (US1 T019).
  - **US3 (P2)** depends only on Foundational; independent of US1/US2/US4.
- **Polish (Phase 7)**: Depends on the desired user stories being complete.
  - T037 (conformance gate) depends on pinned IG versions (T041, done) and the committed
    source baseline (T043, done).
  - T016 real (non-dry-run) submission depends on a passing T037.
  - T036 (CI) depends on the new tests (T012, T027, T028) existing.
  - T039/T042 depend on the Phase 3/5 migration being complete.

### Within Each User Story

- Tests (T012, T027/T028) written/refreshed first and FAIL before implementation.
- US1: auth/PUT-planner before submission before outcome wiring (T014/T015 → T016 → T019).
- US2: version/timestamp/stamp before pipeline insertion (T023/T024/T025 → T026).
- US4: Composition promotion + TypeFilter before queryability verification (T029/T030 → T031).
- US3: validation before path-precedence (T033 → T034).

### Parallel Opportunities

- Setup: T003, T004, T005 in parallel (different files).
- Foundational: all touch `process.py` → sequential (T006 → T011).
- Tests within/across stories run in parallel: [T012] · [T013] · [T021, T022] · [T027, T028] ·
  [T032] (different `tests/*.py` files).
- Implementation tasks within a story edit `process.py` → sequential.
- Polish: T035, T036, T038, T040 in parallel (different files); T039/T031 after a runnable
  processor.

---

## Parallel Example: User Story 4

```bash
# Launch US4's unit tests together (different files, no dependencies):
Task: "Unit test for eICR Composition promotion in tests/test_promotion.py"
Task: "Unit test for TypeFilter selection in tests/test_typefilter.py"

# Implementation then proceeds sequentially in process.py:
#   T029 Composition promotion → T030 --only-types/--skip-types + skipped accounting
#   → T031 verify queryability + independent per-type persistence (Scenarios G & H)
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 Setup → 2. Phase 2 Foundational (CRITICAL — blocks all stories)
3. Phase 3 US1 (migrate transaction → independent per-resource PUTs) → **STOP and VALIDATE**:
   run against `test/input` pointed at a test FHIR server; confirm each contained resource
   persists under its own id, references resolve, and the summary/exit status are correct.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → per-resource persistence works (MVP).
3. US2 → provenance tags make runs searchable/auditable.
4. US4 → Composition promotion + independent per-type persistence make content analytics-ready.
5. US3 → safe, code-free configuration for real deployments.
6. Polish → README, CI, and the dual-gate conformance + server validation.

### Parallel Team Strategy

After Foundational, US1 and US3 can be built by different developers immediately; US2's
pure-logic functions (T023–T025) in parallel too. US4 (T029/T030) integrates once US1's
per-resource pipeline (T015/T016/T019) exists.

---

## Notes

- [P] = different files, no dependencies. Most `process.py` tasks are NOT [P] (same file).
- Verify each story's tests fail before implementing it.
- Commit after each task or logical group; keep `config.json` and secrets out of VCS.
- Stop at any checkpoint to validate a story independently against `test/input/`.

## Implementation status notes (re-generated for constitution v1.1.0, 2026-06-12)

**Already complete and still valid (`[X]`):** all of Phase 1 (Setup) and Phase 2
(Foundational); US1 auth/refs/collision-guard (T013/T014/T017/T018); all of US2 pure logic
(T021–T025); all of US3 (T032–T034); and Polish T037/T038/T040/T041 (conformance script,
discovery test, known-issues filtering, pinned IG versions).

**Outstanding migration & net-new work (`[ ]`) — the v1.1.0 delta:**

1. **US1 transaction → independent per-resource PUTs** (T012, T015, T016, T019, T020):
   `process.py` still defines `transform_collection_to_transaction` and `submit_transaction`;
   replace with per-resource `PUT [base]/<Type>/<id>` (no atomic transaction; failures
   isolated per resource — FR-020/FR-022, D2).
2. **US2 pipeline re-point** (T026): stamp each contained resource + the promoted Composition
   in the new pipeline.
3. **US4 (entirely new, P1)** (T027–T031): eICR Composition promotion (FR-021, D2b); the
   `--only-types`/`--skip-types` TypeFilter with `skipped` accounting (FR-023, D10); and the
   analytics-queryability / independent-per-type verification (quickstart G & H).
4. **Polish refresh** (T035, T036, T039, T042): README + CI updated for the new model; re-run
   dry-run Scenario A; extend the re-run/idempotency test.

**External blockers (unchanged):** the live-server steps (T031 queryability, T042 Scenario D
resource-count) need a reachable test FHIR server; the test MeasureReports currently fail
Aidbox validation, which is exactly the driving case for the D10 `--skip-types`/`--only-types`
workflow built in T030.
