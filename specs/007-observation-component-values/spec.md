# Feature Specification: Surface Component & Coded Measurements in the Observation View

**Feature Branch**: `007-observation-component-values`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "The analytics team wants to see more fields in the Observation ViewDefinition. Specifically: 'Looking at the observations file, there are lines for \"Blood pressure panel with all children optional\" but none of them have recorded measurements in any of the other columns'. Indeed, I see that for that example we are missing the Diastolic and Systolic values for this example. Have a look at our test data to see how to pull this, and how to make it extensible to other types of Observations present in the test data."

## Overview

The analytics Observation view currently produces **one row per Observation** with a single set of
value columns that only read a measurement stored **at the top level** of the Observation (a scalar
quantity, a coded value, or a string). For **panel Observations** — where the actual measurements
live in the Observation's nested per-measurement parts rather than at the top level — every value
column comes back empty. In the test data the clearest case is **"Blood pressure panel with all
children optional"**: its Systolic and Diastolic readings are recorded as nested parts, so the row
shows the Observation exists but reports no numbers.

This feature makes the Observation view surface those nested panel measurements (Systolic and
Diastolic for blood-pressure panels) **as columns on the same one-row-per-Observation row**, and
does so with an approach that generalizes to the other Observation shapes present in the test data
so the analytics team is not left with silently-empty rows for measured observations.

## Clarifications

### Session 2026-07-07

- Q: How should nested panel measurements (US1/P1) be represented — generic row-per-component, type-specific named columns (e.g. `systolic_*`), or something else? → A: Add **two generic component triads**. Each triad is `component_display` + `component_value` (numeric) + `component_unit`, sourced positionally from the Observation's nested parts (first part → triad 1, second part → triad 2). Columns are **not** named for a specific Observation type; the `component_display` column identifies each measurement (e.g. "Systolic blood pressure" / "Diastolic blood pressure"). These columns are expected to be empty for the many Observations that carry no nested parts.
- Q: How should the scalar-quantity (`valueQuantity`) case be accommodated? → A: No change — the existing top-level value + unit columns already cover it.
- Q: How should the coded-result (`valueCodeableConcept`) case be accommodated? → A: Keep the existing coded value (the code, already present) and **add the coded value's human-readable display** alongside it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See blood-pressure panel readings (Priority: P1)

An analyst querying the Observation view for blood-pressure panel Observations can read the actual
Systolic and Diastolic values (and their units) for each such Observation, instead of seeing a row
whose measurement columns are all empty.

**Why this priority**: This is the reported gap. Blood pressure is a core measure input
(controllable-BP scenario) and today the analytics team sees the Observation exists but cannot see
what the reading was — the data is effectively invisible for analysis. Fixing this delivers the
requested value on its own.

**Independent Test**: Publish/materialize the Observation view against a server holding the
processed fixtures, query the rows for the "Blood pressure panel with all children optional"
Observations, and confirm each row now reports a Systolic value + unit and a Diastolic value + unit
matching the source Observation (e.g. 128 mmHg / 88 mmHg for the not-in-population controllable-BP
example), rather than empty measurement columns.

**Acceptance Scenarios**:

