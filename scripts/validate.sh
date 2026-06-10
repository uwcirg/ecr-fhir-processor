#!/usr/bin/env bash
#
# Conformance gate (constitution Principle III, gate 1): validate the JSON the processor
# would submit against the HL7 FHIR Reference Validator, using IG versions pinned in the
# run config. Run this over dry-run output BEFORE any real (non-dry-run) submission.
#
# The gate enforces "zero PROJECT-INTRODUCED errors" — not "zero errors". The supplier's
# source fixtures carry inherent validator errors (R5-backport extensions, duplicate
# population ids, terminology display mismatches, and the validator's intermittent
# ballot-vs-pinned IG resolution). Those are not ours to fix. So the gate reduces every
# validator error to a location/line/UUID-independent SIGNATURE and fails only on
# signatures that are NOT in the committed source baseline — i.e. errors the transform
# introduced.
#
# The baseline (test/conformance-baseline.sigs) is the set of error signatures produced by
# validating the pre-transform source fixtures with the pinned IG set. It is committed so a
# gate run needs only ONE validation pass (the output), keeping CI fast. Regenerate it with
# `--update-baseline` whenever the fixtures or the pinned IG versions change, and commit it.
#
# Usage:
#   scripts/validate.sh [OUTPUT_GLOB] [CONFIG]
#       Gate: validate OUTPUT_GLOB and fail on any error signature absent from the baseline.
#         OUTPUT_GLOB  files to validate         (default: output/**/*.json)
#         CONFIG       config with ig_versions{} (default: config.json -> config.example.json)
#
#   scripts/validate.sh --update-baseline [SOURCE_GLOB] [CONFIG]
#       Regenerate test/conformance-baseline.sigs from the pre-transform source fixtures.
#         SOURCE_GLOB  source fixtures           (default: test/input/**/*.json)
#
# Exit status: 0 = no project-introduced errors (after known-issue filtering); 1 = errors;
# 2 = the gate could not run (missing jar/java/baseline, no files, validator crash).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Mode + argument parsing -------------------------------------------------------- #
MODE="gate"
if [[ "${1:-}" == "--update-baseline" ]]; then
  MODE="update"
  shift
fi

if [[ "$MODE" == "update" ]]; then
  GLOB="${1:-test/input/**/*.json}"
else
  GLOB="${1:-output/**/*.json}"
fi
CONFIG="${2:-config.json}"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="config.example.json"
fi

VALIDATOR_JAR="validator_cli.jar"
FHIR_VERSION="4.0.1"
KNOWN_ISSUES="known-validation-issues.md"
BASELINE_FILE="test/conformance-baseline.sigs"

if [[ ! -f "$VALIDATOR_JAR" ]]; then
  echo "ERROR: $VALIDATOR_JAR not found in repo root. Download the HL7 FHIR Reference Validator." >&2
  exit 2
fi
if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: Java is required to run $VALIDATOR_JAR but was not found on PATH." >&2
  exit 2
fi

# Scratch dir for the validator program, raw output, and signature sets.
TMPDIR_GATE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_GATE"' EXIT

# --- Normalizer: raw validator output -> error signatures (one per line) ------------ #
# Drop the "Error @" prefix, line/col, array indices, resource-instance ids and UUIDs, and
# collapse Bundle/contained container prefixes so the SAME data error has the SAME signature
# whether a resource is validated standalone or wrapped in a (collection or transaction)
# Bundle. Written to a file and run as `python3 <file>` so its stdin stays free for data.
NORMALIZER="$TMPDIR_GATE/normalize.py"
cat >"$NORMALIZER" <<'PY'
import re, sys
UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
HEAD = re.compile(r'^\s*(?:Error|error)\s+@\s+(.*)$')
for line in sys.stdin:
    m = HEAD.match(line.rstrip('\n'))
    if not m:
        continue
    s = m.group(1)
    s = re.sub(r'\(line \d+, col\d+\)', '', s)            # drop line/col
    s = re.sub(r'\[\d+\]', '', s)                         # drop array indices
    s = re.sub(r'/\*([A-Za-z]+)/[^*]+\*/', r'/*\1*/', s)  # drop instance id in /*Type/<id>*/
    s = re.sub(r'^.*resource/\*([A-Za-z]+)\*/\.', r'\1.', s)  # collapse (nested) Bundle prefix
    s = re.sub(r'contained/\*([A-Za-z]+)\*/\.', r'\1.', s)    # collapse contained prefix
    s = UUID.sub('', s)                                   # drop bare UUIDs
    s = re.sub(r'\s+', ' ', s).strip()
    if s:
        print(s)
PY

normalize_errors() { python3 "$NORMALIZER"; }  # reads raw validator output on stdin

# --- Build versioned -ig arguments from every config.ig_versions entry -------------- #
# The pinned set mirrors what the test-data supplier validates against (constitution II:
# IG Version Tracking). Unpinned (TODO_PIN) entries are skipped with a warning.
VENDORED_IG_DIR="igs"  # optional local package.tgz for IGs not on a public registry
IG_ARGS=()
add_ig() { # name version
  local name="$1" ver="$2"
  if [[ -z "$ver" || "$ver" == "TODO_PIN" ]]; then
    echo "WARNING: IG '$name' is not pinned (value='${ver:-<empty>}'); skipping its -ig arg." >&2
    echo "         Pin it in $CONFIG.ig_versions for a reproducible gate (constitution II)." >&2
    return
  fi
  local vendored="${VENDORED_IG_DIR}/${name}-${ver}.tgz"
  if [[ -f "$vendored" ]]; then
    IG_ARGS+=("-ig" "$vendored")
  else
    IG_ARGS+=("-ig" "${name}#${ver}")
  fi
}
while IFS=$'\t' read -r ig_name ig_ver; do
  [[ -z "$ig_name" ]] && continue
  add_ig "$ig_name" "$ig_ver"
