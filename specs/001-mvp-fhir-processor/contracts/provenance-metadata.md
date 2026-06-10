# Contract: Provenance Metadata (searchable)

Defines exactly what the processor writes into `resource.meta` and how an operator
filters on it. This is the externally-observable contract behind FR-004/FR-005 and
SC-002/003/004.

## What is written

For every persisted resource (and for a message Bundle, on the Bundle's own `meta`):

| Slot | Field | Value |
|------|-------|-------|
| Identity + version | `meta.tag[]` | `system = <BASE>/processed-by`, `code = ecr-fhir-processor`, `version = <git version>`, `display = "Processed by ecr-fhir-processor <git version>"` |
| Processing time | `meta.tag[]` | `system = <BASE>/processed-on`, `code = <ISO-8601 instant with offset>` (run-constant) |
| Source file | `meta.tag[]` | `system = <BASE>/source-file`, `code = <source .json basename>` |
| Source uri | `meta.source` | `<BASE>/processed-by#<git version>` |

`<BASE>` = `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem` (provisional canonical
host — confirm before publishing; stable constant in `process.py`).

## Invariants

- **INV-1**: `processed-on` is identical across all resources of a single run.
- **INV-2**: Stamping is idempotent — on re-run, this processor's own tags (matched by
  `system`) are replaced, not appended; no tag accumulation (supports SC-008).
- **INV-3**: Pre-existing `meta.tag` from other systems and `meta.profile` are preserved
  (FR-002, FR-015). Clinical content is never altered.
- **INV-4**: `processed-on` includes a timezone offset (FR-007).
- **INV-5**: `version` reflects the actual running git version, never a config value
  (FR-006).

## How the operator filters (server search)

| Goal | Query |
|------|-------|
| All resources this software wrote (per type) | `GET [base]/Patient?_tag=<BASE>/processed-by|ecr-fhir-processor` |
| A specific processing run | `GET [base]/Patient?_tag=<BASE>/processed-on|2026-06-09T14:03:22+00:00` |
| Everything from one source file | `GET [base]/Patient?_tag=<BASE>/source-file|CMS165_bulk_dial_high_00042.json` |
| Combine across types | repeat the `_tag` filter on each resource type of interest |

## Acceptance checks (map to Success Criteria)

- **AC-1 (SC-004)**: 100% of persisted resources carry all three tags + `meta.source`.
- **AC-2 (SC-002)**: A `_tag=…|ecr-fhir-processor` search returns this processor's
  resources and excludes unrelated ones.
- **AC-3 (SC-003)**: A `_tag` filter on `processed-on` narrows results to a single run.
- **AC-4 (US2-5)**: The `source-file` tag lets any persisted resource be traced to its
  origin file.
