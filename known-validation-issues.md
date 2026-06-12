# Known Validation Issues

Tracks HL7 FHIR Reference Validator errors that originate in **upstream IG
dependencies** (not in this project's handling) and are therefore filtered by CI and by
`scripts/validate.sh` so the build stays green while they remain unresolved upstream.

> **Filtering rule (constitution Principle III):** CI/validate filtering MUST match only
> the *specific, documented* error patterns below — never broad wildcards. Any validator
> error that does **not** match a documented entry here is a real failure and MUST fail
> the build.

## How to read this file

Each entry below is consumed by `scripts/validate.sh`: lines beginning with
`PATTERN:` are treated as fixed substrings to filter out of the validator's `error`
output. Everything else is human documentation. When an upstream fix ships (new IG
version or validator release), re-test and **remove** the corresponding entry.

Each documented entry MUST include: the exact validator error message (as a `PATTERN:`
line), the affected resource type, root-cause analysis, the responsible upstream package
and HL7 working group, reproduction steps proving the error exists in the IG's own
published examples, and the environment tested.

## How the gate decides pass/fail (delta vs. source baseline)

The supplier's source fixtures already produce validator errors that are **not ours to
fix** — R5-backport `extension-MeasureReport.*` extensions, duplicate population `id`s,
terminology display-name mismatches, and the validator's own intermittent resolution of
a newer eCR profile version (`3.0.0-ballot`) instead of the pinned `2.1.2`. Validating the
same resources before and after our transform yields the **same** error signatures.

So the gate enforces constitution Principle III's actual requirement — *zero
**project-introduced** errors* — rather than "zero errors". `scripts/validate.sh`:

1. validates the would-be output with the pinned IG set (`config.ig_versions`), then
2. reduces every `Error @ …` line to a location/line/UUID-independent **signature**
   (Bundle/contained container prefixes are collapsed so a resource has the same signature
   standalone or wrapped in a Bundle), and
3. fails only on signatures **absent from the committed source baseline**
   (`test/conformance-baseline.sigs`) and not matched by a `PATTERN:` below.

The baseline is the set of error signatures from validating the pre-transform fixtures
(`test/input/**/*.json`) with the same pinned IGs. It is committed so a gate run needs only
**one** validation pass. Because the validator's exact error wording changes between
releases, the baseline is tied to a **pinned validator version** (`FHIR_VALIDATOR_VERSION`
in `.github/workflows/ci.yml`, currently `6.9.9`). Regenerate and commit the baseline
whenever the fixtures, the pinned IG versions, or the validator version change — using that
same validator version:

```
scripts/validate.sh --update-baseline "test/input/**/*.json" config.example.json
```

### Pinned IG set (constitution II: IG Version Tracking)

`config.example.json.ig_versions` mirrors exactly what the test-data supplier validates
against (all resolvable from `packages.fhir.org`):

| IG | Version |
| --- | --- |
| `hl7.fhir.us.core` | `6.1.0` |
| `hl7.fhir.us.qicore` | `4.1.1` |
| `hl7.fhir.us.cqfmeasures` | `3.0.0` |
| `hl7.fhir.us.davinci-deqm` | `5.0.0` |
| `hl7.fhir.us.ecr` | `2.1.2` |
| `hl7.fhir.us.ph-library` | `2.0.0` |

Note: the supplier does **not** validate against the APHL Chronic Disease Surveillance IG
(`cqf.aphl.chronic-ds`, an unpublished draft only available as a build.fhir.org CI tarball),
so it is intentionally absent. The fixtures' `…/Measure/…|0.0.002` canonical references
resolve to warnings, not errors, without it.

- **Environment tested:** HL7 FHIR Validation tool v6.9.9; Java 17.0.15; FHIR R4 (4.0.1);
  2026-06-10. All six IG packages and their dependencies load successfully.

## Aidbox ingestion-time validation (separate from the HL7 validator gate)

> **Scope note:** This section documents **Aidbox server** rejections seen when *submitting*
> resources (HTTP 422 at PUT time) — a different mechanism from the HL7 Reference Validator
> gate documented above. **Do not add `PATTERN:` lines here:** those are consumed by
> `scripts/validate.sh` to filter *HL7 validator* output, and these Aidbox messages never
> appear there. This section is reference documentation only.

First live submission run against an Aidbox server (branch `indi-resources`, commit `61f6367`,
`log/ecr-fhir-processor_2026-06-12t120819.log`): **39/50 resources succeeded, 11 failed.**
All 11 failures trace to **three upstream/source-data causes** — none introduced by this
project's transform — consistent with the gate philosophy above (*zero project-introduced
errors*, not *zero errors*). What's new is that **Aidbox enforces as hard 422s several things
the HL7 validator gate only warns about or that the committed baseline already tolerates.**

Every failing `OperationOutcome` is emitted by Aidbox's **FHIR Schema validation engine**
(each cites `http://aidbox.app/CodeSystem/schema-id`). The engine is enabled with
`BOX_FHIR_SCHEMA_VALIDATION=true` (Aidbox default is `false`).

### Cause 1 — `invalid-target-profile` (reference target-profile conformance)

- **Aidbox message:** `Referenced resource Patient/<id> content doesn't conform to any of
  target profiles: http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient`
  (also seen for `us-core-encounter`).
- **Affected:** Observation ×2, MedicationRequest ×1 (and the two message Bundles containing them).
- **Root cause:** profile-family disagreement baked into the source eCR data. The eICR
  `Patient` is tagged `us-ph-patient` and `Encounter` is `eicr-encounter`, but the
  quality-measure resources that reference them are tagged US Core
  (`us-core-vital-signs` Observation, US-Core `MedicationRequest`), whose reference elements
  declare `targetProfile = us-core-patient` / `us-core-encounter`. Aidbox validates the
  *referenced* resource against the required profile and rejects on mismatch. Note: the
  `Patient` PUTs successfully **standalone** (HTTP 200) — rejection occurs only when it is
  validated *as a reference target*. The HL7 validator gate does **not** flag this.
