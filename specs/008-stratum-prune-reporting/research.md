# Research: Stratum Prune Reporting

There were no `NEEDS CLARIFICATION` items. Each decision below settles a design choice the spec left to planning.

## R1. How the prune returns three counts

- **Decision**: `prune_measurereport_strata` and `prune_nested_measurereports` return a frozen dataclass `StratumPruneResult(removed: int, kept: int, emptied: int)` that supports `+` for summing. Callers read `.removed` where they read the int before.
- **Rationale**: The counts are named and typed, and summing nested MeasureReports is one expression. Only 2 production call sites and about 8 test assertions need changing.
- **Alternatives considered**:
  - An optional mutable `stats` accumulator parameter, keeping the `int` return. This means fewer test edits, but the function gains in/out-parameter behavior, and it's easy to forget to pass the accumulator.
  - An `int` subclass that carries extra attributes. Too clever; `==` and `+` semantics get confusing.
  - A separate counting pass after the prune. That walks the strata twice and can't tell "emptied by the prune" from "already empty" without a snapshot.

## R2. Definition of "kept" and "emptied"

- **Decision**: `kept` is the number of strata remaining after the prune, across **all** stratifiers of the report, including untouched ones. `emptied` counts stratifiers whose stratum list had at least one stratum before the prune and none after it, which is exactly the case where the code deletes the `stratum` property.
- **Rationale**: This follows the spec (FR-002/FR-003). The `food-insecurity` stratifier in the fixtures has no strata in the input, so it naturally contributes 0 to both counts. Expected result for every fixture: removed=1, kept=4, emptied=1.
- **Alternatives considered**: Counting kept only within touched stratifiers. Rejected because it hides how much of the report survived, which is the point of the feature.

## R3. Per-file note wording

- **Decision**: `pruned {removed} mrp-2 stratum(s), kept {kept}, {emptied} stratifier(s) left empty`. All three counts are always present once `removed > 0`, zeros included.
- **Rationale**: It keeps the existing `pruned N mrp-2 stratum(s)` prefix, so anyone grepping logs for the old note still matches. It's one clause on the existing RunSummary line, and zeros are explicit instead of implied.
- **Alternatives considered**:
  - `pruned 1 of 5 …`: the "of" total is derivable (removed + kept), so it's redundant.
  - Separate RunSummary columns: these would require changing `FileOutcome`/`RunSummary` in `fhir_common.py` and the per-type table. That's more surface than the spec asks for (no footer totals).

## R4. Stratifier identifier in the WARNING

- **Decision**: A new helper `_stratifier_label(stratifier, index)` picks the first available of:
  1. `stratifier.id`, e.g. `stratifier-payer`;
  2. `code=<first coding.code>` from `stratifier.code`. In R4 that field is a list of CodeableConcept, but a lone dict is tolerated defensively;
  3. `text=<code.text>`;
  4. `#<index>`.

  The WARNING becomes: `Removed value/component-less MeasureReport stratum (base-FHIR mrp-2) from %s at group[%d] stratifier %s; carried populations: %s`.
- **Rationale**: Every fixture stratifier has an `id`, and those ids are readable (`stratifier-payer`). The fallbacks follow the existing population-label rule (first coding with a code, then text), so a WARNING never lacks an identifier (FR-006). The existing message text is kept up to and including the filename, so `test_warning_carries_population_counts` and log greps keep working.
- **Alternatives considered**: Printing the coding display as well (e.g. `plan "SDE Payer"`). Possible later; `id` is enough for the fixtures, and display strings vary in case between fixtures (`Age group` vs `Age Group`).

## R5. Where the counts travel to the RunSummary

- **Decision**: Through the existing `outcome.detail` string, built by `_record_remediation(outcome, result.removed, note)`. `_record_remediation` itself is unchanged.
- **Rationale**: `remediations_applied` keeps receiving the *removed* count, so `transformed` and `remediated` are mathematically unchanged (FR-010). The `removed <= 0` early return already makes clean reports silent (FR-007). For a failed PUT or a dry-run, the detail note is already appended (FR-008).
- **Alternatives considered**: New `FileOutcome` fields. Rejected: they'd touch `fhir_common.py` and the summary renderer for a value that's only displayed.

## R6. Message Bundles with Cause 2 and Cause 4 notes

- **Decision**: No change to ordering. The message Bundle line keeps the Cause 2 note first and the Cause 4 trigger-code note second, separated by `; `. Only the Cause 2 clause changes.
- **Rationale**: Cause 4 reporting is out of scope (spec Assumptions). Commas inside the Cause 2 clause and `; ` between the two notes keep them distinguishable.
