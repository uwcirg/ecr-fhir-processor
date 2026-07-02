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
- Makes every emitted resource **storable on the Aidbox ingestion surface** without
  fabricating or dropping clinical content (see [Aidbox storability](#aidbox-storability)):
  non-mutating levers clear reference and terminology rejections, and a documented,
  non-fabricating **stratum-prune transform** makes MeasureReports storable (removing each
  malformed `mrp-2` stratum that carries no stratification key) rather than deferring them.
- Lets a problem resource type be landed in a **separate idempotent run** via
  `--only-types` / `--skip-types`: persist one type first, then land another later — the
  second run neither duplicates nor rolls back the first.
- Logs every outcome to the console and a timestamped audit file, reporting each FHIR type
  as **stored / remediated / deferred**, and exits with a **three-state code**: `0` when
  every in-scope resource stored (remediation is still `0`), `1` on an unexpected failure,
  and `2` when a type was deferred (isolated to avoid fabrication). A rejected resource
  never blocks its siblings.

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

# Independent per-type runs (operational convenience — MeasureReports are storable now
# via the stratum-prune transform, so this split is no longer required for them):
#   1. land everything except MeasureReports …
python3 process.py --input-dir test/input --skip-types MeasureReport
#   2. … then land just those (idempotent — neither duplicates nor rolls back run 1):
python3 process.py --input-dir test/input --only-types MeasureReport
```

## Aidbox storability

Aidbox's FHIR Schema engine (kept **enabled** — `BOX_FHIR_SCHEMA_VALIDATION=true`) is a
second validation surface, distinct from the HL7 validator gate. Making every emitted
resource storable there is done **without fabricating or dropping clinical content**
(constitution Principle VIII, subordinate to Principle V). The four documented Aidbox
rejection causes are cleared in priority order — non-mutating levers first, a transform
only where no lever exists (see [`known-validation-issues.md`](known-validation-issues.md)):

- **Cause 1 — reference target-profile conformance** (Observation, MedicationRequest, and
  the message Bundles carrying them). Cleared by a **non-mutating lever**: the per-request
  `aidbox-validation-skip: reference` header the processor already sends when
  `config.server.validation_skip` includes `"reference"`. **No content is edited** — the
  submitted bytes equal the emitted bytes.
- **Cause 3 — terminology display binding** (the MeasureReports). Cleared **box-side** by
  leaving `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` unset. The processor makes **no** content
  change and never rewrites terminology displays.
- **Cause 2 — base-FHIR `mrp-2` invariant** (every MeasureReport, standalone and nested in
  message Bundles). The **only** cause with no non-mutating lever, so the **only** content
  transform: the processor **removes each stratifier `stratum` that has neither `value` nor
  `component`** — a stratum with no stratification key is malformed *structure*, not
  clinical content. The transform is **non-fabricating** (it only removes, never invents a
  `value`/`component`), idempotent, and runs on the write path **before** the `output/`
  mirror so the mirrored bytes equal the PUT bytes. Every removal is logged at WARNING with
  the population counts the stratum carried, and re-validating the transformed output
  through the HL7 gate introduces **no new signature** vs. `test/conformance-baseline.sigs`.
  MeasureReports are thus made storable **rather than deferred** — replacing the earlier
  "land MeasureReports in a later run once Aidbox is relaxed" stance.
- **Cause 4 — base-FHIR `ext-1` invariant** (the CMS2 eICR Composition + its message
  Bundle). Also no non-mutating lever (`ext-1` is a base cardinality invariant), so a
  second structure-only transform: the processor **removes each child of an
  `eicr-trigger-code-flag-extension` that carries neither a `value[x]` nor nested
  extensions** — in the sample data an empty `triggerCodeValueSetVersion`. The
  `triggerCode`/`triggerCodeValueSet` siblings (the clinical payload) are preserved and no
  version is fabricated (non-fabricating, idempotent, runs before the mirror). Every
  removal is logged at WARNING, and the transformed output introduces **no new** HL7-gate
  signature.

The FHIR Schema engine stays **enabled** throughout (`BOX_FHIR_SCHEMA_VALIDATION=true`) —
it is never disabled to force storage (that reverts Aidbox to the deprecated legacy engine
and breaks the FHIR REST API). Every applied lever/transform is logged at WARNING
(`[remediation:<key>]`) and documented in `known-validation-issues.md`; an undocumented
remediation is a defect, enforced by a test. The run reports each FHIR type as
**stored / remediated / deferred / transformed** (where `transformed` counts resources a
content transform touched — visible even if the resource then failed on an independent
cause) and exits `0` (all stored) / `1` (unexpected failure) / `2` (a type deferred), so
operators and CI can branch on the outcome without Aidbox logs.

## Analytics views (`publish_views.py`)

Downstream analytics (e.g. a DoH team) query flattened, one-row-per-resource SQL views
rather than raw FHIR. The materialized views now span **twelve resource types** — Patient
plus Condition, Encounter, Observation, Practitioner, Organization, Location, Measure,
Bundle, Procedure, MedicationRequest, and ServiceRequest. Those views are defined by
checked-in **SQL-on-FHIR `ViewDefinition`** resources under
[`viewdefinitions/`](viewdefinitions/) and pushed to
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

# Publish + materialize every checked-in view (twelve resource types):
python3 publish_views.py --config config.json --verbose
```

After a successful run the Patient view is queryable as `sof.patient_view` (one row per
first-class Patient, default DoH demographic columns; absent source fields are `NULL`,
never fabricated). It also carries a `cms_measure` column (the resource's CMS-measure tag —
see [Provenance & search recipes](#provenance--search-recipes)), so an analyst filters the
flattened view to one measure with a single predicate:

```sql
SELECT * FROM sof.patient_view WHERE cms_measure = 'CMS165';   -- one measure
SELECT cms_measure, count(*) FROM sof.patient_view GROUP BY cms_measure;  -- distribution
```

A Patient persisted before this column existed (not yet re-processed) yields `NULL` here,
never an error.

### Joining views (`AidboxQuery`)

Reference columns (e.g. Observation `subject`) hold the referenced resource's **key** —
emitted via `getReferenceKey()`, equal to the target view's `getResourceKey()` `id` — so
views join directly without a `Type/` prefix to strip. (A raw `.reference` string column
would be `NULL` under Aidbox's reference normalization; see
[research.md R4](specs/004-remaining-viewdefinitions/research.md).) Save a reusable query as
an `AidboxQuery` resource, then call it by name. In the Aidbox REST console at
`https://<aidbox-url>/ui/console#/rest`:

```http
PUT /AidboxQuery/aidboxquery_ecr_test_patient_obs
accept:application/json
content-type:application/json

{
    "resourceType": "AidboxQuery",
    "query": "select pt.id, pt.name_family, pt.name_given, pt.birth_date, ob.cms_measure, ob.category, ob.code_display from sof.patient_view pt join sof.observation_view ob on ob.subject = pt.id;"
}
```

Then invoke it by name — it's a plain `GET`, so you can just paste this URL into your
browser's address bar (no CLI or special UI needed). The join key `ob.subject = pt.id` is
what `getReferenceKey()` makes possible:

```
https://<aidbox-url>/$query/aidboxquery_ecr_test_patient_obs
```

This is an illustrative join, not a clinically-vetted public-health query — it shows the
mechanics (key-based view joins, `cms_measure` carried through), and the column list is the
analyst's to refine.

**Conformance gate.** A `ViewDefinition` is a SQL-on-FHIR logical-model resource, outside
the eCR/US-Core IG set, so its conformance gate is **Aidbox acceptance** (`PUT` accepted +
`$materialize` succeeds) — *not* `validator_cli.jar`. A unit test checks the checked-in
file is valid JSON with the required fields before any network call.

### Adding another resource type

The mechanism is resource-type-agnostic: drop a new `<type>.ViewDefinition.json` into
[`viewdefinitions/`](viewdefinitions/) and re-run `publish_views.py` — **no code or
invocation change**. Twelve views are authored today (Patient plus the eleven listed
above), each with the same provenance scoping and `cms_measure` column as Patient. Two are
special cases: `sof.measure_view` materializes but returns **zero rows** until `Measure`
resources are loaded (this project's fixtures only *reference* APHL Measure canonicals), and
`sof.bundle_view` exposes container metadata only — its nested clinical content is promoted
to the other first-class views, not flattened here. Each view's column set is an informed,
reviewable default, refined as the analytics team specifies the columns they need.

## Provenance & search recipes

Every persisted resource carries four searchable `meta.tag[]` entries plus
`meta.source`, under the canonical base
`https://uwcirg.github.io/ecr-fhir-processor/CodeSystem`:

| Goal | FHIR `_tag` query |
|------|-------------------|
| Everything this software wrote | `GET [base]/Patient?_tag=<BASE>/processed-by\|ecr-fhir-processor` |
| A specific processing run | `GET [base]/Patient?_tag=<BASE>/processed-on\|2026-06-09T14:03:22+00:00` |
| Everything from one source file | `GET [base]/Patient?_tag=<BASE>/source-file\|CMS165_bulk_dial_high_00042.json` |
| One CMS quality measure (any resource type) | `GET [base]/Condition?_tag=<BASE>/cms-measure\|CMS165` |
| The un-attributed bucket | `GET [base]/Condition?_tag=<BASE>/cms-measure\|unknown` |

All resources in a single run share one `processed-on` value, so one `_tag` query
isolates a run. Re-running identical input updates the same resources in place (no
duplicates); only the provenance tags and server-managed `meta.lastUpdated`/`versionId`
change.

### CMS-measure attribution (`cms-measure` tag)

Every persisted resource is tagged with its CMS quality measure under
`<BASE>/cms-measure`, **derived purely from the input filename**: a name beginning
`CMS<n>` (case-insensitive — `CMS2`, `CMS122`, `CMS165`, …) yields that uppercased code;
any other name yields the positive sentinel `unknown`. The parent directory is never
consulted for the value — if a file's `CMS<n>` prefix disagrees with the measure folder it
sits in, the processor logs a `WARNING` (naming both) and the **filename wins**; it is
never silently reconciled. The tag's `display` is the human slug from the authoritative
crosswalk (`MEASURE_SLUG_BY_CMS` in `process.py`): `CMS2`→`depression-screening`,
`CMS122`→`poor-diabetic-control`, `CMS165`→`controllable-bp` (`unknown`→`unknown measure`).

The tag is idempotent (exactly one per resource, replaced in place on re-stamp), so the
production fix for an un-attributed file is simply to **rename it to the `CMS<n>`
convention and re-run** — the same resources re-attribute from `unknown` to `CMS<n>` with
no duplicate resource or tag. `unknown` is a positive value in the project-owned system (no
published `CodeSystem` resource — consistent with the other provisional tag systems), so
un-attributed resources can be positively listed and counted; the HL7
`DataAbsentReason`/`unknown` vocabulary is the noted standards-track alternative.

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
