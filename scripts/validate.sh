#!/usr/bin/env bash
#
# Conformance gate (constitution Principle III, gate 1): validate the JSON the processor
# would submit against the HL7 FHIR Reference Validator, using IG versions pinned in the
# run config. Run this over dry-run output BEFORE any real (non-dry-run) submission.
#
# Usage:
#   scripts/validate.sh [OUTPUT_GLOB] [CONFIG]
#     OUTPUT_GLOB  files to validate           (default: output/**/*.json)
#     CONFIG       config with ig_versions{}   (default: config.json, falls back to
#                                               config.example.json)
#
# Exit status: 0 = zero project-introduced errors (after filtering documented known
# issues); non-zero otherwise.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

OUTPUT_GLOB="${1:-output/**/*.json}"
CONFIG="${2:-config.json}"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="config.example.json"
fi

VALIDATOR_JAR="validator_cli.jar"
FHIR_VERSION="4.0.1"
KNOWN_ISSUES="known-validation-issues.md"

if [[ ! -f "$VALIDATOR_JAR" ]]; then
  echo "ERROR: $VALIDATOR_JAR not found in repo root. Download the HL7 FHIR Reference Validator." >&2
  exit 2
fi
if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: Java is required to run $VALIDATOR_JAR but was not found on PATH." >&2
  exit 2
fi

# --- Read IG versions from config (stdlib Python; zero-dependency) ----------------- #
read_ig() {
  python3 - "$CONFIG" "$1" <<'PY'
import json, sys
cfg, key = sys.argv[1], sys.argv[2]
try:
    with open(cfg) as fh:
        data = json.load(fh)
    print((data.get("ig_versions") or {}).get(key, ""))
except Exception:
    print("")
PY
}

ECR_IG_VERSION="$(read_ig hl7.fhir.us.ecr)"
US_CORE_VERSION="$(read_ig hl7.fhir.us.core)"
DEQM_VERSION="$(read_ig hl7.fhir.us.davinci-deqm)"
APHL_VERSION="$(read_ig aphl.chronic-ds)"

# --- Build versioned -ig arguments (skip unpinned TODO_PIN placeholders) ----------- #
IG_ARGS=()
add_ig() { # name version
  local name="$1" ver="$2"
  if [[ -z "$ver" || "$ver" == "TODO_PIN" ]]; then
    echo "WARNING: IG '$name' is not pinned (value='${ver:-<empty>}'); skipping its -ig arg." >&2
    echo "         Pin it in $CONFIG.ig_versions for a reproducible gate (constitution II)." >&2
    return
  fi
  IG_ARGS+=("-ig" "${name}#${ver}")
}
add_ig hl7.fhir.us.ecr "$ECR_IG_VERSION"
add_ig hl7.fhir.us.core "$US_CORE_VERSION"
add_ig hl7.fhir.us.davinci-deqm "$DEQM_VERSION"
add_ig aphl.chronic-ds "$APHL_VERSION"

echo "Validating '$OUTPUT_GLOB' (FHIR $FHIR_VERSION) with IGs: ${IG_ARGS[*]:-<none pinned>}"

# --- Collect documented known-issue PATTERNs to filter ----------------------------- #
mapfile -t KNOWN_PATTERNS < <(grep -E '^PATTERN:' "$KNOWN_ISSUES" 2>/dev/null | sed -E 's/^PATTERN:[[:space:]]*//' || true)

# --- Run the validator -------------------------------------------------------------- #
set +e
VALIDATOR_OUTPUT="$(java -jar "$VALIDATOR_JAR" "$OUTPUT_GLOB" -version "$FHIR_VERSION" "${IG_ARGS[@]}" 2>&1)"
set -e
echo "$VALIDATOR_OUTPUT"

# --- Count error lines, minus documented known issues ------------------------------ #
ERROR_LINES="$(echo "$VALIDATOR_OUTPUT" | grep -E '^\s*(Error|error) ' || true)"
if [[ -n "$ERROR_LINES" && "${#KNOWN_PATTERNS[@]}" -gt 0 ]]; then
  for pat in "${KNOWN_PATTERNS[@]}"; do
    [[ -z "$pat" ]] && continue
    ERROR_LINES="$(echo "$ERROR_LINES" | grep -vF "$pat" || true)"
  done
fi

REMAINING="$(echo "$ERROR_LINES" | grep -c . || true)"
if [[ "$REMAINING" -gt 0 ]]; then
  echo "FAIL: $REMAINING project-introduced validator error(s) after known-issue filtering." >&2
  exit 1
fi

echo "PASS: zero project-introduced validator errors (warnings are acceptable)."
