# Research: MVP eCR FHIR Processor

**Phase 0 output.** Resolves the spec's Open Questions (OQ-1 identity, OQ-2 granularity)
and the remaining design unknowns, via a data-inspection spike over `test/input/**` plus
constitution constraints.

---

## D1 — Resource identity strategy (resolves OQ-1)

**Decision**: Retain each source resource's original `resource.id`. Persist with HTTP
`PUT [base]/<ResourceType>/<id>` (update-in-place), never blind `POST`.

**Evidence** (spike over all 10 fixture files):

- Every clinical `resource.id` is a GUID, e.g. `Patient/4865655a-d6f8-47fe-86a9-694ea02d98d3`.
- Shared resources reuse **identical** GUIDs across scenarios:
  `Practitioner/b2360d5d-...`, `Organization/380dcfda-...`, `Location/26bbd95f-...`
  appear unchanged in all four collection bundles.
- The eCR document Bundle uses a stable named id
  (`eicr-report-ChronicDSControllingBloodPressure`); the MessageHeader and inner
  collection Bundle use GUIDs.

**Rationale**: GUIDs are globally unique, so retaining them and PUTting is safe and
idempotent — re-running the same input updates the same resource (FR-016) and the shared
Practitioner/Org/Location are written once and merely updated by later scenarios rather
than duplicated. Minting new ids would (a) break the relative references (see D2) and
(b) create duplicates on every run.

**Alternatives considered**:
- *Mint new server-assigned ids (POST)* — rejected: duplicates on every run; breaks
  relative references; defeats FR-016.
- *Conditional create (`If-None-Exist`)* — rejected: more complex, and unnecessary
  because ids are already stable and unique.

---

## D2 — Persistence granularity & mechanism (resolves OQ-2; constitution v1.1.0 Principles VI + V)

**Decision**: Persist the **contained resources** of each collection Bundle as
first-class resources, each via its **own independent** `PUT [base]/<ResourceType>/<id>`
— **not** wrapped in a server-atomic `transaction` Bundle. Each resource (and each input
kind) is an independent unit of work whose success or failure is isolated from the others
(constitution Principle V — "Independent persistence (no global transaction)"; Principle
VI — analytics-ready granularity).

**Why the change from a transaction Bundle** (this supersedes the earlier MVP draft, which
converted the collection Bundle into one atomic `transaction`):

- The downstream SQL-on-FHIR consumer requires every contained resource to be a queryable
  first-class resource (Principle VI) — satisfied by either mechanism, but…
- …the target Aidbox server currently **rejects the test MeasureReports** on validation.
  Inside one atomic `transaction`, a single rejected entry rolls back *every* resource in
  that bundle — so one bad MeasureReport would block the Patient/Encounter/Observation/etc.
  that validate cleanly. Independent PUTs isolate the failure to just the offending
  resource(s) (amended Principle V).
- It also lets a problem resource type be persisted in a **separate later run** (e.g.,
  MeasureReports after Aidbox validation is relaxed) without re-sending or rolling back
  what already landed (see D10).

**Mechanism**: individual `PUT [base]/<Type>/<id>` per resource. A FHIR **`batch`** Bundle
(which is **non-atomic** — per-entry success, no rollback) is an acceptable round-trip
optimization *because it preserves per-entry isolation*; a **`transaction`** Bundle is
**not** permitted for multi-resource persistence (it reintroduces all-or-nothing).

**Evidence**:

- Inter-resource references inside the collection bundle are **relative**:
  `Condition.subject → "Patient/4865655a-..."`, `Encounter.participant →
  "Practitioner/b2360d5d-..."`, etc. Each referenced resource must therefore exist at
  `[base]/<Type>/<id>` — which independent PUTs (retained ids, D1) satisfy.
- Collection bundles carry **no** `entry.request` and `type = "collection"`, so they are
  not directly submittable as-is; the processor iterates `entry[].resource` and PUTs each.

