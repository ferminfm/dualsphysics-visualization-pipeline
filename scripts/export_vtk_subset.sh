#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-}"
DEST_DIR="${2:-outputs/vtk-subset}"
MAX_FILES="${MAX_FILES:-20}"
MAX_BYTES="${MAX_BYTES:-20000000}"

if [[ -z "$SOURCE_DIR" ]]; then
  cat >&2 <<'USAGE'
Usage:
  scripts/export_vtk_subset.sh SOURCE_DIR [DEST_DIR]

Environment:
  MAX_FILES=20
  MAX_BYTES=20000000
USAGE
  exit 2
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "ERROR: source directory not found: $SOURCE_DIR" >&2
  exit 2
fi

mkdir -p "$DEST_DIR"
copied=0
bytes=0

while IFS= read -r -d '' file; do
  size=$(stat -c '%s' "$file")
  if (( copied >= MAX_FILES )); then
    break
  fi
  if (( bytes + size > MAX_BYTES )); then
    break
  fi
  cp "$file" "$DEST_DIR/"
  copied=$((copied + 1))
  bytes=$((bytes + size))
done < <(find "$SOURCE_DIR" -type f \( -name '*.vtk' -o -name '*.vtp' -o -name '*.vtu' \) -print0 | sort -z)

echo "Copied files: $copied"
echo "Copied bytes: $bytes"
echo "Destination: $DEST_DIR"

