# Contract: FHIR Submission

Defines how the processor authenticates and persists each input kind. Behind FR-002,
FR-009, FR-016, FR-017, FR-012.

## Authentication (D6)

OAuth2 **client-credentials**:

```text
POST {server.token_endpoint}
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials&client_id={id}&client_secret={secret}
→ { "access_token": "...", "token_type": "Bearer", "expires_in": N }
```

- Bearer token cached in memory for the run; sent as `Authorization: Bearer <token>` on
  all FHIR requests.
- On `401`, refresh once and retry; a second `401` → fail that submission (ERROR).

## Persistence by input kind (D1, D2, D2b)

> **No global transaction (D2, constitution Principle V).** Multi-resource persistence is
> performed as **independent `PUT`s** — each resource is its own request and its own
> outcome. A non-atomic `batch` Bundle MAY be used as a round-trip optimization (it keeps
> per-entry isolation); a `transaction` Bundle MUST NOT be used (it reintroduces
> all-or-nothing rollback).

### Collection Bundle → independent PUTs (one per contained resource)
```text
For each entry.resource (subject to the type filter, --only-types/--skip-types):
  stamp(resource.meta)
  PUT {server.base_url}/{resourceType}/{id}
  Content-Type: application/fhir+json
  Expect: 200 (updated) or 201 (created), evaluated PER RESOURCE.
# Optional optimization: one non-atomic `batch` Bundle whose entries each carry
#   request = { method: "PUT", url: "<ResourceType>/<id>" }; read per-entry status from
#   the batch-response Bundle. NEVER type="transaction".
```

### MeasureReport (standalone)
```text
PUT {server.base_url}/MeasureReport/{id}
Content-Type: application/fhir+json
Body: stamped MeasureReport
Expect: 200 (updated) or 201 (created).
# Often deferred to a separate run via --only-types/--skip-types (D10): Aidbox currently
# rejects the test MeasureReports until its validation profile is relaxed.
```

### eCR message Bundle (+ promoted Composition, D2b)
```text
PUT {server.base_url}/Bundle/{id}                # wrapper GUID; stamped meta
Content-Type: application/fhir+json
Expect: 200 or 201.

# Then promote the nested eICR Composition as its own first-class resource:
PUT {server.base_url}/Composition/{composition.id}   # per-case GUID (D4b-safe)
Body: stamped Composition extracted from the nested document Bundle
Expect: 200 or 201.
# Promote ONLY the Composition. Do NOT re-persist the eICR's other nested clinical copies
# (lower-fidelity duplicates of the authoritative collection-Bundle resources). The
# MessageHeader stays nested.
```

## Semantics & invariants

- **SUB-1 (FR-016)**: All writes are PUT-by-id (update-in-place). Re-running identical
  input produces no new resources (SC-008).
- **SUB-2 (FR-017)**: `resource.id` retained → relative references resolve. References
  are never rewritten (D3). Absolute references to a non-target host — and any promoted
  Composition reference that does not resolve to a persisted resource — are logged WARNING,
  not mutated.
- **SUB-3 (FR-012, amended Principle V)**: Non-2xx → log ERROR including the server
  `OperationOutcome`; the affected **resource** is counted `failed`, never `succeeded`.
  Failures are **isolated per resource** — a rejected resource does NOT roll back or block
  its siblings (no atomic transaction). With a `batch`, outcomes are read per entry.
- **SUB-4**: `Accept: application/fhir+json` on all requests; request/response status and
  any `OperationOutcome` recorded in the audit log (FR-013).
- **SUB-5 (--dry-run)**: All transforms/stamping/extraction run, but no token request and no
  submission occur; the would-be requests (including the promoted Composition PUT) are logged.
- **SUB-6 (D10, Principle V)**: `--only-types`/`--skip-types` select which resourceTypes are
  PUT this run; excluded resources are counted `skipped` (not `failed`). Re-running a deferred
  type later (idempotent PUT-by-id) neither duplicates nor rolls back already-persisted
  resources.

## Acceptance checks

- **AC-1 (SC-001)**: Every present input resource (subject to the type filter) yields a
  submission attempt with a recorded per-resource outcome.
- **AC-2 (SC-008)**: Two consecutive runs of unchanged input leave the same resource
  count on the server; only provenance + server-managed metadata differ.
- **AC-3 (SC-006)**: Unreachable server / rejected submission / missing config never
  reports success → clear message + non-zero exit.
- **AC-4 (D2, Principle V)**: A run where one resource type (e.g., MeasureReport) is rejected
  still persists the other types successfully; only the rejected resources are counted
  `failed`.
- **AC-5 (D2b, Principle VI)**: After persisting an in-population scenario, the eICR
  `Composition` is independently retrievable at `[base]/Composition/{id}`, and the
  authoritative collection-Bundle clinical resources are unchanged by the promotion (no
  lower-fidelity overwrite).
