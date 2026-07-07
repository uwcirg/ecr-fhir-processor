# Known Validation Issues

Documents FHIR validation errors seen in this project's pipeline that originate in
**upstream sources** (the test-data supplier's fixtures or upstream IG dependencies) —
**not** in this project's handling. It covers two distinct validation surfaces:

1. **The HL7 FHIR Validator gate** — the HL7 FHIR Validator (`validator_cli.jar`), run by
   `scripts/validate.sh` and CI. Errors documented for this surface are *filtered* so the
   build stays green while they remain unresolved upstream. This is the bulk of the file.
2. **Aidbox ingestion-time validation** — HTTP 422s returned when *submitting* resources to
   an Aidbox server. Documented in its own section near the end as **reference only**:
   nothing there is filtered, and it does not affect the build.

> **Filtering rule (constitution Principle III):** the gate's filtering (surface 1) MUST
> match only the *specific, documented* `PATTERN:` lines below — never broad wildcards. Any
> HL7-validator error that does **not** match a documented entry here is a real failure and
> MUST fail the build.

> **A note on the word "reference":** "the validator" or "the HL7 FHIR Validator" always
> means the `validator_cli.jar` gate tool (never a "reference implementation"). FHIR
> *references* (the `Reference` data type / referential integrity, as in the Aidbox
> `aidbox-validation-skip: reference` lever) are a separate, unrelated meaning, used only in
> the Aidbox section.

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
> resources (HTTP 422 at PUT time) — a different mechanism from the HL7 FHIR Validator
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
- **Existence vs. conformance (important):** Aidbox "reference validation" covers two
  distinct sub-checks — (1) *referential existence* (does `Patient/<id>` exist on the
  server?) and (2) *target-profile conformance* (does the referenced resource's **content**
  satisfy the `targetProfile` the referencing element declares?). **These failures are
  entirely (2), not (1).** The message says the referenced resource's *content* "doesn't
  conform" — Aidbox resolved the target (it exists) and judged its content against the
  profile. The `reference` skip value disables reference validation *as a category*, so it
  suppresses **both** sub-checks; the docs advertise (1), but it provably also covers (2).
- **Aidbox workaround:** `aidbox-validation-skip: reference` request header on the PUT
  (must be enabled box-wide with `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true`). This is the
  only **per-request** lever, so it can be applied surgically by the submitter without
  weakening the whole box. **The processor sends this header when configured** via
  `config.server.validation_skip` (a list, e.g. `["reference"]`; empty/absent = full
  validation). **Confirmed effective (2026-06-12):** the docs only describe this header as
  skipping *referential-existence* checks, but an empirical run with
  `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true` + `validation_skip: ["reference"]`
  (`log/ecr-fhir-processor_2026-06-12t152045.fails.log`) cleared **all three** Cause-1
  failures (Observation ×2 + MedicationRequest ×1; 39→42 succeeded). So the header **also
  suppresses target-profile *conformance* checks**, not just existence.
  (`BOX_FHIR_VALIDATOR_STRICT_PROFILE_RESOLUTION=false` (default) only ignores *unknown*
  profiles — these profiles are loaded, so that lever does not help here.)
- **Chosen remediation (Principle VIII — non-mutating lever):** the processor sends the
  per-request `aidbox-validation-skip: reference` header (driven by
  `config.server.validation_skip = ["reference"]`) and makes **no** content change to the
  affected resources (FR-002, FR-003). This is a lever, not a transform — the submitted
  bytes equal the emitted bytes. Applied levers are logged via
  `log_remediation(REMEDIATION_REFERENCE_SKIP, …)`.

REMEDIATION: aidbox-cause-1-reference-skip

### Cause 2 — `mrp-2` constraint (base FHIR R4 invariant)

- **Aidbox message:** `Invalid constraint result for ID 'mrp-2'. Expression:
  'group.stratifier.stratum.all(value.exists() xor component.exists())'.` → *Stratifiers SHALL
  be either a single criteria or a set of criteria components.*
- **Affected:** every MeasureReport (5 standalone + 3 inside message Bundles).
- **Root cause:** the source MeasureReports contain a stratum with `population` only and
  **no `value` and no `component`** (confirmed e.g. `group[0].stratifier[1].stratum[0]`).
  This is a genuine **base FHIR R4 invariant violation in supplier data** — Aidbox is correct
  to reject it; it is not strictness.
- **Aidbox workaround:** there is **no validation-side lever** — no per-constraint /
  per-invariant skip, no warnings-only mode, and the FHIR Schema engine cannot be turned off
  on a modern Aidbox (see the DO-NOT-USE note below). This is the **only** Cause with no
  non-mutating lever, so it is the one place Principle VIII permits a content transform.
- **Chosen remediation (Principle VIII — content transform, non-fabricating):** the
  processor **removes each stratifier `stratum` that has neither `value` nor `component`**
  (`prune_measurereport_strata` in `process.py`). A stratum with no stratification key is
  malformed *structure*, not clinical content — the removal rule is
  `value is None and not component`; conforming strata (`value` xor `component`) are left
  untouched, and the transform **only removes, never fabricates** (never adds a `value`/
  `component` to "fix" a stratum, per Principle V). It is idempotent, applied to standalone
  **and** message-Bundle-nested MeasureReports (FR-005), and runs on the write path before
  the `output/` mirror so the mirrored bytes equal the PUT bytes (FR-008). The
  `test/input/` fixtures are never modified. Every removal is logged at WARNING via
  `log_remediation(REMEDIATION_MRP2_STRATUM_PRUNE, …)` **including the removed stratum's
  population counts** (FR-006), so no count is silently dropped. Re-validated through the
  HL7 gate the transformed output introduces **no new signature** vs.
  `test/conformance-baseline.sigs` (FR-009).

REMEDIATION: aidbox-cause-2-mrp2-stratum-prune
- **`BOX_FHIR_SCHEMA_VALIDATION=false` is NOT a validation switch — DO NOT USE IT (empirical,
  2026-06-12):** it is an **engine selector**. On a modern Aidbox, FHIR Schema validation is
  mandatory; setting this flag `false` reverts the box to the **deprecated legacy (Zen/Entity)
  engine**. Observed consequences: the Aidbox console (`/ui/console#/settings`) warns *"This
  Aidbox instance uses deprecated capabilities … Please migrate to FHIR Schema engine,"* and
  **every FHIR PUT returns `HTTP 404 "PUT /fhir/<Type>/<id> not found"`** — the legacy engine
  does not serve the REST update-by-id path the processor uses. It does **not** relax
  validation; it breaks the FHIR API. (An earlier run where the flag appeared to have "no
  effect" was simply a case where the env var had not yet taken effect in the running box —
  the engine cannot be left running *and* unvalidated.) **Always run with
  `BOX_FHIR_SCHEMA_VALIDATION=true`.**

### Cause 3 — `terminology-binding-error` on `improvementNotation`

- **Aidbox message:** `Wrong Display Name 'Lower score indicates better quality' for
  http://terminology.hl7.org/CodeSystem/measure-improvement-notation#decrease. Valid display
  is 'Decreased score indicates improvement'.`
- **Affected:** same MeasureReports as Cause 2.
- **Root cause:** source sends code `decrease` with a non-canonical `display`. Same class as
  the **terminology display-name mismatches** already noted as upstream in
  "How the gate decides pass/fail" above. Upstream, not ours.
- **Aidbox workaround:** the FHIR Schema validator validates terminology bindings only when an
  external terminology server is configured via `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL`; leaving
  it **unset** skips binding validation box-wide. (It also enforces only `required`-strength
  bindings; weaker strengths are ignored.)
- **Chosen remediation (Principle VIII — non-mutating box-side lever):** rely on the box
  leaving `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` **unset**. The processor makes **no** content
  change — it MUST NOT rewrite terminology displays (FR-004). No per-request code path is
  involved; the reliance is recorded here and keyed to `REMEDIATION_TERMINOLOGY_UNSET`.

REMEDIATION: aidbox-cause-3-terminology-unset

### Cause 4 — `ext-1` constraint on an empty trigger-code sub-extension (base FHIR R4 invariant)

- **Aidbox message:** `Invalid constraint result for ID 'ext-1'. Expression:
  'extension.exists() != value.exists()'. Human-readable message: 'Must have either
  extensions or value[x], not both'.` at
  `Composition.section[9].entry[0].extension[0].extension[1]` (schema-id
  `triggerCodeValueSetVersion`).
- **Affected:** the eICR Composition of the **depression-screening (CMS2)** message Bundle
  (`Bundle_06308645-…`), surfacing on both the whole-Bundle PUT and the promoted Composition
  PUT. Isolated to that fixture — the other three trigger-code Bundles carry a real
  `triggerCodeValueSetVersion` (`valueString` present) and are unaffected.
- **Root cause:** the drajer/eCRNow `eicr-trigger-code-flag-extension` carries a
  `triggerCodeValueSetVersion` sub-extension that is a bare `{"url": …}` shell — **neither a
  `value[x]` nor nested extensions**. Aidbox's `ext-1` is XOR (`extension.exists() !=
  value.exists()`), so an element with *neither* side fails it (the "not both" wording is the
  generic message for the XOR). A genuine **base FHIR R4 invariant violation in supplier
  data**, not strictness.
- **Aidbox workaround:** there is **no validation-side lever** — `ext-1` is a base cardinality
  invariant, not a profile/terminology toggle (`BOX_FHIR_VALIDATOR_STRICT_EXTENSION_RESOLUTION`
  governs *unknown*-extension resolution, not this). Like Cause 2, this is a Cause with no
  non-mutating lever, so Principle VIII permits a content transform.
- **Chosen remediation (Principle VIII — content transform, non-fabricating):** the processor
  **removes each child sub-extension of an `eicr-trigger-code-flag-extension` that carries
  neither a `value[x]` nor nested extensions** (`prune_empty_trigger_code_extensions` in
  `process.py`). A url-only version marker is malformed *structure*, not clinical content —
  the `triggerCode` and `triggerCodeValueSet` siblings (the actual clinical payload) are
  preserved, and the transform **only removes, never fabricates** (never invents a version
  string, per Principle V). It is idempotent, walks message-Bundle → document-Bundle →
  Composition (so the Bundle is not rejected whole, FR-005; the same in-place walk cleans the
  promoted Composition, the same object), and runs on the write path before the `output/`
  mirror so the mirrored bytes equal the PUT bytes (FR-008). The `test/input/` fixtures are
  never modified. Every removal is logged at WARNING via
  `log_remediation(REMEDIATION_TRIGGER_CODE_EXT_PRUNE, …)` naming the removed sub-extension
  (FR-006), so no element is silently dropped. Re-validated through the HL7 gate the
  transformed output introduces **no new signature** vs. `test/conformance-baseline.sigs`
  (FR-009).

REMEDIATION: aidbox-cause-4-trigger-code-ext-prune

### Aidbox config levers (summary)

| Lever | Scope | Silences | Notes |
| --- | --- | --- | --- |
| `BOX_FHIR_SCHEMA_VALIDATION=false` | box-wide | **DO NOT USE** | Not a validation switch — an engine selector. `false` reverts to the deprecated legacy engine: console warns to migrate, and **every FHIR PUT 404s** (`not found`). Breaks the FHIR API; does not relax validation. FHIR Schema validation is mandatory — always keep `=true`. |
| `BOX_FHIR_VALIDATION_SKIP_REFERENCE=true` + `aidbox-validation-skip` header | **per-request** | Cause 1 (**confirmed**) | Only per-PUT lever. Sent by the processor via `config.server.validation_skip` (e.g. `["reference"]`). Confirmed 2026-06-12 to also cover target-profile *conformance*, not just existence. |
| `BOX_FHIR_TERMINOLOGY_SERVICE_BASE_URL` unset | box-wide | Cause 3 | No terminology server ⇒ binding validation skipped. Exact name per [Aidbox settings reference](https://www.health-samurai.io/docs/aidbox/reference/all-settings#fhir-terminology-service-base-url) (note the `BOX_FHIR_` prefix — **not** `AIDBOX_`; the wrong name silently re-enables Cause 3, seen in the 2026-07-02 run). |
| `BOX_FHIR_VALIDATOR_STRICT_PROFILE_RESOLUTION` / `..._STRICT_EXTENSION_RESOLUTION` | box-wide | — | Default `false`: *unknown* profiles/extensions ignored. Does not help Causes 1–4 (profiles/extensions are loaded; `ext-1` is a base cardinality invariant, not a resolution toggle). |
| _(no lever)_ | — | Cause 4 | Base-FHIR `ext-1` has no per-constraint skip. Cleared by the trigger-code sub-extension prune transform (above), like Cause 2. |

**Key takeaway:** with the schema engine kept **on** (`BOX_FHIR_SCHEMA_VALIDATION=true`,
mandatory — FR-014), all four causes are cleared in Principle VIII priority order: Causes 1
and 3 by **non-mutating levers** (reference-skip header; terminology server unset), and
Causes 2 and 4 — the ones with no lever — by **non-fabricating, structure-only prunes** (the
stratum prune and the empty trigger-code sub-extension prune) documented above. No cause
requires disabling the engine or fabricating clinical content.

**Architectural note:** conformance in this project is owned by the HL7 validator gate
(`scripts/validate.sh` + `test/conformance-baseline.sigs`). Aidbox is the downstream
SQL-on-FHIR analytics store, and its FHIR Schema engine is a **second** validation surface
that must stay enabled (FR-014 — disabling it reverts to the deprecated legacy engine and
breaks the FHIR REST API, see the DO-NOT-USE note above). Because the engine stays on, every
resource is made storable at the write boundary via the documented levers/transform rather
than by relaxing the box — remediation that is transparent (logged), auditable (documented
here), and idempotent.

- **Environment:** Aidbox FHIR Schema validation engine; settings per Aidbox docs
  (`health-samurai.io/docs/aidbox`, `reference/settings/fhir`,
  `modules/profiling-and-validation/skip-validation-of-references-in-resource-using-request-header`);
  fetched 2026-06-12.

## SQL-on-FHIR ViewDefinition FHIRPath — positional component indexer

The Observation view (007) is the **first** checked-in ViewDefinition to use a positional
index. Its second blood-pressure triad reads `component[1]` (and the first reads
`component[0]`); every prior view uses only `.first()` / `.where()` / `.ofType()`, so
indexer support in Aidbox's SQL-on-FHIR FHIRPath was **not previously demonstrated in this
repo**. The authoritative gate is server acceptance on `PUT` + `$materialize` plus the
quickstart query, run by the operator against Aidbox (007 research R2).

- **Primary expression (checked in):** `component[0].…` / `component[1].…`.
- **Documented one-line fallback if Aidbox rejects or nulls the indexer:** swap
  `component[0]`→`component.first()` and `component[1]`→`component.last()` in
  `viewdefinitions/observation.ViewDefinition.json` (column suffixes unchanged). The panel
  fixtures carry exactly two components, so `.first()`/`.last()` is equivalent there.
- **Verification outcome:** _pending — to be recorded here after the operator's
  `publish_views.py` + `sof.observation_view` query confirms whether the primary indexer was
  accepted or the fallback was applied (007 T005/T012)._

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
