# Contract Addendum: Stratum Prune Reporting

This contract amends [`005/contracts/stratum-prune.md`](../../005-aidbox-storability-preprocessing/contracts/stratum-prune.md) and [`005/contracts/run-accounting.md`](../../005-aidbox-storability-preprocessing/contracts/run-accounting.md). All 005 requirements C1–C9 still apply unchanged; only the return type (C-R1) and the log/summary text change.

## Signatures (illustrative)

```python
@dataclass(frozen=True)
class StratumPruneResult:
    removed: int = 0
    kept: int = 0
    emptied: int = 0
    def __add__(self, other: "StratumPruneResult") -> "StratumPruneResult": ...

def prune_measurereport_strata(report: dict, source_filename: str) -> StratumPruneResult: ...
def prune_nested_measurereports(bundle: dict, source_filename: str) -> StratumPruneResult: ...
def _stratifier_label(stratifier: dict, index: int) -> str: ...
```

## Behavioral requirements

| # | Requirement | Spec |
|---|-------------|------|
| R1 | The prune returns `StratumPruneResult`. `removed` equals the int returned under 005, for every input. | FR-009 |
| R2 | `kept` = strata remaining across all stratifiers after the prune. | FR-002 |
| R3 | `emptied` counts only stratifiers that went from ≥1 stratum to 0. A stratifier with no strata in the input is never counted. | FR-003 |
| R4 | `prune_nested_measurereports` returns the `+`-sum over every nested MeasureReport, at any Bundle depth. | FR-004 |
| R5 | Each removal WARNING contains, in order: the remediation key, the source file, `group[<i>]`, `stratifier <label>`, and the carried population counts. Level stays WARNING. | FR-005, FR-011 |
| R6 | `_stratifier_label` uses this order: `id`, then `code=<first coding.code>`, then `text=<code text>`, then `#<index>`. It never returns an empty string. | FR-006 |
| R7 | When `removed > 0`, the per-file detail gets `pruned {removed} mrp-2 stratum(s), kept {kept}, {emptied} stratifier(s) left empty`, whatever the PUT status (including failed or dry-run). | FR-001, FR-008 |
| R8 | When `removed == 0`, nothing is added to the detail and no WARNING is logged. | FR-007 |
| R9 | `remediations_applied` still receives `removed`. Statuses, `transformed`, per-type rows and the exit code are unchanged. | FR-010 |
| R10 | Resource bytes (PUT body and `output/` mirror) are identical to 005 behavior. | FR-009, SC-004 |

## Test scenarios

`tests/test_stratum_prune.py`:
1. One malformed stratum that is its stratifier's only stratum, plus one untouched stratifier with 2 strata: expect (removed 1, kept 2, emptied 1).
2. A stratifier with 1 malformed and 2 conforming strata: expect (1, 2, 0).
3. A stratifier with no `stratum` in the input, alongside a pruned stratifier: the pre-empty one isn't counted in `emptied`.
4. Clean report: expect (0, N, 0), no WARNING (`assertNoLogs`).
5. Idempotency: the second call returns removed 0, emptied 0, with `kept` unchanged.
6. Malformed strata in two stratifiers: two WARNINGs, each with its own `group[i]` and label.
7. Label fallbacks: id present gives the id; no id but coding gives `code=…`; text only gives `text=…`; neither gives `#<index>`.
8. Nested: a message Bundle holding two MeasureReports (one inside a nested document Bundle) returns the field-wise sum.
9. Existing tests C1–C9 pass after `removed == 1` becomes `result.removed == 1`.

`tests/test_summary.py`:
10. With a pruned report, the outcome's detail contains all three counts in the R7 format; `remediations_applied == removed`.
11. With a clean report, the detail is unchanged and `remediations_applied == 0`.
