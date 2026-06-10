#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_ROOT="/home/franco/stack-validation/$(date +%Y%m%d)-basilisk-jet-showcase"
QCC="${QCC:-/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc}"
BLENDER="${BLENDER:-/home/franco/bin/blender-portable}"

mkdir -p "$OUT_ROOT"
cd "$REPO_ROOT"

python3 scripts/run_basilisk_jet_showcase.py \
  --qcc "$QCC" \
  --work-dir "$OUT_ROOT" \
  --maxlevel 5 \
  --end-time 0.14 \
  --output-interval 0.035 \
  --threshold 0.08 \
  --timeout-seconds 180

if [ ! -x "$BLENDER" ]; then
  printf 'ERROR: Blender executable not found or not executable: %s\n' "$BLENDER" >&2
  exit 1
fi

BASILISK_SHOWCASE_VTK_DIR="$OUT_ROOT/vtk" \
BASILISK_SHOWCASE_OUTPUT_DIR="$OUT_ROOT/render_frames" \
  "$BLENDER" --background \
  --python scripts/blender_render_basilisk_showcase.py

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -framerate 1 \
    -i "$OUT_ROOT/render_frames/basilisk_jet_showcase_%04d.png" \
    -c:v libx264 -pix_fmt yuv420p \
    "$OUT_ROOT/basilisk_jet_showcase_5s.mp4"

  ffmpeg -y -framerate 1 \
    -i "$OUT_ROOT/render_frames/basilisk_jet_showcase_%04d.png" \
    -vf tile=3x2:margin=12:padding=6:color=0x20252e \
    -frames:v 1 -update 1 \
    "$OUT_ROOT/basilisk_jet_showcase_contact_sheet.png"
else
  printf 'WARNING: ffmpeg not found; PNG frames were rendered but MP4/contact sheet were not assembled.\n' >&2
fi

printf 'BASILISK_JET_SHOWCASE_OUTPUT=%s\n' "$OUT_ROOT"
