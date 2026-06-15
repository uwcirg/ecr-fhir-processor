# Quickstart: Patient ViewDefinition + Publish/Materialize

**Feature**: `002-patient-viewdefinition` | **Date**: 2026-06-15

Runnable validation that the Patient view publishes, materializes, and returns one flat row per
first-class Patient. Proves SC-001…SC-006. Details: [contracts/](./contracts/),
[data-model.md](./data-model.md).

## Prerequisites

- Python 3 (stdlib only — no install step; Principle I).
- `config.json` (copy `config.example.json`) with real `server.{base_url, token_endpoint,
  client_id, client_secret}` for an **Aidbox ≥ 2508** target (research.md R3; `$materialize`
  requires 2508+).
- First-class `Patient/<id>` resources already persisted on that server — produced by the
  existing processor (`python process.py ...`, feature 001). For a clean count, note the number
  of distinct Patients (call it **N**).
- The checked-in `viewdefinitions/patient.ViewDefinition.json`.

## 1. Dry run (no network) — verify discovery + config

```bash
python publish_views.py --dry-run --verbose
```

**Expect**: the Patient ViewDefinition file is discovered and reported as a planned
`PUT … /ViewDefinition/patient` + `POST … /$materialize`; no server contact. With a missing/
placeholder `config.json` and without `--dry-run`, the step instead **fails at startup** with a
clear "Missing required config field…" message (FR-007).

## 2. Publish + materialize

```bash
python publish_views.py --config config.json --verbose
```

**Expect** (FR-004, FR-009):

```
ViewDefinition: patient
  publish:     OK (200|201)
  materialize: OK  -> sof.patient_view (view)
--- 1 view: 1 published, 1 materialized, 0 failed ---
```

Exit status `0`. A timestamped audit log is written under `log/`.

## 3. Query the materialized view — one row per Patient (SC-001/SC-002/SC-005)

Using any SQL tool against the Aidbox database (or Aidbox's SQL endpoint):

```sql
SELECT count(*) FROM sof.patient_view;          -- expect N
SELECT id, mrn, name_family, name_given, gender, birth_date,
       race_code, ethnicity_code, address_city, address_state, address_postal_code
FROM sof.patient_view
ORDER BY name_family;
```

**Expect**:
- `count(*) = N` — exactly one row per first-class Patient (SC-001).
- Demographic columns reflect the source Patient; columns whose source field is absent are
  **NULL**, never fabricated (SC-005). E.g. the fixture patient *Robinson, Tyler* →
  `mrn=MRN-DM-A15`, `gender=male`, `birth_date=2010-05-12`, `race_code=2106-3`,
  `ethnicity_code=2186-5`, `address_city=Chicago`, `address_state=IL`,
  `address_postal_code=60601`.

## 4. Idempotent re-run (SC-003)

```bash
python publish_views.py --config config.json
```

**Expect**: success again; still **exactly one** `ViewDefinition/patient` on the server (no
duplicate) and one `sof.patient_view`. Re-running does not re-persist or roll back unrelated
resources (FR-005).

## 5. Failure surfacing (SC-004)

Temporarily point `--viewdefinitions-dir` at a copy containing a deliberately non-conformant
ViewDefinition (e.g. an unknown FHIRPath in a column), then run the step.

**Expect**: the server's rejection reason (from the `OperationOutcome`) is logged, the offending
view is reported as failed (publish or materialize, distinguished), the run exits **non-zero**,
and any other valid views are still attempted (FR-008, per-view isolation).

## 6. Empty-set edge case

Against a server with **zero** Patients, run step 2.

**Expect**: publish + materialize both **succeed**, `SELECT count(*) FROM sof.patient_view` = 0,
the step reports zero rows, exit `0` (empty is not a failure).

## 7. Generalization check (SC-006, Story 3 — optional)

Drop a second minimal ViewDefinition file (any resource type) into `viewdefinitions/` and re-run
step 2 with no other change.

**Expect**: both views are published and materialized by the same invocation — confirming the
mechanism is resource-type-agnostic (FR-011).

## Automated checks

- `python -m unittest tests/test_viewdefinition.py` — discovery, `$materialize` body builder,
  outcome→exit-code aggregation, ViewDefinition required-field/JSON checks.
- CI lint (`ruff`) over the new `process.py` code.