1. **Given** a persisted blood-pressure panel Observation whose nested parts carry a Systolic
   reading and a Diastolic reading, **When** the analyst reads that Observation's row in the view,
   **Then** the row reports two generic component triads — each a **display label, a numeric value,
   and a unit** — so that (label "Systolic blood pressure", value, unit) and (label "Diastolic blood
   pressure", value, unit) are both readable from that single row.
2. **Given** the same panel Observation, **When** the analyst reads its row, **Then** it is still a
   **single row** for that Observation (the panel is not expanded into multiple rows).
3. **Given** a panel Observation that records only one of the two readings (a child is optional and
   absent), **When** the analyst reads its row, **Then** the present reading's triad is populated and
   the absent triad is empty (never a fabricated or zero value).
4. **Given** a non-component Observation (scalar quantity or coded result), **When** the analyst
   reads its row, **Then** the two component triads are empty and its top-level value columns carry
   the measurement — the empty triads are expected, not an error.

---

### User Story 2 - No silently-empty rows for the other Observation shapes present (Priority: P2)

An analyst querying the Observation view for the non-panel Observations in the data — a scalar
laboratory quantity (Hemoglobin A1c) and a coded screening result (depression screening) — can see
the measured value and enough descriptive context (the value's human-readable label for coded
results) to interpret the row without opening the source resource.

**Why this priority**: The user asked for the fix to be "extensible to other types of Observations
present in the test data." The scalar-quantity case already reports its value; the coded case
currently reports only a raw code with no label. Rounding this out prevents the analytics team from
hitting the same "row exists but I can't read it" problem on the next Observation type, and confirms
the design generalizes beyond blood pressure.

**Independent Test**: Query the view for the Hemoglobin A1c Observation and confirm its value/unit
are populated; query the depression-screening Observations and confirm the coded result carries a
human-readable label (not only a bare code).

**Acceptance Scenarios**:

1. **Given** a persisted scalar-quantity Observation (Hemoglobin A1c), **When** the analyst reads
   its row, **Then** the numeric value and unit are reported.
2. **Given** a persisted coded-result Observation (depression screening), **When** the analyst
   reads its row, **Then** the coded result is reported together with its human-readable label.
3. **Given** any Observation whose measurement is absent for a given column, **When** the analyst
   reads its row, **Then** that column is empty rather than fabricated.

---

### Edge Cases

- **Panel with a missing child**: A blood-pressure panel where only Systolic (or only Diastolic) is
  recorded → the present reading is reported; the missing one is empty.
- **Non-panel Observation**: An Observation with no nested measurement parts → the panel-specific
  columns are empty; its top-level value columns behave exactly as before (no regression).
- **A future/other panel type**: A component-bearing Observation that is *not* blood pressure →
  its first two nested parts populate the two generic triads (each self-described by its
  `component_display`); the view does not error or corrupt other rows.
- **More than two nested parts**: An Observation with more than two nested measurement parts → only
  the first two are surfaced by the two triads; parts beyond the second are not shown (the two-triad
  count is a reviewable default sized to the blood-pressure panel present in the data).
- **Ambiguous top-level vs nested value**: An Observation that somehow carries both a top-level value
  and nested parts → both are reported in their respective columns; neither overwrites the other.
- **One-row invariant**: Adding measurement columns must not multiply rows — the view stays one row
  per Observation (consistent with the rest of the checked-in view set).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Observation view MUST expose **two generic component triads** on each
  Observation's row, sourced from the Observation's nested measurement parts. Each triad consists of
  a **component display label**, a **numeric component value**, and a **component unit**. For a
  blood-pressure panel these carry the Systolic and Diastolic readings.
- **FR-002**: The component-triad columns MUST be **generic** — named for their position/role (e.g.
  "component 1 / component 2"), **not** for a specific Observation type (no `systolic_*` /
  `diastolic_*` columns). The `component_display` value in each triad MUST identify which
  measurement that triad holds (e.g. "Systolic blood pressure").
- **FR-003**: The view MUST remain **one row per Observation**; surfacing panel measurements MUST
  NOT expand a panel into multiple rows.
- **FR-004**: When a component triad has no corresponding nested part (a child is absent, or the
  Observation has no nested parts at all), that triad's columns MUST be empty and MUST NOT be
  fabricated, defaulted, or zero-filled. Empty triads are an expected, accepted outcome for the many
  Observations that carry no nested parts.
- **FR-005**: The view MUST continue to report the existing top-level measurement columns for
  Observations that carry a top-level value with no regression. For scalar-quantity Observations
  (e.g. Hemoglobin A1c) the existing value + unit columns are sufficient and MUST be retained
  unchanged.
- **FR-006**: For coded-result Observations (e.g. depression screening), the view MUST report the
  coded value's **human-readable display label** in addition to the existing coded value (the code),
  which is retained.
- **FR-007**: The two component triads MUST be sourced **positionally** from the Observation's
  nested parts (first nested part → triad 1, second → triad 2). Disambiguation of which measurement
  each triad holds is provided by that triad's `component_display` value, not by matching a specific
  measurement code.
- **FR-008**: The change MUST be limited to the Observation view definition; it MUST NOT alter what
  Observations are persisted, nor change any other resource type's view, nor change the view's
  provenance/measure-scoping behavior.
- **FR-009**: Every Observation present in the test data MUST, after this change, report its
  recorded measurement(s) in the view rather than an all-empty measurement row — verifiable against
  the fixtures.
- **FR-010**: The approach MUST be documented as a **reviewable default column set** (consistent
  with the existing Observation view and the 002/004 precedent), so the analytics team can confirm
  or refine the exact columns without a structural rework.

### Key Entities *(include if feature involves data)*

- **Observation**: A single measurement or assessment persisted by the processor. Carries a code
  identifying what was measured, a category, a subject/encounter, an effective time, and a value.
  The value may be recorded **at the top level** (scalar quantity, coded value, string) or, for a
  **panel**, distributed across **nested measurement parts**.
- **Component triad**: A generic set of three columns — display label, numeric value, unit —
  surfacing one of an Observation's nested measurement parts. The view exposes **two** such triads,
  filled positionally from the Observation's nested parts. For a blood-pressure panel, triad 1 and
  triad 2 carry the Systolic and Diastolic readings; the display label makes each triad
  self-describing regardless of type. Empty for Observations with no (or fewer) nested parts.
- **Observation view row**: One flattened analytics row per persisted Observation, exposing the
  Observation's identity, code/category, subject/encounter, effective time, provenance/measure tag,
  its top-level value columns (scalar value + unit; coded value **code and display**), and the two
  component triads — whether the measurement was recorded at the top level or in nested parts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every blood-pressure panel Observation in the test data, the analyst can read two
  populated component triads — each with a non-empty display label, value, and unit — corresponding
  to the Systolic and Diastolic readings; 0 such Observations show an all-empty measurement row.
- **SC-002**: The Observation view returns exactly one row per persisted Observation before and
  after the change (row count is unchanged; no panel is multiplied).
- **SC-003**: Every distinct Observation type present in the test data (scalar quantity, coded
  result, blood-pressure panel) reports its recorded value(s) in the view — 100% of measured
  Observations are readable without opening the source resource.
- **SC-004**: No regression: every measurement value the view reported before this change is still
  reported, unchanged, afterward.
- **SC-005**: Adding coverage for an additional panel type in the future is a change to the single
  Observation view definition only (no change to persisted data, other views, or the publish
  mechanism).

## Assumptions

- **Two generic, positional component triads (decided — see Clarifications 2026-07-07).** The
  representation is neither a row-per-component nor type-specific named columns. Instead the view
  adds two triads (display + value + unit), filled positionally from the Observation's nested parts.
  This preserves the view set's one-row-per-resource invariant and keeps the columns generic; the
  `component_display` value disambiguates each triad. The triads are accepted to be empty for the
  many Observations without nested parts.
- **Extensibility is served by generic, self-describing triads.** Because the triads are not tied to
  Systolic/Diastolic by name, any future component-bearing Observation reuses the same two columns
  with no per-type schema. "Extensible to other Observation types present in the test data" is
  further served by surfacing the coded-result display so coded Observations (depression screening)
  are readable, and by the scalar case already being covered by the existing value/unit columns.
- **Two triads is a reviewable default sized to the data** (the blood-pressure panel has exactly two
  nested parts). Adding a third triad later, if a wider panel appears, is an edit to the single
  Observation view file plus a re-run — consistent with how the Observation view (FR-002 of 004) and
  Patient view (002) shipped their reviewable default column sets.
- **This is a view-definition-only change** over already-persisted, already-storable resources: no
  change to what is persisted, to other views, to the publish/materialize mechanism, or to
  provenance/measure scoping.
- **Validation is server acceptance + fixture query**, consistent with the rest of the view set:
  the authoritative gate is that the view is accepted and materializes, and that querying it against
  the processed fixtures shows the expected non-empty measurements. The user runs all live/e2e
  steps against the server.
