# Quickstart: Validate Aidbox Storability Pre-Processing

Runnable validation that this feature achieves its goal — **every storable resource lands on Aidbox
without fabricating or dropping clinical content** — and that remediation is transparent, auditable,
and idempotent. See [spec.md](./spec.md) for acceptance scenarios, [data-model.md](./data-model.md)
for the outcome model, and the contracts for exact rules.

## Prerequisites

- Python 3 (stdlib only) — no install step (Principle I).
- `java` + `validator_cli.jar` at the repo root (for the HL7 no-regression gate).
- A reachable **Aidbox** with the **FHIR Schema engine enabled** (`BOX_FHIR_SCHEMA_VALIDATION=true`,
  FR-014) and, for the two non-mutating levers:
  - `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true` (enables the Cause-1 per-request header), and
  - `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` **unset** (Cause 3 binding validation off).
- `config.json` copied from `config.example.json` with real `server` credentials and
  **`"validation_skip": ["reference"]`** (Cause 1 lever).

## 1. Fast local checks (no server)

```bash
ruff check .
python -m unittest tests.test_stratum_prune tests.test_exit_codes tests.test_summary -v
```

Expected: pruning invariants/idempotency/nested-walk/WARNING-with-counts pass; the three-state exit
code and per-type stored/remediated/deferred counts pass.

## 2. Transform on the write path, output == submitted bytes (FR-008)

```bash
python process.py --dry-run --input-dir test/input --output-dir output
```

Expected: for each MeasureReport (standalone and nested in a message Bundle) that had a
`population`-only stratum, a **WARNING** logs the removal **with the population counts it carried**
(FR-006). The mirrored files under `output/{measure}/{date}/` are the transformed resources — the same
bytes that will be PUT (inspect one MeasureReport to confirm the malformed stratum is gone and nothing
else changed). `test/input/` is untouched (FR-008, Principle III).

## 3. HL7 no-regression gate (FR-009, SC-005)

```bash
scripts/validate.sh "output/**/*.json" config.json
```

Expected: **zero new error signatures** vs. `test/conformance-baseline.sigs`. If the prune legitimately
*removed* a signature, regenerate the baseline (never to admit a new one) and commit it
([[conformance-gate-baseline-stale]]):

```bash
scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json
```

## 4. End-to-end persistence against a clean Aidbox (SC-001)

```bash
python process.py --input-dir test/input   # uses config.json
```

Expected (US1 + US2 + US3):

- The reference-skip header clears Cause 1 (Observation ×2, MedicationRequest ×1 + their message
  Bundles) with **no content change**.
- The stratum prune clears Cause 2 for **every** MeasureReport (standalone + nested), so the message
  Bundles are accepted whole; Cause 3 is silent because no terminology server is configured.
- The run stores the **full storable set** (targeting **50/50** for the current sample) and prints a
  **per-resource-type summary** of stored / remediated / deferred (FR-012, SC-006).
- **Exit code `0`** for the current sample (all stored, `remediated > 0`, `deferred == 0`). If a future
  input can only be stored by fabrication, that type is **deferred** and the run exits with the
  distinct **completed-with-deferrals** code — never the unexpected-error code (FR-012).

## 5. Idempotent re-run (FR-010, SC-004)

```bash
python process.py --input-dir test/input   # run a second time
```

Expected: no duplicate resources and no content diffs for already-stored resources (retained-id PUT
update-in-place); exit `0`.

## 6. Auditability (FR-013, SC-003)

- Confirm the run's timestamped log under `log/` records every applied lever/transform at WARNING+.
- Confirm `known-validation-issues.md` → "Aidbox ingestion-time validation" documents, per Cause, the
  chosen lever/transform (reference-skip header; box-side terminology; stratum prune) — and no longer
  frames `mrp-2` as out of scope or suggests `BOX_FHIR_SCHEMA_VALIDATION=false`.

## Negative / edge checks

- **Reference-skip disabled** (`validation_skip: []` or box flag off): Cause 1 resurfaces as a
  per-resource failure surfaced in the summary — not masked (spec Edge Case).
- **Terminology server configured**: Cause 3 resurfaces (out of scope here; would need its own
  remediation).
- **Undocumented Aidbox rejection**: reported as `failed` and drives the **unexpected-error** exit
  code — never auto-suppressed.
