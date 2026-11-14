# Feature Specification: Stratum Prune Reporting

**Feature Branch**: `008-stratum-prune-reporting`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Extend the Cause 2 mrp-2 stratum prune's reporting. For each MeasureReport it changes, report strata removed, strata kept, and stratifiers left empty (whose stratum property was deleted), in the RunSummary per-file detail. Add the group index and stratifier identifier to each removal WARNING. Report nothing extra for MeasureReports that needed no prune. Don't change the remediated/transformed accounting rules or the prune logic itself."

**Builds on**: `specs/005-aidbox-storability-preprocessing` (Cause 2 transform; contracts `stratum-prune.md`, `run-accounting.md`).

## Background

The processor removes MeasureReport strata that have neither a `value` nor a `component`. Base FHIR invariant `mrp-2` forbids such strata, and Aidbox rejects the whole resource when it finds one. Today an operator sees two things:

- one WARNING per removed stratum, naming the source file and the population counts the stratum carried;
- a RunSummary per-file note, `pruned N mrp-2 stratum(s)`.

That's enough to see that strata were removed, but not enough to judge what's left. An operator can't tell "pruned 1 of 1" from "pruned 1 of 40". They can't tell whether a stratifier was left with no strata, which in the downstream analytics looks like the measure was never stratified on that dimension. And with several removals in one report, they can't tell which stratifier each WARNING refers to.

In the current test fixtures, every MeasureReport loses exactly one stratum: the only stratum of the `stratifier-payer` stratifier (code `plan`, "SDE Payer"). That stratifier always ends up with no strata. Some fixtures also have a stratifier that had no strata in the input (`stratifier-food-insecurity-risk-status`). That one wasn't emptied by the prune and must not be reported as if it were.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See how much of each pruned MeasureReport survived (Priority: P1)

An operator runs the processor (live or dry-run) and reads the RunSummary. For every file whose MeasureReport(s) were pruned, the per-file note says how many strata were removed, how many remain, and how many stratifiers the prune left with no strata. The operator can judge right away whether a stratified breakdown survived, without opening the output file.

**Why this priority**: This is the main gap. Whether the prune cost real analytic coverage depends on the removed/kept ratio and on emptied stratifiers, and today neither is visible.

**Independent Test**: Run the processor in dry-run over a fixture MeasureReport known to contain one malformed stratum among several conforming ones. Check that the RunSummary line for that file reports 1 removed, the right kept count, and the right emptied-stratifier count.

**Acceptance Scenarios**:

1. **Given** a standalone MeasureReport with 6 stratifiers holding 5 strata in total, one of which is malformed and is its stratifier's only stratum, **When** the processor runs, **Then** the RunSummary per-file note reports 1 stratum removed, 4 strata kept, and 1 stratifier left empty.
2. **Given** a MeasureReport where a stratifier has 1 malformed and 2 conforming strata, **When** the processor runs, **Then** the note reports 1 removed and 0 stratifiers left empty for that report, and the kept count includes the 2 conforming strata.
3. **Given** a message Bundle whose nested MeasureReport has malformed strata, **When** the processor runs, **Then** the note on the message Bundle's line reports removed, kept and emptied counts for the nested MeasureReport(s).
4. **Given** a MeasureReport with a stratifier that already had no strata in the input, **When** the processor runs, **Then** that stratifier is NOT counted as left empty by the prune.

---

### User Story 2 - Trace each removal to its stratifier (Priority: P2)

An operator reading the log (console or `log/` file) sees, for each removed stratum, which group and which stratifier it came from, alongside the population counts already logged. They can then match a removal to a specific dimension (e.g. payer) and to the corresponding column in the analytics views.

**Why this priority**: When a file has a single removal, the file name and counts are enough. Once a report has several removals, the WARNINGs can't be told apart. That makes auditing harder, but it isn't a blind spot about outcomes the way Story 1 is.

**Independent Test**: Run the prune on a MeasureReport with malformed strata in two different stratifiers. Check that each WARNING names its own group index and stratifier identifier.

**Acceptance Scenarios**:

1. **Given** a removed stratum in group 0 of a stratifier with id `stratifier-payer`, **When** the WARNING is logged, **Then** it includes the group index `0` and the identifier `stratifier-payer`, as well as the source file name and population counts it already carries.
2. **Given** a removed stratum in a stratifier with no `id`, **When** the WARNING is logged, **Then** it identifies the stratifier by its code (or, failing that, by its position in the group). It never leaves the stratifier unidentified.

---

### User Story 3 - Clean reports stay quiet (Priority: P3)

An operator processing MeasureReports that need no prune sees no new log lines and no new summary text for them.

**Why this priority**: This protects the readability of existing output. It's a constraint on Stories 1–2 more than new value on its own.

**Independent Test**: Run the processor on a MeasureReport with no malformed strata. Check that its RunSummary line and log output are byte-for-byte what the current processor produces.

**Acceptance Scenarios**:

1. **Given** a MeasureReport with no malformed strata, **When** the processor runs, **Then** no removed/kept/emptied note appears for it, and no prune WARNING is logged.

---

### Edge Cases

