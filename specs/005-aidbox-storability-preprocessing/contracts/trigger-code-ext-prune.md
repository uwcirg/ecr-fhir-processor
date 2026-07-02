# Contract: eICR Trigger-Code Empty Sub-Extension Pruning Transform

The second content transform this feature introduces (Cause 4 — base-FHIR `ext-1`). It is an
**internal function contract** — the processor exposes no new CLI surface or API. Implemented in
`process.py`; wired into the write path of `_process_message` (the only path that persists an eICR
Composition / trigger-code section), before the output mirror and the PUT.

## Signature (illustrative)

```python
def prune_empty_trigger_code_extensions(node: object, source_filename: str) -> int:
    """Remove url-only children of every eICR trigger-code-flag extension.

    Recursively walks `node` (message Bundle → document Bundle → Composition.section[*].
    entry[*]). For each `eicr-trigger-code-flag-extension`, drops any child sub-extension
    that carries neither a `value[x]` nor nested extensions. Mutates in place. Returns the
    number of sub-extensions removed. Logs a WARNING per removal. Idempotent.
    """
```

Empty-detection helper:

```python
def _extension_carries_nothing(ext: dict) -> bool:
    """True iff `ext` has neither a `value[x]` nor child `extension` entries (base-FHIR
    ext-1: `extension.exists() != value.exists()` — a url-only shell fails the XOR)."""
```

## Inputs

- `node`: a parsed FHIR resource dict (message Bundle, or a Composition) already stamped by `_stamp`.
  The promoted Composition is the **same object** nested in the document Bundle, so a single walk over
  the message Bundle cleans both the Bundle PUT and the standalone Composition PUT.
- `source_filename`: for log attribution only.

## Behavioral requirements

| # | Requirement | Maps to |
|---|-------------|---------|
| C1 | A child sub-extension of an `eicr-trigger-code-flag-extension` is removed **iff** it has neither a `value*` key nor a non-empty `extension` array (`_extension_carries_nothing`). A sibling with a populated `valueString` (e.g. a real `triggerCodeValueSetVersion`) is **not** removed. | FR-015 |
| C2 | The `triggerCode` and `triggerCodeValueSet` siblings (the clinical payload) are left byte-identical. | FR-015 |
| C3 | Every other element of the resource is unchanged; only the empty sub-extension is dropped. | FR-015 |
| C4 | No fabrication: the transform never invents a version `valueString` or any element to "fix" the extension. It only removes. The flag extension retains its non-empty children, so it stays `ext-1`-valid; the transform never deletes the flag extension itself in the sample data. | FR-007, FR-015, Principle V |
| C5 | Idempotent: a second call removes 0 and changes nothing. | FR-010 |
| C6 | Each removal logs at **WARNING** or above and the message **names the removed sub-extension** (its `url`) plus the source file, so the drop is auditable and keyed to `REMEDIATION_TRIGGER_CODE_EXT_PRUNE`. | FR-006, SC-003 |
| C7 | Recurses through the message Bundle → nested document Bundle → Composition, so a Bundle carrying the malformed extension is not rejected as a whole. | FR-015 |
| C8 | The transform runs **before** `_maybe_mirror(...)`, so the mirrored `output/` bytes equal the submitted bytes. | FR-008 |

## Post-conditions

- The (possibly modified) resource satisfies base-FHIR `ext-1`
  (`extension.exists() != value.exists()`) for every trigger-code sub-extension.
- Re-validating the transformed resource with the HL7 gate yields **no new signature** vs.
  `test/conformance-baseline.sigs` (FR-009 — verified by `scripts/validate.sh`, not by this function).

## Scope note

In the current sample this occurs only in the depression-screening (CMS2) message Bundle
(`Bundle_06308645-…`); the other three trigger-code Bundles carry a populated version and are
untouched. Trigger-code flag extensions appear only within the promoted eICR Composition, so the
removal count is attributed to both the whole-Bundle PUT and the Composition PUT (both are made
storable by the same removal).

## Test scenarios (→ `tests/test_trigger_code_ext_prune.py`)

1. **Removes empty sub-extension**: flag extension with `[triggerCodeValueSet, <empty version>,
   triggerCode]` ⇒ returns 1, the empty version gone, siblings intact.
2. **Preserves clinical siblings**: the `triggerCode`/`triggerCodeValueSet` children are byte-identical
   after pruning.
3. **Keeps populated version**: a `triggerCodeValueSetVersion` with a `valueString` ⇒ returns 0,
   deep-equal to input.
4. **No-op without flag extension** / **no fabrication**: a resource with no trigger-code flag
   extension is unchanged; an empty version is removed, never given a fabricated value.
5. **Idempotent**: apply twice ⇒ second call returns 0, no change.
6. **WARNING names the sub-extension**: a removal logs a WARNING containing
   `triggerCodeValueSetVersion`, the remediation key, and the source file.
7. **Nested walk**: a message Bundle whose nested document Bundle holds the Composition ⇒ the walk
   cleans it; the rest of the Bundle is otherwise unchanged.
