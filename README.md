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
  bundle**, **MeasureReport**, **eCR message bundle**, or **unknown** (skipped).
- Stamps every persisted resource (and a message Bundle's own `meta`) with searchable
  provenance metadata, then persists it:
  - **collection** Bundles are converted to a FHIR **transaction** Bundle of
    `PUT [Type]/<id>` entries (ids retained) and `POST`ed to the base.
  - standalone **MeasureReport**s and **message** Bundles are `PUT` under their retained
    ids.
- Logs every outcome to the console and a timestamped audit file, and exits non-zero if
  any submission failed.

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
| `ig_versions{}` | recommended | IG → version for the conformance gate (`hl7.fhir.us.ecr`, `hl7.fhir.us.core`, `hl7.fhir.us.davinci-deqm`, `aphl.chronic-ds`). |
| `paths{input_dir,output_dir,log_dir}` | optional | Defaults `input`/`output`/`log`. |

> The software **version is not a config field** — it is derived at runtime from
> `git describe --tags --always --dirty` (falls back to `unknown` when git is
> unavailable).

## Usage

```text
python3 process.py [--config PATH] [--input-dir PATH] [--measure NAME]
                   [--output-dir PATH] [--no-output-mirror] [--dry-run]
                   [--log-dir PATH] [--verbose]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--config` | `config.json` | Run config (template: `config.example.json`). |
| `--input-dir` | `config.paths.input_dir` (`input`) | Root of the input tree. |
| `--measure` | all | Restrict to one measure folder. |
| `--output-dir` | `config.paths.output_dir` (`output`) | Submitted-JSON mirror location. |
| `--no-output-mirror` | off | Skip writing the local output mirror. |
| `--dry-run` | off | Discover/classify/stamp/transform but **do not submit** (no server needed). |
| `--log-dir` | `config.paths.log_dir` (`log`) | Audit-log directory. |
| `--verbose` | off | Console DEBUG verbosity (file log is always detailed). |

### Examples

```bash
# Dry run over the test fixtures (no server, no config required):
python3 process.py --input-dir test/input --dry-run --verbose

# Persist to the configured FHIR server:
python3 process.py --input-dir test/input --config config.json
```

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
# 1. Unit tests for pure logic (transform, stamping, collision, version, config):
python3 -m unittest discover -s tests

# 2. Conformance gate — validate the would-be submissions with the HL7 validator:
python3 process.py --input-dir test/input --dry-run --output-dir output
scripts/validate.sh        # wraps validator_cli.jar with versioned -ig packages

# 3. Server acceptance gate — persist to a test FHIR server and confirm acceptance.
```

See [`specs/001-mvp-fhir-processor/quickstart.md`](specs/001-mvp-fhir-processor/quickstart.md)
for the full validation guide and
[`.specify/memory/constitution.md`](.specify/memory/constitution.md) for the governing
principles. Documented upstream validator issues are tracked in
[`known-validation-issues.md`](known-validation-issues.md).