- **Several MeasureReports under one file** (a message Bundle with more than one nested MeasureReport, or nested Bundles): the file's note reports totals across every MeasureReport the prune walked in that file.
- **Every stratum in the report is removed**: the kept count is reported as `0`, not left out.
- **A stratifier already had no strata, or an empty `stratum` list, in the input**: it doesn't count as left empty by the prune. That count covers only stratifiers the prune itself emptied.
- **A conforming stratum (`value` or `component` present)**: it counts as kept and is never altered.
- **The file's PUT fails, or the run is a dry-run**: the counts are reported anyway, because the prune ran. This matches how `transformed` is counted today (it records that a transform ran, regardless of storage).
- **A stratifier has no `id` and no usable code**: the WARNING identifies it by its position (index) within its group.
- **A stratifier's code carries several codings**: use the first coding that has a code, the same rule the existing population-label logic uses.
- **The same MeasureReport appears both standalone and nested in its eCR message Bundle**: each file's line reports its own counts. This feature does not de-duplicate across files.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: For each input file in which the mrp-2 stratum prune removed at least one stratum, the RunSummary per-file note MUST report three counts: (a) strata removed, (b) strata kept, and (c) stratifiers the prune left with no strata.
- **FR-002**: "Strata kept" MUST be the number of strata remaining, after the prune, across every stratifier of every MeasureReport the prune processed for that file. It MUST include strata in stratifiers that had no removals.
- **FR-003**: "Stratifiers left empty" MUST count only stratifiers that had at least one stratum before the prune and none after it. Stratifiers that were already empty in the input MUST NOT be counted.
- **FR-004**: When one file contains several MeasureReports (nested in a message/document Bundle, at any depth), the three counts MUST be totals across all of them, shown on that file's single RunSummary line.
- **FR-005**: Each removal WARNING MUST also include the zero-based group index and a stratifier identifier, in addition to what it carries today (source file name and the removed stratum's population counts).
- **FR-006**: The stratifier identifier MUST be chosen in this order: the stratifier's `id`, if present; otherwise the first code found in the stratifier's code(s), or its text; otherwise the stratifier's zero-based position within its group. A WARNING MUST never omit the identifier.
- **FR-007**: For an input file in which the prune removed nothing, the processor MUST NOT emit any new summary text or log output compared with current behavior.
- **FR-008**: The counts MUST be reported whenever the prune removed at least one stratum, whatever the storage outcome (succeeded, failed or dry-run). This matches the existing rule that a transform that ran is always visible.
- **FR-009**: The feature MUST NOT change which strata are removed, how an emptied stratifier is represented (the `stratum` property is deleted, never left as `[]`), the idempotency of the prune, or the resource content submitted to the server or written to `output/`.
- **FR-010**: The feature MUST NOT change how runs and resources are counted: the meaning and values of `submitted`, `succeeded`, `remediated`, `failed`, `deferred`, `skipped` and `transformed`, and the exit code.
- **FR-011**: The removal WARNINGs MUST stay at WARNING level or above (Constitution Principle V/VIII: no silent remediation).
- **FR-012**: The prune and run-accounting contract documents from feature 005 MUST be updated to describe the new counts and the extended WARNING content, so the documented contract matches runtime behavior.

### Key Entities

- **Prune result (per MeasureReport, summed per file)**: strata removed, strata kept, stratifiers left empty. Collected while the prune runs and attached to the file's RunSummary note.
- **Removal record (per removed stratum)**: source file, group index, stratifier identifier, and the removed stratum's population counts. Surfaced as one WARNING.
- **Stratifier identifier**: a human-readable label for a stratifier: its `id`, else its code, else its position within its group.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every fixture MeasureReport under `test/input/`, the RunSummary line reports removed, kept and emptied counts that match an independent count of the fixture (strata without value/component; strata remaining; stratifiers going from at least one stratum to none). Agreement on 100% of fixtures.
- **SC-002**: For every removal WARNING produced by the full fixture set, an operator can identify the exact group and stratifier from the log line alone. 100% of WARNINGs carry both.
- **SC-003**: For a MeasureReport that needs no prune, the summary and log output are identical to the current processor's output for the same input. Zero added lines.
- **SC-004**: The bytes submitted to the server and written to `output/` are identical before and after this feature for every fixture. Zero content differences.
- **SC-005**: Every run-level count (`submitted`, `succeeded`, `remediated`, `failed`, `deferred`, `skipped`, `transformed`) and the exit code are identical before and after this feature for the full fixture set.
- **SC-006**: Validating the transformed resources against the HL7 conformance gate shows no new signature compared with the committed baseline. The feature changes reporting only, so this holds trivially, but it is still checked.

## Assumptions

- The audience is the operator reading the run's console/log output and RunSummary. No new output file, CLI flag or analytics column is in scope.
- Run-level totals for strata removed/kept in the RunSummary footer are **out of scope**. The per-file note is enough for current run sizes, and a footer line can be added later if needed.
- The exact wording and layout of the per-file note (e.g. `pruned 1 of 5 mrp-2 strata (kept 4); 1 stratifier left empty`) is left to planning, provided all three counts are present and unambiguous.
- Cross-file de-duplication (the standalone MeasureReport and its byte-identical copy nested in the message Bundle) is out of scope. Each file reports what was pruned in it.
- The Cause 4 trigger-code extension prune's reporting is out of scope and stays unchanged.
- Group index and stratifier position are zero-based, matching array positions in the FHIR JSON.
- Users of this feature run all live/Aidbox steps themselves. Verification here is limited to unit tests, dry-run and the conformance gate.
