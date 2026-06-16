# Phase 0 Research: Filter Analytics by CMS Measure

**Feature**: `003-cms-measure-filter` | **Spec**: [spec.md](./spec.md) | **Constitution**: v1.2.0

All Technical-Context unknowns were resolvable from the existing codebase (`process.py`
stamping, `viewdefinitions/patient.ViewDefinition.json`) plus the constitution. No
`NEEDS CLARIFICATION` remains. Decisions R1–R7 below.

---

## R1 — Where does the CMS code get derived, and does it need new function signatures?

**Decision**: Derive the CMS code with a single pure helper
`cms_measure_from_filename(filename: str) -> str` and call it **inside the existing
`stamp()`** (`process.py:164`), which already receives `source_filename`. No new parameter is
threaded through `Pipeline.process` → `_process_*` → `_stamp` → `stamp_resource` → `stamp`.

**Rationale**: The CMS code is a *pure function of the filename*, and `stamp()` already has the
filename. Deriving it there is maximally DRY and touches the fewest call sites — consistent
with the existing `source-file` tag, which is likewise built from `source_filename` inside
`stamp()`. Threading a new `cms_measure` argument through five function signatures would be
strictly more code for the same result.

**Alternatives considered**:
- *Add a `cms_measure` field to `InputFile` and thread it through the pipeline* (parallel to
  `measure`/`population`). Rejected: more signature churn, and the value is recomputable from
  the filename `stamp()` already holds. The one thing that genuinely needs the directory slug —
  the disagreement warning (R3) — is handled separately in `discover_inputs`, which already has
  both values.
