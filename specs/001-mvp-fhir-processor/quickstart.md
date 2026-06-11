# Quickstart & Validation Guide: MVP eCR FHIR Processor

Runnable scenarios that prove the feature works end-to-end. Implementation details live
in `tasks.md`; resource shapes in the IGs; interfaces in [`contracts/`](./contracts/).

## Prerequisites

- Python 3 (standard library only — no `pip install`).
- A git checkout (version is derived via `git describe`).
- For real submission: a reachable FHIR R4 server + OAuth2 client-credentials.
- For the conformance gate: Java + `validator_cli.jar` (in repo root).

## Setup

```bash
cp config.example.json config.json
# Edit config.json: set server.base_url, token_endpoint, client_id, client_secret.
# config.json is git-ignored (constitution: Secret Protection) — never commit it.
```

## Scenario A — Dry run over the test fixtures (no server needed)

Proves discovery, classification, stamping, the per-resource PUT plan (independent, no
transaction), and the eICR Composition promotion.

```bash
python3 process.py --input-dir test/input --dry-run --verbose
```

**Expected**: RunSummary lists every fixture file with its `kind`
(`collection-bundle` / `measure-report` / `message-bundle`), the per-resource `PUT`s it
would issue (one per contained resource — no `transaction` bundle), a promoted
`PUT .../Composition/<id>` for each in-population message bundle, and resource counts;
`failed = 0`; exit `0`. No network calls.

## Scenario B — Conformance gate (HL7 Reference Validator)

Per constitution Principle III (dual-gate, gate 1). Validate the stamped/transformed
bundles the processor would submit.

```bash
# Processor writes the would-be submissions to output/ during a dry run:
python3 process.py --input-dir test/input --dry-run --output-dir output
# Delta gate: validates output with the pinned IG set (config.ig_versions) and fails only
# on validator errors introduced vs. the committed source baseline.
scripts/validate.sh "output/**/*.json" config.example.json
```

**Expected**: `PASS` — zero project-introduced errors vs. `test/conformance-baseline.sigs`
(warnings OK; the supplier's inherent source errors are the baseline, and documented known
issues are filtered per `known-validation-issues.md`). Regenerate the baseline with
`scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json` when the
fixtures or pinned IG versions change.

## Scenario C — Persist to a FHIR server (gate 2)

Proves end-to-end persistence + update-in-place.

```bash
python3 process.py --input-dir test/input --config config.json
```

**Expected**: each bundle submitted; RunSummary shows `succeeded` counts, `failed = 0`,
exit `0`. Verify on the server:

```bash
# Everything this run wrote (per contract: provenance-metadata.md)
curl "$BASE/Patient?_tag=https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by|ecr-fhir-processor"
# A relative reference resolves (FR-017): the Patient referenced by a Condition exists
curl "$BASE/Condition/<id>" ; curl "$BASE/Patient/<referenced-id>"
```

## Scenario D — Re-run = update-in-place, no duplicates (SC-008)

```bash
python3 process.py --input-dir test/input --config config.json   # run 1
# record server resource count
python3 process.py --input-dir test/input --config config.json   # run 2
# recount
```

**Expected**: identical resource count after run 2; only provenance tags + server
`meta.lastUpdated`/`versionId` changed on the touched resources.

## Scenario E — Failure modes report loudly (SC-006)

```bash
# Missing credential:
python3 process.py --config /tmp/bad-config.json        # → non-zero, names the field
# Unreachable server:
python3 process.py --config config.json                 # (server down) → non-zero, ERROR logged
```

**Expected**: clear message, non-zero exit, nothing falsely reported as persisted.

## Scenario F — Provenance filtering (SC-002 / SC-003 / US2-5)

After Scenario C, run the three `_tag` queries in
[`contracts/provenance-metadata.md`](./contracts/provenance-metadata.md) and confirm:
filter by `processed-by` returns only this processor's resources; filter by `processed-on`
narrows to one run; filter by `source-file` traces resources to their origin file.

## Scenario G — Independent per-type persistence: defer MeasureReports (constitution Principle V, D10)

Proves failure isolation and the separate-run workflow for a resource type the server
currently rejects (the test MeasureReports fail Aidbox validation).

```bash
# 1. Land everything EXCEPT MeasureReports (conformant resources persist independently):
python3 process.py --input-dir test/input --config config.json --skip-types MeasureReport
# 2. Relax the Aidbox MeasureReport validation profile (may require a server restart).
# 3. Land just the MeasureReports in a separate run:
python3 process.py --input-dir test/input --config config.json --only-types MeasureReport
```

**Expected**: Run 1 — all non-MeasureReport resources `succeeded`, MeasureReports `skipped`,
exit `0`; one rejected resource never blocks its siblings. Run 2 — MeasureReports
`succeeded`; the resources from run 1 are untouched (idempotent PUT-by-id; no duplicates, no
rollback).

## Scenario H — eICR Composition is first-class & queryable (constitution Principle VI, D2b)

```bash
python3 process.py --input-dir test/input --config config.json
# The promoted Composition exists independently and is analytics-queryable:
curl "$BASE/Composition/<eicr-composition-id>"
curl "$BASE/Composition?_tag=https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by|ecr-fhir-processor"
```

**Expected**: the in-population eICR `Composition` is retrievable as its own resource (not
only inside the stored message Bundle); the authoritative collection-Bundle clinical
resources are unchanged by the promotion (no lower-fidelity overwrite).

## Validation → Success Criteria map

| Scenario | Validates |
|----------|-----------|
| A | FR-001/003, per-resource transform + Composition-promotion plan |
| B | Constitution III gate 1 (conformance) |
| C | SC-001, FR-002/009, FR-017 (refs resolve) |
| D | SC-008, FR-016 |
| E | SC-006, FR-010/012/014 |
| F | SC-002/003/004, FR-004/005, US2-5 |
| G | Constitution Principle V — independent, isolated, re-runnable per-type persistence (D10) |
| H | Constitution Principle VI — analytics-ready first-class Composition (D2b) |
