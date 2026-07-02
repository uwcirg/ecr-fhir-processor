# Contract: MeasureReport `mrp-2` Stratum Pruning Transform

The single content transform this feature introduces (Cause 2). It is an **internal function
contract** — the processor exposes no new CLI surface or API. Implemented in `process.py`; wired into
the write path of `_process_measure_report` (standalone) and `_process_message` (nested), before the
output mirror and the PUT.

## Signature (illustrative)

```python
def prune_measurereport_strata(report: dict, source_filename: str) -> int:
    """Remove every stratifier stratum lacking both `value` and `component`.

    Mutates `report` in place. Returns the number of strata removed. Logs a WARNING per
    removed stratum, including any population counts it carried. Idempotent.
    """
```

A companion walker prunes MeasureReports nested inside a message/document Bundle:

```python
def prune_nested_measurereports(bundle: dict, source_filename: str) -> int:
    """Find every MeasureReport in `bundle.entry[*].resource` (recursing into nested
    Bundles) and apply prune_measurereport_strata to each. Returns total strata removed."""
```

## Inputs

- `report` / `bundle`: a parsed FHIR resource dict (already stamped by `_stamp`).
- `source_filename`: for log attribution only.

## Behavioral requirements

| # | Requirement | Maps to |
|---|-------------|---------|
| C1 | A stratum is removed **iff** `stratum.get("value") is None and not stratum.get("component")`. | FR-005 |
| C2 | A stratum with `value` **xor** `component` is left byte-identical. | FR-005 |
| C3 | Every non-stratum element of the MeasureReport (group populations, measureScore, DEQM extensions, meta, id, etc.) is unchanged. | FR-005 |
| C4 | Empty `stratum` arrays and empty `stratifier`/`group` arrays are left in place (the transform removes strata only; an empty stratum list satisfies `mrp-2` vacuously). | data-model §4 |
| C5 | Idempotent: a second call removes 0 and changes nothing. | FR-010 |
| C6 | Each removal logs at **WARNING** or above and the message **includes the removed stratum's `population` counts** (e.g. code + count per population), so the drop is auditable. | FR-006, SC-003 |
| C7 | Applies to **standalone** MeasureReports and MeasureReports **nested inside** a persisted message/document Bundle; the nested walk recurses through nested Bundles. | FR-005 |
| C8 | The transform runs **before** `_maybe_mirror(...)`, so the mirrored `output/` bytes equal the submitted bytes. | FR-008 |
| C9 | No fabrication: the transform never adds a `value`, `component`, or any element. It only removes. | FR-007, Principle V |

## Post-conditions

- The (possibly modified) resource satisfies base-FHIR `mrp-2`
  (`group.stratifier.stratum.all(value.exists() xor component.exists())`).
- Re-validating the transformed resource with the HL7 gate yields **no new signature** vs.
  `test/conformance-baseline.sigs` (FR-009 — verified by `scripts/validate.sh`, not by this function).

## Test scenarios (→ `tests/test_stratum_prune.py`)

1. **Removes malformed stratum**: MeasureReport with one `population`-only stratum ⇒ returns 1, that
   stratum gone, resource now `mrp-2`-clean.
2. **Preserves conforming siblings**: stratifier with one malformed + one `value`-bearing stratum ⇒
   only the malformed one removed; the conforming stratum byte-identical.
3. **No-op on clean input**: all strata have `value` or `component` ⇒ returns 0, deep-equal to input.
4. **Idempotent**: apply twice ⇒ second call returns 0, no change.
5. **WARNING carries counts**: a removed stratum with a population count of N ⇒ a WARNING log record
   containing N (assert via `assertLogs`).
6. **Nested walk**: a message Bundle whose nested content Bundle holds a MeasureReport with a malformed
   stratum ⇒ `prune_nested_measurereports` removes it; the outer Bundle is otherwise unchanged.
7. **Everything-else untouched**: deep-equal on the MeasureReport minus the removed stratum path
   (group populations, measureScore, DEQM `extension-criteriaReference`, meta all intact).
