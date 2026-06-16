# Quickstart: Filter Analytics by CMS Measure

**Feature**: `003-cms-measure-filter` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Runnable validation that the CMS-measure attribution is stamped, queryable by tag, and
filterable as a Patient-view column. Implementation lives in `tasks.md`/the code; this is the
prove-it-works guide. Maps to SC-001…SC-006.

## Prerequisites

- The feature-001 environment: Python 3 (stdlib only), `validator_cli.jar` + Java available
  (Principle III), and a reachable Aidbox with valid `config.json` (base URL + OAuth2 creds).
- Fixtures present under `test/input/` (the `CMS122_*` / `CMS165_*` collection bundles).
- The Patient view + publish step from feature 002 (`viewdefinitions/patient.ViewDefinition.json`,
  `publish_views.py`).

## A. Unit logic (no server, no Java)

```bash
python -m unittest tests.test_cms_measure -v
python -m unittest tests.test_viewdefinition -v
```

**Expected**: derivation cases pass (`CMS165_*`→`CMS165`, `CMS2_*`→`CMS2`, `cms165_*`→`CMS165`,
`CMSX_*`/`foo.json`→`unknown`); `stamp()` adds exactly one cms-measure tag and re-stamp keeps
exactly one; the disagreement rule warns only on concrete-vs-different-concrete; the Patient
ViewDefinition carries the `cms_measure` column. (SC-002, SC-005, SC-006 in unit form.)

## B. Stamping on real fixtures (dry-run, no server)

```bash
python process.py --dry-run --verbose --no-output-mirror 2>&1 | tee /tmp/cms-dryrun.log
```

**Expected**: run completes exit 0; no `CMS measure mismatch` warnings for the canonical
fixtures (their filenames and measure folders agree). To see the tag concretely, inspect one
mirrored/stamped resource (run without `--dry-run` against a test server, or add a temporary
mirror) and confirm `meta.tag` contains
`{ "system": ".../cms-measure", "code": "CMS165", ... }` for a `CMS165_*` file. (FR-002, FR-003.)

### Negative / mismatch check (SC-006)

```bash
# temporary: a CMS122-named file placed under the controllable-bp (CMS165) folder
cp test/input/poor-diabetic-control/standard/CMS122_*.json \
   test/input/controllable-bp/standard/ 2>/dev/null
python process.py --dry-run --measure controllable-bp 2>&1 | grep "CMS measure mismatch"
# clean up the copy afterward
```

**Expected**: one WARNING line per mismatched file naming `filename=CMS122 directory=CMS165`;
the resource would still be tagged `CMS122` (filename wins). Remove the temp copy after.

## C. FHIR conformance gate (Principle III — must pass)

```bash
python process.py            # persist fixtures to the test server (or mirror), then:
java -jar validator_cli.jar output/**/*.json -version 4.0.1 \
  -ig hl7.fhir.us.ecr#$ECR_IG_VERSION -ig hl7.fhir.us.core#$US_CORE_VERSION \
  -ig hl7.fhir.us.davinci-deqm#$DEQM_VERSION
```

**Expected**: zero project-introduced errors (the added tag yields at most warnings — C-6).
Apply the same `known-validation-issues.md` filtering as CI.

## D. End-to-end: query by measure (server)

```bash
python process.py                 # persist fixtures (resources now carry cms-measure tags)
python publish_views.py           # re-publish + $materialize the Patient view (now has cms_measure)
```

Then against the materialized `sof.patient_view`:

```sql
SELECT cms_measure, count(*) FROM patient_view GROUP BY cms_measure;     -- distribution
SELECT * FROM patient_view WHERE cms_measure = 'CMS165';                 -- one measure (SC-001/003)
```

Or by FHIR `_tag` (any resource type, FR-008):

```bash
curl -s "$BASE/Condition?_tag=https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure|CMS165" \
  -H "Authorization: Bearer $TOKEN" | jq '.total'
```

**Expected**: the `CMS165` filter returns exactly the CMS165-sourced patients/resources and
excludes the CMS122 ones (SC-001, SC-003).

## E. Re-attribution on rename (US3 / SC-004)

```bash
# 1. process a deliberately non-conforming filename → lands as 'unknown'
cp test/input/controllable-bp/standard/CMS165_*.json /tmp/export_noprefix.json
python process.py --input-dir /tmp   # (point at a scratch dir holding the renamed file)
#    -> its resources carry cms-measure code 'unknown'

# 2. rename to the convention and re-process
mv /tmp/export_noprefix.json /tmp/CMS165_reattributed.json
python process.py --input-dir /tmp
```

**Expected**: the same resource ids now carry `CMS165` (not `unknown`); exactly one cms-measure
tag (no duplicate), no duplicate resource on the server, and the `unknown` count drops (SC-004).
Idempotent update-in-place via retained ids.

## Success mapping

| Check | Criterion |
|-------|-----------|
| D (measure filter returns only that measure) | SC-001, SC-003 |
| A/B (every stamped resource has exactly one CMS-measure tag) | SC-002 |
| A (only canonical `CMS<n>`/`unknown` codes) | SC-005 |
| E (rename → re-attribute in place, no dupes) | SC-004 |
| B negative (mismatch warned, never silent) | SC-006 |
