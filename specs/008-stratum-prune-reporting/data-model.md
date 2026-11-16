# Data Model: Stratum Prune Reporting

These structures exist in memory only. Nothing is persisted, and FHIR resource content is unchanged.

## StratumPruneResult

What one prune call returns: for a single MeasureReport, or summed across a Bundle's nested MeasureReports.

| Field | Type | Meaning |
|-------|------|---------|
| `removed` | int ≥ 0 | Strata removed because they had neither `value` nor `component` (unchanged predicate). |
| `kept` | int ≥ 0 | Strata remaining after the prune, across every stratifier of every processed report. |
| `emptied` | int ≥ 0 | Stratifiers that had ≥1 stratum before and 0 after (their `stratum` property was deleted). |

**Rules**
- `emptied ≤ removed`: each emptied stratifier lost at least one stratum.
- `removed + kept` = the number of strata before the prune (per report, and per summed total).
- A stratifier that had no strata, or `stratum: []`, in the input contributes 0 to all three counts.
- Summing: `a + b = (a.removed+b.removed, a.kept+b.kept, a.emptied+b.emptied)`. The zero value is `StratumPruneResult(0, 0, 0)`.
- **Idempotency**: a second prune of the same report gives `removed=0, emptied=0`, and `kept` equals the first call's `kept`.

## Removal record (one WARNING per removed stratum)

| Part | Source | Example |
|------|--------|---------|
| remediation key | constant | `aidbox-cause-2-mrp2-stratum-prune` |
| source file | `source_filename` argument | `MeasureReport_533b….json` |
| group index | zero-based position in `report.group` | `group[0]` |
| stratifier label | see below | `stratifier-payer` |
| population counts | existing `_summarize_stratum_populations` | `initial-population=0, denominator=0, …` |

## Stratifier label

The first available of:

1. `stratifier.id` → `stratifier-payer`
2. The first `coding.code` found in `stratifier.code` (a list of CodeableConcept; a lone dict is tolerated) → `code=plan`
3. The first `text` in `stratifier.code` → `text=SDE Payer`
4. The zero-based position within its group → `#1`

It is never empty.

## Per-file note (RunSummary detail)

Appended via the existing `_record_remediation` only when `removed > 0`:

```text
pruned {removed} mrp-2 stratum(s), kept {kept}, {emptied} stratifier(s) left empty
```

`remediations_applied` receives `removed`, exactly as today.
