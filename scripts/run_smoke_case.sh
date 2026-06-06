#!/usr/bin/env bash
set -euo pipefail

WRAPPER="${DUALSPHYSICS_WRAPPER:-/home/franco/bin/dualsphysics5.4-cuda128}"
CASE_INPUT="${1:-}"
OUTPUT_DIR="${2:-outputs/smoke}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"

if [[ ! -x "$WRAPPER" ]]; then
  echo "ERROR: DualSPHysics wrapper not executable: $WRAPPER" >&2
  exit 2
fi

if [[ -z "$CASE_INPUT" ]]; then
  cat >&2 <<'USAGE'
Usage:
  scripts/run_smoke_case.sh CASE_INPUT [OUTPUT_DIR]

Example:
  scripts/run_smoke_case.sh /path/to/CaseDambreak_Def.xml outputs/dambreak
USAGE
  exit 2
fi

if [[ ! -f "$CASE_INPUT" ]]; then
  echo "ERROR: case input not found: $CASE_INPUT" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"
echo "Wrapper: $WRAPPER"
echo "Case: $CASE_INPUT"
echo "Output: $OUTPUT_DIR"
echo "Timeout: ${TIMEOUT_SECONDS}s"

timeout "$TIMEOUT_SECONDS" "$WRAPPER" -gpu "$CASE_INPUT" "$OUTPUT_DIR"

