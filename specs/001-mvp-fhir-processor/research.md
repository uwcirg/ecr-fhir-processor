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

## D2 — Persistence granularity (resolves OQ-2)

**Decision**: Persist the **contained resources** of each collection Bundle as
first-class resources, by converting the `collection` Bundle into a `transaction`
Bundle where each entry carries `request.method = PUT` and
`request.url = <ResourceType>/<id>`, then POSTing the transaction to `[base]`.

**Evidence**:

- Inter-resource references inside the collection bundle are **relative**:
  `Condition.subject → "Patient/4865655a-..."`, `Encounter.participant →
  "Practitioner/b2360d5d-..."`, etc.
- Collection bundles carry **no** `entry.request` and `type = "collection"` — they are
  not directly transactable as-is.

**Rationale**: For relative references to resolve on the target server, each referenced
resource must exist at `[base]/<Type>/<id>`. Converting to a transaction Bundle of PUTs
persists every contained resource at its retained id atomically, makes the relative
references resolve, and preserves update-in-place semantics. This honors the user's
"persist all input bundles" intent (nothing is dropped) while delivering the
individually-queryable resources the user anticipated wanting (spec OQ-2).

**Per input type**:
| Input file | type | Persistence action |
|------------|------|--------------------|
| Collection Bundle (`CMS*_*.json`) | `collection` | Convert → `transaction` of PUTs; stamp each entry resource; POST `[base]` |
| MeasureReport (`MeasureReport_*.json`) | individual | Stamp; PUT `[base]/MeasureReport/<id>` (or single-entry transaction) |
| eCR message Bundle (`Bundle_*.json`) | `message` | Stamp the Bundle's `meta`; PUT `[base]/Bundle/<id>` |

**Alternatives considered**:
- *Store the collection Bundle as one opaque `Bundle` resource* — rejected: relative
  references would not resolve to queryable resources; surveillance queries
  (e.g., find this run's Patients) would not work.
- *Submit the eCR message Bundle to `$process-message`* — deferred beyond MVP; that
  operation triggers message-processing workflows on the server we don't control. MVP
  persists it as a retrievable `Bundle` resource. (Revisit if the destination requires
  `$process-message` ingestion.)

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
    "hl7.fhir.us.ecr": "TODO_PIN",
    "hl7.fhir.us.core": "TODO_PIN",
    "hl7.fhir.us.davinci-deqm": "TODO_PIN",
    "aphl.chronic-ds": "0.0.002"
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
ad-hoc runs. The `aphl.chronic-ds` Measure canonicals are pinned at `0.0.002` per the
fixtures; the others carry `TODO_PIN` per the constitution's deferred-TODO note.

**Alternatives considered**: hard-coding IG versions in `process.py` — rejected by
Principle II (must be config/constants, not buried); the script will read them from
config and expose them as constants for the validator invocation.

---

## D8 — Failure handling & exit semantics (confirms FR-011/012/014)

**Decision**:
- Malformed/unreadable input file → log WARNING, skip file, increment `skipped`,
  continue.
- Server rejects a submission (non-2xx) → log ERROR with server `OperationOutcome`,
  increment `failed`, do **not** count as persisted.
- Transaction Bundle partial semantics: a `transaction` is atomic server-side; a 4xx/5xx
  means the whole bundle was rejected — count its resources as failed for that file.
- Exit code: `0` only if `failed == 0`; otherwise non-zero. A run that processed nothing
  (empty input) exits `0` and reports "nothing processed".

**Rationale**: Loud-not-silent (Principle V); reflects failures in exit status (FR-012,
FR-014).

---

## D9 — Output mirror & logging

**Decision**: Optionally write the exact submitted JSON (post-stamp, pretty-printed) to
`output/{measure}/{YYYY-MM-DD}/` for human inspection (constitution: Clear, Predictable
Output). Log to console + `log/ecr-fhir-processor_{timestamp}.log` (Python `logging` with
two handlers). The `{YYYY-MM-DD}` is the processing/reporting date.

**Rationale**: Matches the constitution's output-organization and dual-logging rules and
aids troubleshooting of what was actually sent.

---

## Summary of decisions

| ID | Decision |
|----|----------|
| D1 | Retain original GUID `resource.id`; PUT (update-in-place) |
| D2 | Persist contained resources via collection→transaction(PUT); MeasureReport & message Bundle PUT by id |
| D3 | Don't rewrite references; warn on non-target absolute refs |
| D4 | Provenance via searchable `meta.tag` (processed-by+version / processed-on / source-file) + `meta.source` |
| D4b | The nested eICR document Bundle's fixed `Bundle.id` (`eicr-report-ChronicDSDiabetesPoorControl`) is a template handle, **not** identity — identity is per-case `Bundle.identifier`. Any standalone persist MUST upsert via conditional-update-by-`identifier`, never PUT-by-id. Generic guard: detect same-`(type,id)`/differing-content collisions and fail loudly |
| D5 | Version from `git describe --tags --always --dirty`; fallback `unknown` |
| D6 | OAuth2 client-credentials, stdlib `urllib`, in-memory token |
| D7 | Reconcile `config.example.json`: drop `software.version`, add `ig_versions` + `paths`; reject placeholders |
| D8 | Warn-skip malformed; fail-loud on rejection; non-zero exit on any failure |
| D9 | Output mirror by measure/date; dual console+file logging |

All spec NEEDS-CLARIFICATION / Open Questions are resolved. Ready for Phase 1.
