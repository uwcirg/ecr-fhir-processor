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