**Per input type**:
| Input file | type | Persistence action |
|------------|------|--------------------|
| Collection Bundle (`CMS*_*.json`) | `collection` | Stamp each contained resource; **independent** `PUT [base]/<Type>/<id>` per resource (or non-atomic `batch`); failures isolated per resource |
| MeasureReport (`MeasureReport_*.json`) | individual | Stamp; `PUT [base]/MeasureReport/<id>` — independently (often a separate run; see D10) |
| eCR message Bundle (`Bundle_*.json`) | `message` | Stamp the Bundle's `meta`; `PUT [base]/Bundle/<id>` (wrapper GUID). **Plus** promote the nested eICR Composition — see D2b |

**Alternatives considered**:
- *Atomic `transaction` Bundle (the earlier MVP draft)* — **rejected now**: all-or-nothing
  rollback means one rejected resource type (MeasureReport) defeats the whole scenario;
  violates amended Principle V (independent persistence).
- *Store the collection Bundle as one opaque `Bundle` resource* — rejected: relative
  references would not resolve to queryable resources; surveillance/analytics queries
  (e.g., find this run's Patients) would not work (Principle VI).
- *Submit the eCR message Bundle to `$process-message`* — deferred beyond MVP; that
  operation triggers message-processing workflows on the server we don't control. MVP
  persists it as a retrievable `Bundle` resource. (Revisit if the destination requires
  `$process-message` ingestion.)

---

## D2b — Promote the eICR Composition to a first-class resource (constitution Principle VI)

**Decision**: For in-population scenarios carrying an eCR message Bundle
(`Bundle_<uuid>.json`), extract the nested eICR **`Composition`** and persist it
independently — stamp it and `PUT [base]/Composition/<id>` — **in addition to** persisting
the message Bundle whole (D2). **Only** the Composition is promoted.

**Why**: SQL-on-FHIR `ViewDefinition`s can flatten only first-class resources; the eICR
**Composition** (the artifact the downstream DoH analytics team cares about most) was
otherwise trapped inside the stored message Bundle and unqueryable.

**No fidelity regression (Principles VI + V)**: Do **not** promote the eICR's other nested
clinical resources — they are lower-fidelity duplicates (e.g., Observation
`effectiveDateTime` loses time-of-day; `Patient.address.line` double-JSON-encoded) of the
authoritative collection-Bundle resources already persisted under the same GUIDs.
Re-persisting them would overwrite clean data (and could trip the FR-019 collision guard).
The `MessageHeader` stays nested (its `focus` is the fixed-id document Bundle).

**Safety**: The Composition's `id` is a **per-case GUID** (unique), so
`PUT [base]/Composition/<id>` is collision-safe (unlike the document Bundle's fixed
template-handle id — see D4b). Its references (`subject`/`encounter`/`author`/
`section.entry`) resolve to the clean collection-Bundle resources (same retained GUIDs).
Guardrail: log a WARNING for any Composition reference that does not resolve to a persisted
resource (consistent with D3); do not mutate it.

**Alternatives considered**:
- *Promote all nested eICR resources* — rejected: overwrites authoritative clinical data
  with degraded duplicates (fidelity regression; Principle V).
- *Persist only the Composition and drop the message Bundle* — rejected: we keep the whole
  eCR payload for provenance and **add** the Composition, not replace it.

---

## D3 — Reference style on the target server

**Decision**: Do **not** rewrite references. Relative references (`Type/<id>`) are kept
relative and resolve against `[base]`. Absolute references already present in the source
that point at the origin server (`http://ecr.drajer.com/...`) are left as-is.

**Rationale**: Constitution Principle II forbids rewriting reference styles in a way that
breaks resolution. Retaining ids (D1) keeps relative refs valid. The source's own
absolute refs are external by definition; silently rewriting them risks corruption. Any
unresolved absolute reference is a data characteristic to surface (logged), not silently
"fixed."

**Note for tasks**: log a WARNING when an absolute reference to a non-target host is
detected, so the operator is aware it will not resolve internally. Do not mutate it.

---

## D4 — Provenance metadata mechanism (resolves FR-004 / FR-005)

**Decision**: Stamp `meta.tag[]` entries (FHIR-native, server-searchable via `_tag`) plus
`meta.source`. Three tags, one source:

| Purpose | Field | System (canonical) | Code / value |
|---------|-------|--------------------|--------------|
| Processor identity + version | `meta.tag` | `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by` | code=`ecr-fhir-processor`, `version`=`<git version>`, display=`Processed by ecr-fhir-processor <git version>` |
| Processing run timestamp | `meta.tag` | `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-on` | code=`<ISO-8601 instant w/ offset>` |
| Source file | `meta.tag` | `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/source-file` | code=`<basename of source .json>` |
| Source provenance (uri) | `meta.source` | — | `<processed-by canonical>#<git version>` |

**Search recipes the operator gets** (constitution: easy to filter):
- Everything this software wrote: `GET [base]/Patient?_tag=https://.../processed-by|ecr-fhir-processor`
- A specific run: `?_tag=https://.../processed-on|2026-06-09T14:03:22+00:00`
- A specific source file: `?_tag=https://.../source-file|CMS165_bulk_dial_high_00042.json`
- (Cross-type): apply the same `_tag` filter on any resource type.

**Rationale**: `meta.tag` is the standard, universally-searchable provenance slot —
every FHIR R4 server indexes `_tag`. One run shares a single `processed-on` value across
all its resources, so a single `_tag` query isolates a run. Tags are additive and do not
change clinical meaning (FR-015). The timestamp includes a timezone offset (FR-007).

**Alternatives considered**:
- *`Provenance` resource per target* — the most semantically correct FHIR model
  (`Provenance.recorded`/`.agent`/`.target`), and a natural future enhancement, but
  heavier for MVP (an extra resource per persisted resource, plus target reference
  management). Deferred; the tag approach fully satisfies FR-004/FR-005.
- *Extension on `meta`* — rejected: custom extensions under `meta` are not searchable by
  default, defeating "easy to filter."
- *`meta.lastUpdated`* — rejected for the processing timestamp: it is server-managed and
  reflects server write time, not our processing time.

**Open implementation detail (non-blocking)**: the exact canonical host strings above are
provisional; confirm the org's canonical base when publishing. They only need to be
stable constants in `process.py`.

---

## D4b — Fixed (non-GUID) ids & cross-scenario collisions (refines D1/D2)

**Trigger**: A crosswalk of two `poor-diabetic-control/standard` scenarios
(`CMS122_DENOM_HbA1c_7p5_GoodControl` vs `CMS122_VAR_NUM_DM_CKD_Insulin_PoorControl`)
surfaced an id-reuse pattern the original spike missed.

**Findings**:
- Patient-level resources (Patient, Condition, Encounter, Observation, MeasureReport) and
  the **message-wrapper** Bundles all use GUIDs that are **unique per scenario**
  (wrappers `f0b34c63…` vs `bbe4547f…`).
- Shared reference resources (`Practitioner/b2360d5d…`, `Organization/380dcfda…`,
  `Location/26bbd95f…`) recur across scenarios with **identical content** — PUT-dedup is
  correct and desired.
- **Exception (apparent clash)**: the nested **eICR document Bundle** uses a **fixed,
  measure-named id** `eicr-report-ChronicDSDiabetesPoorControl`, **reused across distinct
  patients with different content** (A → Patient `016788c3…`, 8 entries; B → Patient
  `b9a1b53d…`, 10 entries).

**Root cause (the id is not the identity)**: For a `type=document` (or `message`) Bundle,
FHIR places the document's persistent, globally-unique identity in **`Bundle.identifier`**,
not `Bundle.id`. eCRNow (drajer-health/eCRNow) honors this: it names `Bundle.id` after the
eICR *template/trigger* (hence constant per measure), while the per-case identity lives in
`Bundle.identifier`, which **is** unique per case:

| Scenario | `Bundle.id` (template handle, fixed) | `Bundle.identifier.value` (per-case) | Composition.subject |
|----------|--------------------------------------|--------------------------------------|---------------------|
| GoodControl | `eicr-report-ChronicDSDiabetesPoorControl` | `urn:uuid:46a5fec8-872e-47fc-8a33-4bd660e591bb` | Patient/016788c3 |
| VAR_NUM (PoorControl) | `eicr-report-ChronicDSDiabetesPoorControl` | `urn:uuid:d26b2292-a18a-4e4a-bd9a-3f249ece5500` | Patient/b9a1b53d |

The same split holds for the `Composition` (GUID `id`, **plus** a distinct per-case
`Composition.identifier` UUID). So this is FHIR-correct generation, not a defect to report
upstream — the colliding `Bundle.id` is simply not the element that carries identity.

**Why MVP is safe as-designed**: D2 persists the message Bundle whole under its **wrapper
GUID** id; the fixed-id document Bundle is nested *content*, not a standalone server
resource, so no overwrite occurs and FR-019's guard never fires. Collection-bundle
resources are GUID-keyed (or identical shared refs), so no harmful clash there either.

**Decision (resolution + guardrail)**:
1. **Identity rule for the eICR document Bundle**: its identity is **`Bundle.identifier`**,
   never `Bundle.id`. Any future path that persists it as a standalone resource MUST upsert
   via **conditional update by identifier** —
   `PUT [base]/Bundle?identifier=urn:ietf:rfc:3986|<urn:uuid:…>` — which gives each case a
   distinct, idempotently-updatable server resource without ever touching the colliding id.
   It MUST **never** `PUT [base]/Bundle/eicr-report-ChronicDSDiabetesPoorControl` (that is
   the overwrite landmine), nor route the message through `$process-message`, without
   applying this rule.
2. **Generic guard (defense in depth)**: within a run, the processor **MUST detect** two
   resources sharing `(resourceType, id)` but differing in content and **fail loudly**
   (ERROR, do not silently overwrite) rather than let the last writer win (Principle V; see
   spec FR-019 / edge case). This catches the symptom even where the identity rule above
   has not (yet) been applied.
3. Identical-content collisions (the shared Practitioner/Org/Location, reused with the same
   GUID) are expected dedup and logged at most at DEBUG/INFO — not errors.

**Alternatives considered**:
- *Treat `Bundle.id` as the identity and namespace it per scenario (e.g., prefix with
  patient id)* — rejected: `Bundle.id` is not the identity element, so rewriting it both
  misframes the problem and breaks the relative references inside the message Bundle.
  Conditional-update-by-`identifier` is the FHIR-native answer.
- *Silently let PUT-by-id overwrite* — rejected: silent clinical data loss, violates
  Principle V.

## D5 — Software version source (confirms FR-006)

**Decision**: Derive the version at runtime from git:
`git describe --tags --always --dirty`, executed via `subprocess` against the repo
containing `process.py`. Fallback when git/metadata is unavailable: the literal
`unknown` (clearly-marked), logged at WARNING.

**Evidence**: `git describe --tags --always --dirty` currently returns `f0638c5` (no tags
yet → short commit). Once releases are tagged it returns e.g. `v1.2.0-3-gf0638c5` or
`v1.2.0`.

**Rationale**: Satisfies "version not hard-coded in config" (FR-006). Auto-tracks
releases. Stdlib-only (`subprocess`). The `software.version` field in
`config.example.json` becomes redundant and is removed (see D7).

**Alternatives considered**: VERSION file (extra bump step, less automatic); package
metadata (requires packaging the tool — overkill for a single script).

---

## D6 — FHIR server authentication

**Decision**: OAuth2 **client-credentials** grant. POST `grant_type=client_credentials`
(+ `client_id`/`client_secret`) to `config.server.token_endpoint` using
`urllib.request`; cache the bearer token in memory for the run; send
`Authorization: Bearer <token>` on every FHIR call. Refresh on `401`.

**Rationale**: Matches the `token_endpoint` / `client_id` / `client_secret` fields in
`config.example.json` and the constitution's Secret Protection section. Stdlib-only.

**Alternatives considered**: SMART backend services (JWT assertion) — not indicated by
the example config; revisit if the destination requires it.

---

## D7 — Config schema reconciliation

**Decision**: Update `config.example.json` to (a) **remove** `software.version` (now
git-derived, D5) and (b) **add** the IG version block required by constitution
Principle II (IG version tracking). Keep `software.identifier_system`/`identifier_value`
(used as a stable system identifier) and the `server` block. Validate required fields at
startup with field-specific error messages (FR-010); reject if values are still the
example placeholders (e.g., `YOUR_CLIENT_ID`) so a misconfigured run cannot silently hit
an unintended target (FR-010 / US3 scenario 3).

Proposed `config.example.json` shape (final wording in implementation):

```json
{
  "software": {
    "name": "ecr-fhir-processor",
    "identifier_system": "urn:oid:2.16.840.1.113883.3.2",
    "identifier_value": "ecr-fhir-processor"
  },
  "server": {
    "base_url": "YOUR_FHIR_SERVER_URL",
    "token_endpoint": "YOUR_TOKEN_ENDPOINT",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET"
  },
  "ig_versions": {
    "hl7.fhir.us.core": "6.1.0",
    "hl7.fhir.us.qicore": "4.1.1",
    "hl7.fhir.us.cqfmeasures": "3.0.0",
    "hl7.fhir.us.davinci-deqm": "5.0.0",
    "hl7.fhir.us.ecr": "2.1.2",
    "hl7.fhir.us.ph-library": "2.0.0"
  },
  "paths": {
    "input_dir": "input",
    "output_dir": "output",
    "log_dir": "log"
  }
}
```

**Rationale**: Config-over-code (constitution). IG versions as named config values
(Principle II "IG Version Tracking"). `paths` makes input/output/log locations
configurable while defaulting to the root dirs; a CLI flag may override `input_dir` for
ad-hoc runs.

> **Update (2026-06-12 — supersedes the earlier `TODO_PIN` draft above):** the IG set was
> pinned to exactly what the test-data supplier validates against, all resolvable from
> `packages.fhir.org`: `hl7.fhir.us.core#6.1.0`, `hl7.fhir.us.qicore#4.1.1`,
> `hl7.fhir.us.cqfmeasures#3.0.0`, `hl7.fhir.us.davinci-deqm#5.0.0`, `hl7.fhir.us.ecr#2.1.2`,
> `hl7.fhir.us.ph-library#2.0.0` (validator v6.9.9, Java 17, FHIR R4). The **APHL chronic-ds
> IG is intentionally NOT pinned**: `cqf.aphl.chronic-ds#0.0.002` is an unpublished draft
> available only as a `build.fhir.org` CI tarball (not resolvable from `packages.fhir.org`),
> the supplier itself does not validate against it, and the fixtures'
> `…/Measure/…|0.0.002` canonical references resolve to **warnings, not errors** without it
> (acceptable under Principle II). See `known-validation-issues.md` → "Pinned IG set" for the
> authoritative rationale and the delta-vs-baseline gate that absorbs those warnings.

**Alternatives considered**: hard-coding IG versions in `process.py` — rejected by
Principle II (must be config/constants, not buried); the script will read them from
config and expose them as constants for the validator invocation.

---

## D8 — Failure handling & exit semantics (confirms FR-011/012/014)

**Decision**:
- Malformed/unreadable input file → log WARNING, skip file, increment `skipped`,
  continue.
- Server rejects a **single resource** (non-2xx on its `PUT`) → log ERROR with the server
  `OperationOutcome`, increment `failed` for that resource, do **not** count it as
  persisted, and **continue with the remaining resources** — siblings are not rolled back
  (independent persistence, D2; amended Principle V). There is no all-or-nothing transaction
  whose rejection fails an entire scenario.
- When a non-atomic `batch` Bundle is used as the round-trip optimization (D2), failures are
  read **per entry** from the batch-response Bundle (each entry's status), not as a single
  bundle-level outcome.
- A resource type the operator deliberately deferred via `--skip-types` (D10) is counted
  `skipped`, not `failed`.
- Exit code: `0` only if `failed == 0`; otherwise non-zero. A run that processed nothing
  (empty input, or everything skipped) exits `0` and reports what was skipped.

**Rationale**: Loud-not-silent and failure-isolated (amended Principle V); reflects failures
in exit status (FR-012, FR-014) without letting one bad resource block the rest.

---

## D9 — Output mirror & logging

**Decision**: Optionally write the exact submitted JSON (post-stamp, pretty-printed) to
`output/{measure}/{YYYY-MM-DD}/` for human inspection (constitution: Clear, Predictable
Output). Log to console + `log/ecr-fhir-processor_{timestamp}.log` (Python `logging` with
two handlers). The `{YYYY-MM-DD}` is the processing/reporting date.

**Rationale**: Matches the constitution's output-organization and dual-logging rules and
aids troubleshooting of what was actually sent.

---

## D10 — Independent, selectable persistence by resource type (constitution v1.1.0 Principle V)

**Decision**: Persistence is runnable **per resource type / kind** so a problem type can be
landed separately. Add CLI filters `--only-types` / `--skip-types` (comma-separated FHIR
resourceTypes; also accept the kind alias `measure-report`). Default (neither flag): persist
everything.

**Driving case**: The test **MeasureReports currently fail Aidbox validation**. The operator
runs `--skip-types MeasureReport` first to land all conformant resources, then — after the
Aidbox validation profile is relaxed (may require a server restart) — runs
`--only-types MeasureReport` to land just those. Because every write is an idempotent
`PUT`-by-id (D1) and nothing is wrapped in a shared transaction (D2), the second run neither
duplicates nor rolls back the first run's resources.

**Rationale**: Directly realizes amended Principle V (independent, isolated, re-runnable
persistence per type). Keeps the conformant majority flowing while a single type is worked
out of band.

**Alternatives considered**:
- *Hard-code skipping MeasureReports* — rejected: config-over-code; the relaxation is a
  temporary, operator-driven condition, not a permanent code rule.
- *One `transaction` with a "continue on error" mode* — not a standard FHIR transaction
  option; the non-atomic `batch` (D2) already gives per-entry isolation, and per-type runs
  give the operator explicit control over ordering.

---

## Summary of decisions

| ID | Decision |
|----|----------|
| D1 | Retain original GUID `resource.id`; PUT (update-in-place) |
| D2 | Persist contained resources as **independent** `PUT`s per resource (non-atomic `batch` OK; **no** `transaction`); MeasureReport & message Bundle PUT by id — each an isolated unit of work (Principles VI + V) |
| D2b | **Promote the nested eICR `Composition`** to a first-class resource (`PUT [base]/Composition/<GUID id>`) in addition to the message Bundle; promote **only** the Composition (no fidelity regression on the clean collection-Bundle resources) (Principle VI) |
| D3 | Don't rewrite references; warn on non-target absolute refs (and on any unresolved promoted-Composition ref) |
| D4 | Provenance via searchable `meta.tag` (processed-by+version / processed-on / source-file) + `meta.source` |
| D4b | The nested eICR document Bundle's fixed `Bundle.id` (`eicr-report-ChronicDSDiabetesPoorControl`) is a template handle, **not** identity — identity is per-case `Bundle.identifier`. Any standalone persist MUST upsert via conditional-update-by-`identifier`, never PUT-by-id. Generic guard: detect same-`(type,id)`/differing-content collisions and fail loudly |
| D5 | Version from `git describe --tags --always --dirty`; fallback `unknown` |
| D6 | OAuth2 client-credentials, stdlib `urllib`, in-memory token |
| D7 | Reconcile `config.example.json`: drop `software.version`, add `ig_versions` + `paths`; reject placeholders |
| D8 | Warn-skip malformed; fail-loud on rejection **per resource** (isolated, no sibling rollback); non-zero exit on any failure |
| D9 | Output mirror by measure/date; dual console+file logging |
| D10 | **Independent, selectable persistence by type** via `--only-types`/`--skip-types`, so MeasureReports can be landed in a separate run after Aidbox validation is relaxed (Principle V) |

All spec NEEDS-CLARIFICATION / Open Questions are resolved. Ready for Phase 1.

> **Spec follow-up (not blocking this plan):** D2b (Composition promotion) and D2/D10
> (independent per-type persistence) extend beyond the requirements written in `spec.md`
> (which stops at FR-019 / OQ-1, OQ-2). They are mandated by the amended constitution
> (v1.1.0, Principles VI + V). Run `/speckit-specify` to formalize them as explicit
> functional requirements (e.g., an FR for first-class Composition promotion and an FR for
> independent, isolated, re-runnable per-type persistence) so the spec and plan re-converge.
