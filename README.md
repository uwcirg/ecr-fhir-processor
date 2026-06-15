# ecr-fhir-processor

Processes FHIR R4 electronic Case Reporting (eCR) resources used for chronic-disease
surveillance and persists them to an OAuth2-secured target FHIR server using
**update-in-place** semantics. Covers three CMS quality measures:

1. **CMS122** — Diabetes HbA1c Poor Control (≥9%) — folder `poor-diabetic-control`
2. **CMS165** — Controlling High Blood Pressure — folder `controllable-bp`
3. **CMS2** — Depression Screening — folder `depression-screening` *(in scope; no
   fixtures yet)*

Originally developed for Washington State Department of Health's TRAX "Translational
Repository and Analytics Exchange" project.

## What it does

- Recursively discovers `*.json` under the input tree, organized by
  `{measure}/{population}/{scenario}/`, and classifies each file as a **collection
  bundle**, **MeasureReport**, **eCR message bundle**, or **unknown** (skipped). See
  [`docs/input-data.md`](docs/input-data.md) for how the input files are organized and
  how the files within a scenario relate.
- Stamps every persisted resource (and a message Bundle's own `meta`) with searchable
  provenance metadata, then persists it as **independent, first-class resources** —
  there is **no atomic `transaction`** binding a scenario together, so failures isolate
  per resource and resource types persist independently:
  - **collection** Bundles are split into one **independent `PUT [Type]/<id>`** per
    contained resource (ids retained, update-in-place). A non-atomic `batch` Bundle is an
    allowed round-trip optimization; a `transaction` Bundle is **never** used.
  - standalone **MeasureReport**s and **message** Bundles are `PUT` under their retained
    ids.
  - for in-population scenarios the nested eICR **`Composition`** is **promoted** to a
    first-class resource (`PUT /Composition/<id>`) in addition to persisting the message
    Bundle whole — making it queryable for downstream SQL-on-FHIR analytics. Only the
    Composition is promoted (no lower-fidelity overwrite of the authoritative
    collection-Bundle resources).
- Lets a problem resource type be landed in a **separate idempotent run** via
  `--only-types` / `--skip-types` (e.g. the test MeasureReports that currently fail
  Aidbox validation): persist everything else first, then land the deferred type later —
  the second run neither duplicates nor rolls back the first.
- Logs every outcome to the console and a timestamped audit file, and exits non-zero if
  any submission failed (a rejected resource never blocks its siblings).

The runtime uses the **Python 3 standard library only** — no `pip install` required.

## Setup

```bash
cp config.example.json config.json
# Edit config.json: set server.base_url, token_endpoint, client_id, client_secret.
# config.json is git-ignored (never commit real credentials).
```

### Configuration (`config.json`)

| Key | Required | Notes |
|-----|----------|-------|
| `software.name`, `software.identifier_system`, `software.identifier_value` | yes | Provenance identity. |
| `server.base_url`, `server.token_endpoint`, `server.client_id`, `server.client_secret` | yes (unless `--dry-run`) | OAuth2 client-credentials. **Secrets — never commit.** |
| `ig_versions{}` | recommended | IG → version for the conformance gate, mirroring the test-data supplier's pinned set (`hl7.fhir.us.core`, `hl7.fhir.us.qicore`, `hl7.fhir.us.cqfmeasures`, `hl7.fhir.us.davinci-deqm`, `hl7.fhir.us.ecr`, `hl7.fhir.us.ph-library`). |
| `paths{input_dir,output_dir,log_dir}` | optional | Defaults `input`/`output`/`log`. |

> The software **version is not a config field** — it is derived at runtime from
> `git describe --tags --always --dirty` (falls back to `unknown` when git is
> unavailable).

## Usage

```text
python3 process.py [--config PATH] [--input-dir PATH] [--measure NAME]
                   [--only-types LIST] [--skip-types LIST]
                   [--output-dir PATH] [--no-output-mirror] [--dry-run]
                   [--log-dir PATH] [--verbose]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--config` | `config.json` | Run config (template: `config.example.json`). |
| `--input-dir` | `config.paths.input_dir` (`input`) | Root of the input tree. |
| `--measure` | all | Restrict to one measure folder. |
| `--only-types` | all | Comma-separated FHIR resourceTypes to persist **exclusively** this run (accepts the `measure-report` kind alias). Mutually exclusive with `--skip-types`. |
| `--skip-types` | none | Comma-separated FHIR resourceTypes to **exclude** this run (excluded resources counted `skipped`). |
| `--output-dir` | `config.paths.output_dir` (`output`) | Submitted-JSON mirror location. |
| `--no-output-mirror` | off | Skip writing the local output mirror. |
| `--dry-run` | off | Discover/classify/stamp/plan but **do not submit** (no server needed). |
| `--log-dir` | `config.paths.log_dir` (`log`) | Audit-log directory. |
| `--verbose` | off | Console DEBUG verbosity (file log is always detailed). |

### Examples

```bash
# Dry run over the test fixtures (no server, no config required):
python3 process.py --input-dir test/input --dry-run --verbose

# Persist to the configured FHIR server:
python3 process.py --input-dir test/input --config config.json

# Independent per-type runs (the test MeasureReports currently fail Aidbox validation):
#   1. land everything except MeasureReports …
python3 process.py --input-dir test/input --skip-types MeasureReport
#   2. … then, after the Aidbox validation profile is relaxed, land just those
#      (idempotent — neither duplicates nor rolls back the first run):
python3 process.py --input-dir test/input --only-types MeasureReport
```

## Analytics views (`publish_views.py`)

Downstream analytics (e.g. a DoH team) query flattened, one-row-per-resource SQL views
rather than raw FHIR. Those views are defined by checked-in **SQL-on-FHIR
`ViewDefinition`** resources under [`viewdefinitions/`](viewdefinitions/) and pushed to
the target Aidbox server by a separate entry point, `publish_views.py`. It is a rare,
schema-change activity (run it to *change* a view), so it is its own script — not a
`process.py` subcommand — sharing the OAuth2 client, config, and logging via
`fhir_common.py`.

For each `*.json` ViewDefinition it discovers, the step `PUT`s it to
`{base}/ViewDefinition/{id}` (update-in-place — re-runs never duplicate) and then `POST`s
`{base}/ViewDefinition/{id}/$materialize`, reporting publish and materialize outcomes
**separately per view**. Any publish or materialize failure is reflected in a non-zero
exit; one view's failure never blocks another.

```bash
python3 publish_views.py [--config config.json]
                         [--viewdefinitions-dir viewdefinitions]
                         [--materialize-type view|materialized-view|table]
                         [--dry-run] [--verbose] [--log-dir log]
```

- `--materialize-type` — the `$materialize` type. Defaults to `server.materialize_type`
  in `config.json`, else **`view`** (an always-current SQL view that reflects live data
  on every read; `materialized-view`/`table` are point-in-time snapshots Aidbox does not
  auto-refresh).
- `--dry-run` — discover and validate the ViewDefinition files and report the planned
  `PUT`/`$materialize` calls **without contacting the server** (no credentials needed).

```bash
# Verify discovery + config without touching the server:
python3 publish_views.py --dry-run --verbose

# Publish + materialize every checked-in view (currently just Patient):
python3 publish_views.py --config config.json --verbose
```

After a successful run the Patient view is queryable as `sof.patient_view` (one row per
first-class Patient, default DoH demographic columns; absent source fields are `NULL`,
never fabricated).

**Conformance gate.** A `ViewDefinition` is a SQL-on-FHIR logical-model resource, outside
the eCR/US-Core IG set, so its conformance gate is **Aidbox acceptance** (`PUT` accepted +
`$materialize` succeeds) — *not* `validator_cli.jar`. A unit test checks the checked-in
file is valid JSON with the required fields before any network call.

### Adding another resource type

The mechanism is resource-type-agnostic: drop a new `<type>.ViewDefinition.json` into
[`viewdefinitions/`](viewdefinitions/) and re-run `publish_views.py` — **no code or
invocation change**. Only the **Patient** view is authored today; views for other resource
types are intentionally *not* written speculatively, and will be added once the analytics
team specifies the columns they need.

## Provenance & search recipes

Every persisted resource carries three searchable `meta.tag[]` entries plus
`meta.source`, under the canonical base
`https://uwcirg.github.io/ecr-fhir-processor/CodeSystem`:

| Goal | FHIR `_tag` query |
|------|-------------------|
| Everything this software wrote | `GET [base]/Patient?_tag=<BASE>/processed-by\|ecr-fhir-processor` |
| A specific processing run | `GET [base]/Patient?_tag=<BASE>/processed-on\|2026-06-09T14:03:22+00:00` |
| Everything from one source file | `GET [base]/Patient?_tag=<BASE>/source-file\|CMS165_bulk_dial_high_00042.json` |

All resources in a single run share one `processed-on` value, so one `_tag` query
isolates a run. Re-running identical input updates the same resources in place (no
duplicates); only the provenance tags and server-managed `meta.lastUpdated`/`versionId`
change.

## Testing & validation (dual gate)

```bash
# 1. Unit tests for pure logic (per-resource PUT planning, Composition promotion, type
#    filter, stamping, collision, version, config):
python3 -m unittest discover -s tests

# 2. Conformance gate — validate the would-be submissions with the HL7 validator:
python3 process.py --input-dir test/input --dry-run --output-dir output
scripts/validate.sh        # wraps validator_cli.jar with versioned -ig packages

# 3. Server acceptance gate — persist to a test FHIR server and confirm acceptance.
```

See [`docs/input-data.md`](docs/input-data.md) for the input-data reference,
[`specs/001-mvp-fhir-processor/quickstart.md`](specs/001-mvp-fhir-processor/quickstart.md)
for the full validation guide, and
[`.specify/memory/constitution.md`](.specify/memory/constitution.md) for the governing
principles. Documented upstream validator issues are tracked in
[`known-validation-issues.md`](known-validation-issues.md).
