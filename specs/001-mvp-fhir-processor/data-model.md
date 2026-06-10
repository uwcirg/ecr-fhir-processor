# Data Model: MVP eCR FHIR Processor

**Phase 1 output.** Entities, the provenance-metadata model, and the input→submission
transforms. Field-level FHIR resource shapes are defined by the target IGs (see
constitution Principle II); this document covers only what the processor reads, derives,
and writes.

---

## Entities

### InputFile
A single `.json` file discovered under the input tree.
- `path` — absolute filesystem path.
- `filename` — basename (e.g., `CMS165_bulk_dial_high_00042.json`); stamped into
  provenance (D4).
- `measure` — derived from the path segment (`poor-diabetic-control` | `controllable-bp`
  | `depression-screening`).
- `population` — derived from path (`standard` | `not-in-population`).
- `kind` — classified on load: `collection-bundle` | `measure-report` | `message-bundle`
  | `unknown`.
- **Validation**: must parse as JSON and have a `resourceType`; otherwise → `unknown`,
  WARNING, skipped (D8).

### ScenarioFolder
A leaf directory holding the file(s) for one case.
- `measure`, `population`, `scenario_id` (folder name).
- `files[]` — the InputFiles within.
- Standard → collection Bundle + MeasureReport + message Bundle; Not-In-Population →
  collection Bundle + MeasureReport (per spec; not enforced — the processor handles
  whatever files are present).

### FhirResource (a single resource to be persisted)
- `resourceType`, `id` (**retained**, D1), `meta` (mutated additively, D4), body.
- **Identity rule (FR-016)**: persisted at `[base]/<resourceType>/<id>` via PUT.
- **Reference rule (FR-017, D3)**: relative references untouched; absolute non-target
  references untouched but WARNING-logged.

### ProvenanceStamp
The metadata applied to every persisted resource/bundle before submission. See the
[provenance-metadata contract](./contracts/provenance-metadata.md). Carries:
- processor identity (`ecr-fhir-processor`)
- software `version` (git-derived, D5)
- processing `timestamp` (ISO-8601 with offset, run-constant, FR-007)
- `sourceFilename`

### RunConfig
Parsed from `config.json` (template `config.example.json`, reconciled per D7).
- `software.name`, `software.identifier_system`, `software.identifier_value`
- `server.base_url`, `server.token_endpoint`, `server.client_id`, `server.client_secret`
- `ig_versions{}` (named IG → version; Principle II)
- `paths{ input_dir, output_dir, log_dir }`
- **Validation (FR-010)**: all `server.*` required and non-empty; reject values still
  equal to the example placeholders (`YOUR_*`); fail fast naming the offending field.

### RunSummary
Aggregate of one execution (FR-014).
- counts: `read`, `submitted`, `succeeded`, `failed`, `skipped`
- per-file outcomes: `{ filename, kind, action, resource_count, status, detail }`
- `exit_code`: `0` iff `failed == 0`.

### AuditLog
Console + `log/ecr-fhir-processor_{timestamp}.log` (D9). Records discovery, stamping,
submission requests/responses, warnings, and the final RunSummary.

---

## Provenance metadata model (D4)

Applied to `resource.meta` (additive; never replaces existing `tag`/`profile`):

```jsonc
"meta": {
  "profile": [ /* preserved as-is */ ],
  "source": "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by#<version>",
  "tag": [
    /* ...any pre-existing tags preserved... */
    {
      "system":  "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-by",
      "code":    "ecr-fhir-processor",
      "version": "<git version>",
      "display": "Processed by ecr-fhir-processor <git version>"
    },
    {
      "system": "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/processed-on",
      "code":   "2026-06-09T14:03:22+00:00"
    },
    {
      "system": "https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/source-file",
      "code":   "CMS165_bulk_dial_high_00042.json"
    }
  ]
}
```

**Invariants**
- The `processed-on` value is identical for every resource in a single run.
- Stamping is idempotent: re-stamping replaces this processor's own prior tags (matched
  by `system`) rather than appending duplicates, so re-runs don't accumulate tags.
- Existing tags from other systems and `meta.profile` are preserved (FR-002, FR-015).

---

## Input → Submission transforms (D2)

```text
collection Bundle ──► transaction Bundle
  for each entry e:
    stamp(e.resource)
    e.request = { method: "PUT", url: f"{e.resource.resourceType}/{e.resource.id}" }
  bundle.type = "transaction"
  POST [base]  (atomic)

MeasureReport (standalone) ──► stamp ──► PUT [base]/MeasureReport/{id}
                                          (or single-entry transaction)

message Bundle ──► stamp(bundle.meta) ──► PUT [base]/Bundle/{id}
```

**Notes**
- The nested eICR document bundle inside a message Bundle is persisted as part of the
  message Bundle resource (not separately unpacked in MVP); its relative references
  resolve to the resources already persisted from the sibling collection Bundle (same
  retained GUIDs).
- A transaction is server-atomic: any entry failure rejects the whole bundle → that
  file's resources are counted `failed` (D8).

---

## State / lifecycle of a file through a run

```text
discovered → classified(kind) → [unknown? → skip+WARN]
          → parsed → stamped → transformed(by kind) → submitted
          → server 2xx? → succeeded : failed(+ERROR, OperationOutcome logged)
          → (optional) mirrored to output/{measure}/{date}/
```

Re-run of identical input: every resource PUT to the same id → updated in place; only the
ProvenanceStamp (new `processed-on`/`version` if changed) and server-managed
`meta.lastUpdated`/`versionId` differ (FR-016, SC-008).
