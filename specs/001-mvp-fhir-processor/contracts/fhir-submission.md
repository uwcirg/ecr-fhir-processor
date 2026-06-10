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

## Persistence by input kind (D1, D2)

### Collection Bundle → transaction
```text
Transform: type="transaction"; each entry gets
  request = { method: "PUT", url: "<ResourceType>/<id>" }
  (resource.meta stamped first)
POST {server.base_url}
Content-Type: application/fhir+json
Body: the transaction Bundle
Expect: 200 with a transaction-response Bundle (all entries 200/201).
```

### MeasureReport (standalone)
```text
PUT {server.base_url}/MeasureReport/{id}
Content-Type: application/fhir+json
Body: stamped MeasureReport
Expect: 200 (updated) or 201 (created).
```

### eCR message Bundle
```text
PUT {server.base_url}/Bundle/{id}
Content-Type: application/fhir+json
Body: message Bundle with stamped meta
Expect: 200 or 201.
```

## Semantics & invariants

- **SUB-1 (FR-016)**: All writes are PUT-by-id (update-in-place). Re-running identical
  input produces no new resources (SC-008).
- **SUB-2 (FR-017)**: `resource.id` retained → relative references resolve. References
  are never rewritten (D3). Absolute references to a non-target host are logged WARNING,
  not mutated.
- **SUB-3 (FR-012)**: Non-2xx → log ERROR including the server `OperationOutcome`; the
  affected resource(s) counted `failed`, never `succeeded`. A rejected transaction fails
  all of its resources (server-atomic).
- **SUB-4**: `Accept: application/fhir+json` on all requests; request/response status and
  any `OperationOutcome` recorded in the audit log (FR-013).
- **SUB-5 (--dry-run)**: All transforms/stamping run, but no token request and no
  submission occur; the would-be requests are logged.

## Acceptance checks

- **AC-1 (SC-001)**: Every present input bundle yields a submission attempt with a
  recorded outcome.
- **AC-2 (SC-008)**: Two consecutive runs of unchanged input leave the same resource
  count on the server; only provenance + server-managed metadata differ.
- **AC-3 (SC-006)**: Unreachable server / rejected submission / missing config never
  reports success → clear message + non-zero exit.