- *Compute it in `discover_inputs` only and pass it down*. Rejected for the same threading cost;
  `discover_inputs` still computes it (for R3's warning) but does not need to pass it onward.

---

## R2 — Derivation rule (what counts as a CMS token; normalization)

**Decision**: Match a leading token `^CMS\d+` **case-insensitively** against the bare filename
and normalize to uppercase `CMS<digits>` (e.g. `cms165_x.json` → `CMS165`,
`CMS2_bulk.json` → `CMS2`). Take the leading digit run only (greedy `\d+` up to the first
non-digit). Anything not matching the leading pattern → the sentinel `unknown`. Implemented
with stdlib `re` (zero new dependency).

**Rationale**: The fixtures use a variable-length CMS number followed by `_`
(`CMS165_bulk_nip_late_htn_00500.json`, `CMS122_*`, future `CMS2_*`). A fixed-width parse
would break across `CMS2` vs `CMS165`. Anchoring at the start (`^`) and requiring `CMS` + at
least one digit avoids false positives like `CMSReport_…` or `CMSX_…` (those → `unknown`).
Case-folding + uppercase normalization (FR-006) guarantees one canonical code per measure so a
downstream `= 'CMS165'` predicate matches every row for that measure.

**Alternatives considered**:
- *`str.split('_')[0]`*. Rejected: fragile on filenames using other separators or none
  (`CMS165.json`), and it would accept `CMSX` as a "code".
- *Require an exact enum membership (`CMS2|CMS122|CMS165`) and else `unknown`*. Rejected:
  too strict — a correctly-formed but not-yet-enumerated measure (e.g. a 4th CMS measure added
  later) would silently fall to `unknown`. The pattern accepts any well-formed `CMS<n>`; the
  enumerated set lives in the slug map (R4) for the disagreement check and documentation, not
  as a gate on stamping. (See R7 for why a well-formed-but-unmapped code is still tagged as-is.)

---

## R3 — Directory/filename disagreement handling (FR-007)

**Decision**: In `discover_inputs` (which already derives the directory slug `measure` and has
`path.name`), when the filename yields a **concrete** CMS code that maps to a *different* slug
than the directory slug, log one WARNING per file naming both values. The filename code is
authoritative for the tag. A filename that yields `unknown` does **not** trigger the warning
(it is "couldn't determine", not a contradiction).

**Rationale**: Constitution Principle V requires every data-quality accommodation be logged at
WARNING+, and never silently reconciled. A `CMS122_*` file sitting under `controllable-bp/`
(CMS165) is a mislabeled fixture/input worth surfacing. Restricting the warning to
*concrete-code-vs-concrete-slug* mismatches keeps it signal, not noise: `unknown` under a
measure folder is the expected production shape (filename can't be determined) and shouldn't
spam warnings. One warning per *file* (in discovery), not per *resource* (in stamping), avoids
N duplicate lines for an N-resource bundle.

**Alternatives considered**:
- *Warn on any difference including `unknown` vs a slug*. Rejected: noisy for the normal
  production case where files aren't measure-foldered and/or lack the prefix.
- *Reconcile by trusting the directory*. Rejected: violates the spec's single-source-of-truth
  decision (filename wins) and Principle V (no silent correction).

---

## R4 — CMS code ↔ slug mapping: one authoritative location (FR-010)

**Decision**: A single module-level constant dict in `process.py`, e.g.
`MEASURE_SLUG_BY_CMS = {"CMS2": "depression-screening", "CMS122": "poor-diabetic-control",
"CMS165": "controllable-bp"}` (with the inverse derived from it), is the one authoritative
crosswalk. The disagreement check (R3) and any docs reference it; the `--measure` help text and
README enumerate the same slugs but the dict is the source of truth.

**Rationale**: FR-010 requires code and slug not drift independently. The slugs already appear
as bare strings in `process.py` (`--measure` help) and `README.md`; centralizing the crosswalk
in one constant is the DRY fix. It aligns 1:1 with constitution Principle IV's named measures.

**Alternatives considered**:
- *Hardcode the mapping inline at each use site*. Rejected: that is the drift FR-010 forbids.
- *A separate config/JSON file*. Rejected: over-engineered for three stable, constitution-named
  measures; a code constant is simpler and stays stdlib-only (Principle I).

---

## R5 — Persisting the CMS measure as its own `meta.tag` system (FR-002) + idempotency (FR-005)

**Decision**: Add a new tag system constant
`SYSTEM_CMS_MEASURE = f"{PROVENANCE_BASE}/cms-measure"` and append a
`{"system": SYSTEM_CMS_MEASURE, "code": <CMS code or "unknown">}` tag in `stamp()`. Add
`SYSTEM_CMS_MEASURE` to the existing `OWN_TAG_SYSTEMS` frozenset so the idempotent re-stamp
("drop only our own prior tags") replaces it in place rather than appending a duplicate.

**Rationale**: This is the established pattern — `source-file`, `processed-by`, `processed-on`
are all project-owned `meta.tag` systems under `PROVENANCE_BASE`, replaced idempotently via
`OWN_TAG_SYSTEMS`. The CMS-measure tag is one more entry in exactly that mechanism, so FR-005
(idempotent, no duplicate tag, re-attribute on rename — US3) falls out for free. A dedicated
system (not piggybacking on `source-file`) lets a ViewDefinition/`_tag` query filter on
`(system, code)` directly (FR-008), the same way the Patient view already filters on
`processed-by` (002 FR-013).

**Alternatives considered**:
- *Encode CMS in the existing `source-file` tag and parse downstream*. Rejected in the spec
  (Clarifications): brittle SQL string-parsing, not how ViewDefinition selection works.
- *Use a FHIR `meta.tag` Coding with a `display`*. Optional nicety; deferred. The
  `(system, code)` pair is what filters; a `display` (e.g. the slug) MAY be added but is not
  required by any FR. Decision: include a `display` set to the human slug for the concrete
  codes (cheap, aids debugging), `display: "unknown measure"` for the sentinel — derived from
  the same R4 map. (Kept additive; does not affect filtering.)

---

## R6 — `unknown` sentinel: project code vs. HL7 DataAbsentReason; need for a CodeSystem resource

**Decision**: Use a **positive sentinel `unknown` within the project-owned
`…/CodeSystem/cms-measure` system** (spec Clarifications, recommended option 1). Do **not**
author a published `CodeSystem` resource; document the enumerated value set
(`CMS2 | CMS122 | CMS165 | unknown`, plus the open `CMS<n>` form) in the contract and as code
constants.

**Rationale**: The project's existing tag systems (`source-file`, `processed-by`,
`processed-on`) are provisional URL constants with **no checked-in `CodeSystem` resource**
(confirmed: zero `"resourceType":"CodeSystem"` files in the repo). Authoring one now for
`cms-measure` only would be inconsistent and out of scope. A positive `unknown` in the same
system keeps all measure filtering on one `(system, code)` axis and lets analysts *list/count*
un-attributed resources (`code = 'unknown'`) rather than writing a NOT-EXISTS over absent tags.

**Alternatives considered**:
- *HL7 DataAbsentReason `unknown`
  (`http://terminology.hl7.org/CodeSystem/data-absent-reason#unknown`)*. A defensible
  standards-purist choice, but it splits measure filtering across two systems (the analyst must
  query "cms-measure = X OR data-absent-reason = unknown"). Recorded as the documented
  alternative if cross-system standardization is later prioritized.
- *Omit the tag when unknown*. Rejected (spec): makes "find the un-attributed" a NOT-EXISTS
  query and removes the positive bucket the production workflow (US3) needs to find and
  re-attribute.

---

## R7 — Surfacing CMS measure in the Patient ViewDefinition (FR-009)

**Decision**: Add one column to `viewdefinitions/patient.ViewDefinition.json`:
`{ "name": "cms_measure", "path": "meta.tag.where(system =
'https://uwcirg.github.io/ecr-fhir-processor/CodeSystem/cms-measure').code.first()", "type":
"code" }`. Do **not** add a `where` filter on measure (the column lets the analyst filter to any
single measure with one predicate; a server-side filter would hard-wire one measure and defeat
the point). Do **not** create per-measure views.

**Rationale**: FR-009 + SC-003 want "one predicate filters the flattened view to a single
measure". A selectable column (`WHERE cms_measure = 'CMS165'`) delivers exactly that while
keeping a single view (DRY, constitution Principle VII's demand-driven rule). The `.first()`
keeps one row per patient (a resource carries exactly one cms-measure tag, so `.first()` is a
safe single-valued reducer consistent with the view's existing `.first()` idiom). Reading the
tag via the same `meta.tag.where(system=…)` FHIRPath the view already uses for the `processed-by`
`where` filter means no new dialect risk.

A well-formed-but-not-enumerated `CMS<n>` (R2) flows through as its own column value — the view
does not gate on the enumerated set, so a future measure appears immediately without a view
edit. Other resource types are not given views (Principle VII, demand-driven); their resources
still carry the tag for `_tag` filtering (FR-008).

**Alternatives considered**:
- *A measure `where` filter or per-measure views*. Rejected: one predicate on a column is
  simpler, keeps one materialized view, and matches the analyst's "filter to any measure" need.

---

## Cross-cutting: validation & test strategy (Principles II & III)

- The cms-measure tag is **additive** to `meta.tag`; it does not alter `meta.profile` or any
  clinical element, so it cannot introduce HL7-validator *errors* (an unknown tag CodeSystem
  yields at most warnings, which are acceptable per Principle II). The feature-001 validation
  pipeline MUST still be re-run after the change (Principle III, LLM Development Validation) to
  confirm zero new errors.
- Pure logic (`cms_measure_from_filename`, the disagreement decision, the idempotent re-stamp
  including the new tag) is covered by stdlib `unittest` (new `tests/test_cms_measure.py`),
  matching the existing `tests/test_provenance.py` style. The ViewDefinition column is covered
  by extending `tests/test_viewdefinition.py` (JSON parses; `cms_measure` column present with
  the expected system in its `path`).
- The authoritative gate for the ViewDefinition change is Aidbox acceptance on `PUT` +
  `$materialize` (002 R5); the e2e is folded into this feature's quickstart.
