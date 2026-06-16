# Phase 1 Data Model: Filter Analytics by CMS Measure

**Feature**: `003-cms-measure-filter` | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

This feature adds **one attribution tag** to the resources the processor already stamps and
**one column** to the Patient view. It introduces no new persisted resource type and no new
storage. The "entities" below are the CMS code, its tag carrier, the slug crosswalk, and the
view column.

---

## 1. CMS measure code (value)

The canonical attribution of a persisted resource to a CMS quality measure.

| Property | Value |
|----------|-------|
| Type | string |
| Concrete form | `CMS` + one or more digits, uppercase — `CMS2`, `CMS122`, `CMS165` (open-ended: any well-formed `CMS<n>`) |
| Sentinel | `unknown` (filename did not match the convention) |
| Source | Derived purely from the input filename (R1, R2) |
| Normalization | Match `^CMS\d+` case-insensitively on the bare filename; uppercase the matched `CMS`+digits (`cms165…` → `CMS165`). No leading match → `unknown` (FR-001, FR-006) |

**Derivation function** (pure; `process.py`, stdlib `re`):

```text
cms_measure_from_filename(filename: str) -> str
  match ^CMS(\d+) case-insensitively against the filename (basename)
  if match: return "CMS" + matched_digits          # already uppercase
  else:     return "unknown"
```

**Examples**

| Filename | Result | Note |
|----------|--------|------|
| `CMS165_bulk_nip_late_htn_00500.json` | `CMS165` | standard fixture |
| `CMS2_bulk_*.json` | `CMS2` | single-digit measure number |
| `CMS122_*.json` | `CMS122` | three-digit measure number |
| `cms165_x.json` | `CMS165` | case-normalized |
| `CMS165.json` | `CMS165` | digits terminated by `.` |
| `CMSX_x.json` | `unknown` | `CMS` not followed by a digit |
| `CMSReport_x.json` | `unknown` | non-numeric after `CMS` |
| `patient_export_2026.json` | `unknown` | no `CMS` prefix (production shape) |

---

## 2. CMS-measure tag (persisted carrier)

A `meta.tag[]` entry added by `stamp()` to **every resource the processor persists** (the same
set already receiving `source-file` — FR-003), alongside the existing provenance tags.

| Field | Value |
|-------|-------|
| `system` | `https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure` (new constant `SYSTEM_CMS_MEASURE`) |
| `code` | the CMS measure code from §1 (`CMS165` … or `unknown`) |
| `display` | the human slug for concrete codes (e.g. `controllable-bp`); `unknown measure` for the sentinel — derived from §3 (additive, does not affect filtering — R5) |

**Invariants**

- **INV-CMS-1 (uniform breadth, FR-003)**: present on exactly the resources that carry the
  `source-file` tag — no more, no fewer.
- **INV-CMS-2 (exactly one, FR-005 / SC-002)**: a resource carries exactly one cms-measure tag.
  Re-stamping replaces the prior one (system added to `OWN_TAG_SYSTEMS`), never appends.
- **INV-CMS-3 (additive, Principle II)**: adding the tag preserves `meta.profile`, other
  systems' tags, and all clinical content (extends the existing `stamp()` INV-2/INV-3).
- **INV-CMS-4 (canonical, SC-005)**: `code` is always a normalized `CMS<n>` or `unknown` — never
  a raw filename fragment or mixed case.

**Relationship to existing meta.tag entries** (after `stamp()`):

```text
meta.tag[]:
  { system: …/processed-by,  code: ecr-fhir-processor, version: <v>, display: … }   # 002 FR-013 filter
  { system: …/processed-on,  code: <ISO timestamp> }
  { system: …/source-file,   code: <full filename> }
  { system: …/cms-measure,   code: <CMS165 | unknown>, display: <slug | "unknown measure"> }  # NEW
meta.source: …/processed-by#<v>
```

---

## 3. CMS ↔ slug crosswalk (authoritative mapping, FR-010)

One module-level constant in `process.py`, the single source of truth (R4); aligns with
constitution Principle IV.

| CMS code | Slug | Measure |
|----------|------|---------|
| `CMS2` | `depression-screening` | Depression Screening *(in scope; no fixtures yet)* |
| `CMS122` | `poor-diabetic-control` | Diabetes HbA1c Poor Control (≥9%) |
| `CMS165` | `controllable-bp` | Controlling High Blood Pressure |

```text
MEASURE_SLUG_BY_CMS = {"CMS2": "depression-screening",
                       "CMS122": "poor-diabetic-control",
                       "CMS165": "controllable-bp"}
# inverse derived for the directory→code disagreement check (R3)
```

Used by: the §2 `display`, and the directory/filename disagreement check (§4). The `--measure`
help text and README enumerate the same slugs but defer to this constant as the source of truth.

---

## 4. Directory/filename disagreement signal (FR-007, transient — not persisted)

Computed once per file in `discover_inputs`; emits a WARNING, persists nothing.

| Input | Source |
|-------|--------|
| filename CMS code | `cms_measure_from_filename(path.name)` (§1) |
| directory slug | `measure` = first path segment under the input root (existing `discover_inputs` logic) |

**Rule (R3)**: WARN iff the filename code is **concrete** (not `unknown`) **and** the directory
slug maps (via §3) to a **different** concrete code. Filename `unknown` → no warning. The
filename code is authoritative for the tag regardless.

```text
file_code = cms_measure_from_filename(name)
dir_code  = inverse-map(measure_slug)            # None if slug unknown/absent
if file_code != "unknown" and dir_code is not None and file_code != dir_code:
    logger.warning("CMS measure mismatch for %s: filename=%s directory=%s (%s); "
                   "using filename.", name, file_code, dir_code, measure_slug)
```

Satisfies SC-006 (the mismatch is never silent) and Principle V (logged at WARNING).

---

## 5. Patient view column (analyst-facing, FR-009)

One new column appended to `viewdefinitions/patient.ViewDefinition.json` `select[0].column[]`.

| Column | FHIRPath | Type |
|--------|----------|------|
| `cms_measure` | `meta.tag.where(system = '…/CodeSystem/cms-measure').code.first()` | `code` |

- `.first()` keeps one row per patient (a resource has exactly one cms-measure tag — INV-CMS-2 —
  so `.first()` is a safe single-valued reducer; same idiom as the view's other `.first()` paths).
- No `where` filter on measure: the column lets the analyst filter to **any** single measure
  with one predicate (`WHERE cms_measure = 'CMS165'`) — SC-003 — while keeping one view (R7).
- Absent tag (e.g. a Patient persisted before this feature, not yet re-processed) → null column,
  not an error (consistent with FR-010 / the view's never-fabricate rule).

---

## Out of scope (explicit)

- No published `CodeSystem` resource for `cms-measure` (consistent with the existing
  provisional tag systems — R6).
- No new ViewDefinitions for other resource types (Principle VII, demand-driven); their
  resources carry the tag for `_tag` filtering only (FR-008).
- No change to persistence granularity, retained ids, the `output/{measure}/{date}/` mirror
  path (still directory-derived), or the `--measure` filter semantics.
