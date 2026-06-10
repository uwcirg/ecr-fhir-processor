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

## Gate prerequisites / blockers

These are not validator *errors* to filter — they are prerequisites that currently
prevent the conformance gate (`scripts/validate.sh`, quickstart Scenario B) from running
to a green result. Tracked here so the blocker is explicit (constitution Principle II/III;
tasks T032/T036).

### IG versions unpinned + APHL package unresolved (TODO(ECR_IG_VERSION))

- **`hl7.fhir.us.ecr`, `hl7.fhir.us.core`, `hl7.fhir.us.davinci-deqm`** are `TODO_PIN`
  in `config.example.json`. They must be pinned to the versions the target deployment
  confirms before the gate is reproducible. `scripts/validate.sh` deliberately **skips**
  unpinned IGs (with a WARNING) rather than guessing a version.
- **`aphl.chronic-ds#0.0.002`** (the Measure canonicals referenced by the fixtures,
  canonical `fhir.org/guides/cqf/aphl/chronic-ds`) does **not resolve** from the public
  FHIR package registries:
  - `Error fetching https://packages2.fhir.org/packages/aphl.chronic-ds: Not Found`
  - `Error fetching https://packages.fhir.org/aphl.chronic-ds: Not Found`
  The correct package id / registry / tgz source for the APHL Chronic Disease
  Surveillance IG at `0.0.002` must be confirmed (it may need `-ig <path-to-package.tgz>`
  or a custom package server) before validation can load it.
- **Environment tested:** HL7 FHIR Validation tool v6.9.7; Java 17.0.15; FHIR R4 (4.0.1);
  2026-06-09. FHIR core, terminology, and uv.extensions packages loaded successfully —
  the only load failure is the unresolved `aphl.chronic-ds` package above.
- **Status:** the CI `conformance-gate` job is marked `continue-on-error: true` until
  this is resolved (see `.github/workflows/ci.yml`). Resolve by pinning the three eCR/Core/
  DEQM versions and supplying a resolvable APHL package reference, then drop
  `continue-on-error`.

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
