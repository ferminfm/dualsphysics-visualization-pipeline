# Basilisk 3D VOF Jet Showcase Fallback

## Purpose

This workflow is a fallback when the official DualSPHysics 3D inlet or
impinging-jet XML examples are not locally available. It compiles and runs a
tiny Basilisk 3D VOF smoke/export case, converts liquid/interface cells to
legacy VTK point clouds, extracts preliminary slice metrics, and renders a
headless Blender animation.

It is a solver-generated visualization and data-contract proof. It is not
validated atomization, not production CFD, and not experimental agreement.

## Why Basilisk

The DualSPHysics CUDA executable and postprocessors are available locally, but
the official 3D inlet/open-boundary example directories are missing from the
current checkout. The local DualSPHysics PDFs document examples such as
`05_SHAPESINLET3D`, `06_BOX4INLET3D`, and `8_IMPINGINGJET`, but their XML case
directories must be recovered from the full official package before a safe SPH
jet smoke run can be made.

Basilisk is available locally through `qcc`, and the local source tree includes
the official `examples/atomisation.c`. The tiny case in this repository keeps
only the bounded 3D VOF jet/export structure needed for a safe smoke run.

## Files

- `cases/basilisk/tiny_atomisation3d_export.c`
- `scripts/run_basilisk_jet_showcase.py`
- `scripts/blender_render_basilisk_showcase.py`
- `scripts/run_basilisk_jet_showcase_stable.sh`

Generated CSV, VTK, render frames, MP4 files, and logs should stay outside Git.
Final run artifacts should be written under:

```text
/home/franco/stack-validation/YYYYMMDD-basilisk-jet-showcase
```

Use `/tmp` only for disposable experiments, not for final MP4/contact-sheet,
metrics, summary JSON, or logs intended as durable evidence.

## One-Command Stable Run

For the local workstation, the stable no-argument command is:

```bash
scripts/run_basilisk_jet_showcase_stable.sh
```

It writes to:

```text
/home/franco/stack-validation/$(date +%Y%m%d)-basilisk-jet-showcase
```

The script runs the Basilisk smoke/export case, renders the Blender PNG frames,
and assembles the MP4/contact sheet when `ffmpeg` is available.

## Solver Smoke Run

```bash
OUT_ROOT=/home/franco/stack-validation/$(date +%Y%m%d)-basilisk-jet-showcase

python3 scripts/run_basilisk_jet_showcase.py \
  --qcc /path/to/basilisk/src/qcc \
  --work-dir "$OUT_ROOT" \
  --maxlevel 5 \
  --end-time 0.14 \
  --output-interval 0.035 \
  --threshold 0.08 \
  --timeout-seconds 180
```

The runner writes:

- `log.compile.txt`
- `log.run.txt`
- per-frame Basilisk CSV files
- `data/basilisk3d_jet_cells.csv`
- `vtk/basilisk_jet_points_####.vtk`
- `metrics/basilisk3d_jet_slice_metrics.csv`
- `showcase_summary.json`

The metrics are preliminary geometry proxies. The axial coordinate is stored as
`z` for compatibility with the stationary jet geometry contract, but it comes
from the Basilisk `x` direction. `area_proxy` is an approximate VOF-cell
cross-sectional proxy, not a validated physical spray area.

## Headless Blender Render

```bash
BLENDER=${BLENDER:-$HOME/bin/blender-portable}

"$BLENDER" --background \
  --python scripts/blender_render_basilisk_showcase.py -- \
  --vtk-dir "$OUT_ROOT/vtk" \
  --output-dir "$OUT_ROOT/render_frames" \
  --resolution-x 1280 \
  --resolution-y 720
```

If a Blender wrapper does not pass arguments after `--`, the renderer also
accepts environment variables:

```bash
BASILISK_SHOWCASE_VTK_DIR="$OUT_ROOT/vtk" \
BASILISK_SHOWCASE_OUTPUT_DIR="$OUT_ROOT/render_frames" \
  "$BLENDER" --background \
  --python scripts/blender_render_basilisk_showcase.py
```

Then assemble outside Git with existing local tools, for example:

```bash
ffmpeg -y -framerate 6 \
  -i "$OUT_ROOT/render_frames/basilisk_jet_showcase_%04d.png" \
  -c:v libx264 -pix_fmt yuv420p \
  "$OUT_ROOT/basilisk_jet_showcase.mp4"
```

Contact sheets can also be generated outside Git from the rendered PNG frames.

## Local Smoke Result - 2026-06-09

The local fallback smoke run completed successfully after the official
DualSPHysics 3D inlet examples remained missing from the current checkout.

Run configuration:

| Item | Value |
| --- | --- |
| Solver | Basilisk `qcc` with `-grid=octree` |
| Case | `cases/basilisk/tiny_atomisation3d_export.c` |
| Maximum level | `5` |
| End time | `0.14` |
| Output interval | `0.035` |
| VOF threshold for VTK/metrics | `0.08` |
| Frames exported | `5` |
| Raw VOF-cell rows | `1162` |
| Legacy VTK point frames | `5` |
| Preliminary slice-metric rows | `25` |
| Blender output | `5` PNG frames at `1280 x 720` |
| MP4 | `5.0 s`, H.264/yuv420p, generated outside Git |

Local generated artifact paths for the latest run:

```text
/home/franco/stack-validation/20260609-basilisk-jet-showcase/basilisk_jet_showcase_5s.mp4
/home/franco/stack-validation/20260609-basilisk-jet-showcase/basilisk_jet_showcase_contact_sheet.png
/home/franco/stack-validation/20260609-basilisk-jet-showcase/metrics/basilisk3d_jet_slice_metrics.csv
/home/franco/stack-validation/20260609-basilisk-jet-showcase/showcase_summary.json
```

These paths are local run evidence, not public assets and not committed to Git.
The visual is intentionally coarse and should be described as a preliminary 3D
VOF smoke/export showcase only.

## Scientific Caveats

- The case is intentionally coarse and short.
- It is not statistically stationary.
- It does not resolve a production atomizing spray.
- No experimental validation is claimed.
- The geometry metrics are proxy metrics for pipeline testing.
- The next SPH route remains recovery of the official DualSPHysics 3D inlet
  examples, followed by a tiny bounded smoke case.

## Next Steps

1. Recover the official DualSPHysics full-package examples manually.
2. Run a tiny `05_SHAPESINLET3D` or `8_IMPINGINGJET` smoke case outside Git.
3. Export particle VTK frames and compare the same metrics contract used here.
4. Only after a post-transient window is defined, compute time-averaged jet
   geometry statistics for SprayGeo and the Ideal Momentum Jet Explorer.
