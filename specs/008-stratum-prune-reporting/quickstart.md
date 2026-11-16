# Quickstart: Validate Stratum Prune Reporting

All of these steps are local. None of them contacts Aidbox; live and end-to-end runs are done by the user.

## 1. Lint + unit tests

```bash
ruff check process.py tests/
python3 -m unittest discover -s tests -v
```

**Expected**: all tests pass, including the new scenarios in [contracts/stratum-prune-reporting.md](./contracts/stratum-prune-reporting.md).

## 2. Dry-run over the fixtures

Run against the fixtures:

```bash
python3 process.py --config config.example.json --dry-run --input-dir test/input --no-output-mirror
```

**Expected** for every MeasureReport file, standalone and message Bundle alike (spec SC-001):

- One WARNING per file, containing `group[0] stratifier stratifier-payer`, followed by the carried populations.
- The RunSummary line for that file ends with `pruned 1 mrp-2 stratum(s), kept 4, 1 stratifier(s) left empty`. A message Bundle line also carries the unchanged Cause 4 note when it applies.
- Collection-Bundle lines (no MeasureReport) show no prune note.
- Per-type counts and `exit_code` are identical to a dry-run on `main` before this change (SC-005).

## 3. Byte-identical output

The mirror is on by default. Run the dry-run once before and once after the change, each into its own output directory:

```bash
git stash   # or check out main
python3 process.py --config config.example.json --dry-run --input-dir test/input --output-dir <before-output>
git stash pop
python3 process.py --config config.example.json --dry-run --input-dir test/input --output-dir <after-output>
diff -r <before-output>/ <after-output>/   # only provenance meta (version/processed-on) may differ
```

**Expected**: no content differences beyond provenance stamps (SC-004).

## 4. HL7 gate (optional; content is unchanged)

```bash
scripts/validate.sh
```

**Expected**: no new signature against `test/conformance-baseline.sigs` (SC-006). A transient `phinvads.cdc.gov` timeout is not a regression.