done < <(python3 - "$CONFIG" <<'PY'
import json, sys
try:
    with open(sys.argv[1]) as fh:
        data = json.load(fh)
    for name, ver in (data.get("ig_versions") or {}).items():
        print(f"{name}\t{ver}")
except Exception:
    pass
PY
)

# --- Helpers ------------------------------------------------------------------------ #

# Expand a (possibly globstar) glob into an array on stdout, one path per line. The HL7
# validator's own wildcard handling does not understand bash globstar ("**"), so we must
# expand recursive globs ourselves and pass concrete file paths.
expand_glob() { # glob
  shopt -s globstar nullglob
  # shellcheck disable=SC2206  # intentional word-splitting to expand the glob
  local arr=( $1 )
  shopt -u globstar nullglob
  printf '%s\n' "${arr[@]}"
}

# Run the validator over the given files, writing combined stdout+stderr to $1; returns
# the validator's own exit code.
run_validator() { # outfile files...
  local outfile="$1"; shift
  local rc=0
  set +e
  java -jar "$VALIDATOR_JAR" "$@" -version "$FHIR_VERSION" "${IG_ARGS[@]}" >"$outfile" 2>&1
  rc=$?
  set -e
  return "$rc"
}

# True when a validator run did not complete (engine/IG load failure or an exception),
# which is a hard gate failure distinct from per-resource validation errors.
is_hard_fail() { # outfile rc
  [[ "$2" -ne 0 ]] && grep -qE \
    'Unable to load validationEngine|Encountered an exception during validation|Unable to resolve package' "$1"
}

# Drop any signatures matching a documented known-issue PATTERN from $KNOWN_ISSUES.
filter_known_issues() { # reads signatures on stdin
  local patterns=() pat sigs
  mapfile -t patterns < <(grep -E '^PATTERN:' "$KNOWN_ISSUES" 2>/dev/null \
    | sed -E 's/^PATTERN:[[:space:]]*//' || true)
  sigs="$(cat)"
  for pat in "${patterns[@]}"; do
    [[ -z "$pat" ]] && continue
    sigs="$(printf '%s\n' "$sigs" | grep -vF "$pat" || true)"
  done
  printf '%s\n' "$sigs"
}

# --- Validate the requested files --------------------------------------------------- #
mapfile -t FILES < <(expand_glob "$GLOB")
if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "ERROR: no files matched '$GLOB'." >&2
  [[ "$MODE" == "gate" ]] && echo "       Run the processor with --dry-run first." >&2
  exit 2
fi

RAW="$TMPDIR_GATE/validator.txt"
echo "Validating ${#FILES[@]} file(s) from '$GLOB' (FHIR $FHIR_VERSION) with IGs: ${IG_ARGS[*]:-<none pinned>}"
run_validator "$RAW" "${FILES[@]}" && RC=0 || RC=$?
cat "$RAW"
if is_hard_fail "$RAW" "$RC"; then
  echo "ERROR: the validator could not run to completion (exit $RC); see output above." >&2
  exit 2
fi

# --- UPDATE MODE: write the source baseline and exit -------------------------------- #
if [[ "$MODE" == "update" ]]; then
  normalize_errors <"$RAW" | sort -u >"$BASELINE_FILE"
  echo "Wrote $(grep -c . "$BASELINE_FILE" || true) baseline error signature(s) to $BASELINE_FILE"
  echo "Review and commit it. The gate fails on any output error signature not listed here."
  exit 0
fi

# --- GATE MODE: diff output signatures against the committed baseline ---------------- #
if [[ ! -f "$BASELINE_FILE" ]]; then
  echo "ERROR: baseline '$BASELINE_FILE' not found. Generate it once with:" >&2
  echo "         scripts/validate.sh --update-baseline 'test/input/**/*.json' $CONFIG" >&2
  exit 2
fi

normalize_errors <"$RAW" | sort -u >"$TMPDIR_GATE/out.sigs"
OUT_COUNT="$(grep -c . "$TMPDIR_GATE/out.sigs" || true)"
BASE_COUNT="$(grep -c . "$BASELINE_FILE" || true)"

# Introduced = signatures present in output but absent from the baseline, minus known issues.
INTRODUCED_FILE="$TMPDIR_GATE/introduced.sigs"
comm -23 "$TMPDIR_GATE/out.sigs" <(sort -u "$BASELINE_FILE") | filter_known_issues | grep . >"$INTRODUCED_FILE" || true
INTRODUCED_COUNT="$(grep -c . "$INTRODUCED_FILE" || true)"

echo "Delta: ${OUT_COUNT} distinct output error signature(s) vs. ${BASE_COUNT} baseline signature(s)."
if [[ "$INTRODUCED_COUNT" -gt 0 ]]; then
  echo "FAIL: $INTRODUCED_COUNT validator error signature(s) introduced by the transform" >&2
  echo "      (present in output, absent from the source baseline, not a documented known issue):" >&2
  sed 's/^/  - /' "$INTRODUCED_FILE" >&2
  echo "      If these are legitimate upstream/data issues, document them in $KNOWN_ISSUES." >&2
  echo "      If the source fixtures or pinned IG versions changed, regenerate the baseline" >&2
  echo "      with --update-baseline and commit it." >&2
  exit 1
fi

echo "PASS: the transform introduced zero validator errors vs. the source baseline"
echo "      (${BASE_COUNT} inherent source error signature(s); warnings are acceptable)."