- **Aidbox workaround:** `aidbox-validation-skip: reference` request header on the PUT
  (must be enabled box-wide with `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true`). This is the
  only **per-request** lever, so it can be applied surgically by the submitter without
  weakening the whole box. **Caveat (unconfirmed):** the header is documented for skipping
  *referential-existence* checks; whether it also suppresses target-profile *conformance*
  checks (this exact error) was not confirmable from the docs and needs a one-shot empirical
  run. Alternatives: `BOX_FHIR_VALIDATOR_STRICT_PROFILE_RESOLUTION=false` (default) means
  *unknown* profiles are ignored — but here the profiles are loaded, so that doesn't help.

### Cause 2 — `mrp-2` constraint (base FHIR R4 invariant)

- **Aidbox message:** `Invalid constraint result for ID 'mrp-2'. Expression:
  'group.stratifier.stratum.all(value.exists() xor component.exists())'.` → *Stratifiers SHALL
  be either a single criteria or a set of criteria components.*
- **Affected:** every MeasureReport (5 standalone + 3 inside message Bundles).
- **Root cause:** the source MeasureReports contain a stratum with `population` only and
  **no `value` and no `component`** (confirmed e.g. `group[0].stratifier[1].stratum[0]`).
  This is a genuine **base FHIR R4 invariant violation in supplier data** — Aidbox is correct
  to reject it; it is not strictness.
- **Aidbox workaround:** **none granular.** There is no documented per-constraint /
  per-invariant skip and no warnings-only mode for the FHIR Schema engine. The only
  ingestion workaround that **preserves source fidelity** is disabling the engine entirely:
  `BOX_FHIR_SCHEMA_VALIDATION=false` (box-wide; reverts to Aidbox's lighter built-in
  structural validation and removes profile validation for the whole box). Fixing the data
  would mutate supplier content and is out of scope per the gate philosophy.

### Cause 3 — `terminology-binding-error` on `improvementNotation`

- **Aidbox message:** `Wrong Display Name 'Lower score indicates better quality' for
  http://terminology.hl7.org/CodeSystem/measure-improvement-notation#decrease. Valid display
  is 'Decreased score indicates improvement'.`
- **Affected:** same MeasureReports as Cause 2.
- **Root cause:** source sends code `decrease` with a non-canonical `display`. Same class as
  the **terminology display-name mismatches** already noted as upstream in
  "How the gate decides pass/fail" above. Upstream, not ours.
- **Aidbox workaround:** the FHIR Schema validator validates terminology bindings only when an
  external terminology server is configured via `AIDBOX_TERMINOLOGY_SERVICE_BASE_URL`; leaving
  it **unset** skips binding validation box-wide. (It also enforces only `required`-strength
  bindings; weaker strengths are ignored.)

### Aidbox config levers (summary)

| Lever | Scope | Silences | Notes |
| --- | --- | --- | --- |
| `BOX_FHIR_SCHEMA_VALIDATION=false` | box-wide | **all 3** | Disables FHIR Schema engine; reverts to lighter structural validation. Removes profile validation entirely. Cleanest single switch to ingest source as-is. |
| `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true` + `aidbox-validation-skip: reference` header | **per-request** | Cause 1 (likely) | Only per-PUT lever. Target-profile coverage unconfirmed — verify empirically. |
| `AIDBOX_TERMINOLOGY_SERVICE_BASE_URL` unset | box-wide | Cause 3 | No terminology server ⇒ binding validation skipped. |
| `BOX_FHIR_VALIDATOR_STRICT_PROFILE_RESOLUTION` / `..._STRICT_EXTENSION_RESOLUTION` | box-wide | — | Default `false`: *unknown* profiles/extensions ignored. Does not help Causes 1–3 (profiles are loaded). |

**Key takeaway:** there is **no surgical combination that clears all three** while keeping the
schema engine on — Cause 2 (`mrp-2`) is a base-spec invariant with no selective skip, so
getting it past Aidbox requires either `BOX_FHIR_SCHEMA_VALIDATION=false` or mutating the data.

**Architectural note:** conformance in this project is owned by the HL7 validator gate
(`scripts/validate.sh` + `test/conformance-baseline.sigs`). Aidbox is the downstream
SQL-on-FHIR analytics store. Re-enforcing strict conformance at the Aidbox write boundary is
redundant with that gate and drops data the gate already accepts — which argues for letting
Aidbox simply *store* (i.e. `BOX_FHIR_SCHEMA_VALIDATION=false`) rather than re-validate.

- **Environment:** Aidbox FHIR Schema validation engine; settings per Aidbox docs
  (`health-samurai.io/docs/aidbox`, `reference/settings/fhir`,
  `modules/profiling-and-validation/skip-validation-of-references-in-resource-using-request-header`);
  fetched 2026-06-12.

## Open issues (validator errors to filter)

_None recorded yet._

<!--
Template for a new entry (uncomment and fill in; add the PATTERN line so the gate
filters exactly this message and nothing broader):

### <short title>

PATTERN: <exact substring of the validator error line to filter>

- **Affected resource type:** <e.g., MeasureReport>
- **Root cause:** <why this originates upstream, not in our processing>
- **Upstream package / working group:** <e.g., hl7.fhir.us.davinci-deqm — Da Vinci CQI>
- **Reproduction in the IG's own examples:** <steps showing the IG's published example
  triggers the same error>
- **Environment tested:** <validator_cli.jar version, Java version, IG versions, date>
- **Status / tracking link:** <issue URL filed with the working group>
-->
