# DualSPHysics CUDA To Headless Blender Visualization Pipeline

Reproducible DualSPHysics CUDA to headless Blender visualization pipeline for
small free-surface SPH portfolio demos.

The active reproducible path is:

```text
DualSPHysics CUDA 12.8
    -> VTK subset export
    -> Python legacy VTK parser
    -> portable Blender headless render
    -> MP4
```

This repository intentionally does not vendor DualSPHysics, VisualSPHysics,
Blender, VTK, CUDA, generated simulation outputs, MP4 files, raw frames, `.blend`
files, logs, or large render artifacts.

## Public Position

This is a visualization-pipeline demo, not production CFD validation. The
dam-break case is a small portfolio preview used to show a reproducible
GPU-to-render workflow. It should not be presented as atomization, spray, or
production multiphase-physics validation.

## Status

- Active renderer: direct Blender VTK fallback using
  `scripts/blender_import_legacy_vtk.py`.
- Final video pipeline: committed source/docs; MP4 generated locally outside
  Git.
- VisualSPHysics: investigated, but full build is held for now because
  `vtkimporter` and `diffuseparticles` require VTK development metadata and
  Blender-compatible Python extension modules.
- Portable Blender: used headlessly through a user-space wrapper such as
  `$HOME/bin/blender-portable`.

See:

- `docs/visualsphysics_decision.md`
- `docs/video_publish_notes.md`

## Preview

The committed still below is a small direct Blender VTK fallback preview. It is
intended for quick repository review only; source VTK files and full validation
artifacts stay outside Git.

![DualSPHysics dam-break VTK fallback preview](assets/dambreak2d_vtk_fallback_0100.png)

The safe four-frame contact sheet uses frames `0000`, `0050`, `0100`, and
`0150`. Frame `0200` was excluded after QA because it showed a data-level late
rebound/free-surface cavity that could be misread as a render defect.

![DualSPHysics dam-break safe four-frame sequence](assets/dambreak2d_safe_sequence_0000_0050_0100_0150.png)

Caption: DualSPHysics dam-break visualization-pipeline preview rendered
headlessly in Blender from prepared legacy VTK frames. Safe four-frame sequence,
frames `0000-0150`.

## Video

The front-view dam-break MP4 was generated locally and intentionally not
committed. Example local artifact path, replace as needed:

```text
$HOME/stack-validation/20260607-0219-dambreak-frontview-final-video/dambreak2d_frontview_final_0000_0150.mp4
```

Committed thumbnail:

![Front-view dam-break video thumbnail](assets/dambreak_frontview_video_thumbnail.png)

Final video facts:

- Duration: about `22.7 s`
- Resolution: `1280 x 720`
- Codec/pixel format: H.264 / `yuv420p`
- View: front orthographic
- Title card: `6 s`
- Closing card: `5 s`
- Frame `0200`: excluded
- Recommended manual hosting: upload as unlisted first

Future YouTube URL: `TBD`

## VisualSPHysics Decision

VisualSPHysics was investigated as a Blender visualization layer. A disposable
UI registration patch showed that its UI can register headlessly in Blender 4.5
after guarded imports, but the real data path still depends on compiled modules:

- `vtkimporter`
- `diffuseparticles`

Those modules require VTK development headers/CMake metadata and extension
modules compatible with portable Blender's Python 3.11 ABI. The active
reproducible path for this portfolio is therefore the direct Blender VTK
fallback, not a full VisualSPHysics build.

## Validated Machine Summary

- Host: `frontera`
- OS: Ubuntu 24.04
- CPU: Intel Core Ultra 9 275HX, 24 threads
- RAM: about 30 GiB usable
- GPU: NVIDIA GeForce RTX 5070 Laptop GPU, about 8 GB VRAM
- NVIDIA driver: `595.71.05`
- Active DualSPHysics CUDA toolkit: `/usr/local/cuda-12.8`
- DualSPHysics GPU executable: validated for small local examples

## DualSPHysics CUDA 12.8 Wrapper

Canonical local wrapper pattern:

```bash
DUALSPHYSICS_WRAPPER=${DUALSPHYSICS_WRAPPER:-$HOME/bin/dualsphysics5.4-cuda128}
```

Example local target executable, replace for your installation:

```bash
$HOME/opt/dualsphysics/DualSPHysics-cuda128-YYYYMMDD/bin/linux/DualSPHysics5.4_linux64
```

Safe usage pattern:

```bash
"$DUALSPHYSICS_WRAPPER" -gpu CASE_INPUT OUTPUT_DIR
```

## Renderer Controls

`scripts/blender_import_legacy_vtk.py` imports a narrow legacy VTK `POLYDATA`
subset directly inside Blender. It supports ASCII or big-endian binary `POINTS`,
triangular `POLYGONS`, and simple point `SCALARS`/`VECTORS`.

Current render controls include:

- Camera presets: `isometric`, `front`, `front-ortho`, `side`, `top`, `close`.
- Orthographic control: `--ortho-scale`.
- Camera lens control: `--camera-lens`.
- Point visibility/downsampling: `--hide-fluid`, `--fluid-stride`,
  `--boundary-stride`, `--marker-scale`.
- Surface visibility: `--hide-iso`.
- Style/material controls: `--style-preset`, `--fluid-color`,
  `--boundary-color`, `--iso-color`, `--background-color`.
- Light controls: `--light-energy`, `--light-size`, `--light-offset`.
- Render quality controls: `--samples`, `--ambient-occlusion`,
  `--no-ambient-occlusion`, `--contact-shadows`, `--no-contact-shadows`.
- Caption controls: `--caption`, `--caption-size`, `--no-caption`.
- Optional `.blend` output: `--blend`, kept outside Git.

`scripts/assemble_dambreak_video.py` assembles already-rendered PNG frames into
an MP4 and supports:

- title and subtitle text,
- closing card text,
- title/closing/simulation durations,
- FPS and output size,
- HUD text for frame/time, particle count, toolchain, and render path,
- HUD timing and alpha controls: `--seconds-per-frame-index`, `--hud-alpha`,
- card/HUD color controls: `--background`, `--foreground`, `--accent`,
- optional QR placeholder controls: `--qr-placeholder`,
  `--qr-placeholder-text`.

## Commands

### 1. Run A Small Smoke Case

```bash
DUALSPHYSICS_CASE=${DUALSPHYSICS_CASE:-$HOME/opt/dualsphysics/DualSPHysics-cuda128-YYYYMMDD/examples/main/01_DamBreak/CaseDambreakVal2D_Def.xml}

scripts/run_smoke_case.sh \
  "$DUALSPHYSICS_CASE" \
  outputs/dambreak-smoke
```

Generated case outputs should remain outside Git or in ignored local output
directories.

### 2. Export A Small VTK Subset

```bash
VTK_SOURCE=${VTK_SOURCE:-$HOME/stack-validation/YYYYMMDD-HHMM-dualsphysics-vtk-prep/vtk}

MAX_FILES=15 MAX_BYTES=20000000 \
  scripts/export_vtk_subset.sh \
  "$VTK_SOURCE" \
  outputs/vtk-subset
```

The export script copies only a bounded subset of `.vtk`, `.vtp`, or `.vtu`
files. Raw VTK files are ignored and should not be committed.

### 3. Render One Front-Orthographic Frame

```bash
VALID=${VALID:-$HOME/stack-validation/YYYYMMDD-HHMM-single-frame-render}
VTK=${VTK:-$HOME/stack-validation/YYYYMMDD-HHMM-dualsphysics-vtk-prep/vtk}
BLENDER=${BLENDER:-$HOME/bin/blender-portable}
mkdir -p "$VALID/renders" "$VALID/blender-config" "$VALID/blender-scripts"
export BLENDER_USER_CONFIG="$VALID/blender-config"
export BLENDER_USER_SCRIPTS="$VALID/blender-scripts"

"$BLENDER" --background \
  --python scripts/blender_import_legacy_vtk.py -- \
  --fluid "$VTK/dambreak2d_fluid_0100.vtk" \
  --boundary "$VTK/dambreak2d_boundary_0100.vtk" \
  --iso "$VTK/dambreak2d_iso_0100.vtk" \
  --output "$VALID/renders/dambreak2d_front_0100.png" \
  --camera-preset front-ortho \
  --ortho-scale 6.2 \
  --fluid-stride 6 \
  --boundary-stride 1 \
  --marker-scale 0.22 \
  --resolution 1280 \
  --style-preset polished \
  --light-energy 850 \
  --light-size 1.8 \
  --light-offset 0.0,-1.25,1.25 \
  --fluid-color 0.18,0.58,0.95,0.16 \
  --iso-color 0.36,0.78,1.0,0.48 \
  --boundary-color 0.78,0.76,0.70,1.0 \
  --ambient-occlusion \
  --contact-shadows \
  --no-caption
```

Use `--hide-fluid` for a cleaner iso-surface-only preview when particle markers
are visually distracting.

### 4. Assemble A Front-View MP4 From Rendered Frames

This command expects PNG frames that have already been rendered outside Git.

```bash
VALID=${VALID:-$HOME/stack-validation/YYYYMMDD-HHMM-dambreak-frontview-video}

python3 scripts/assemble_dambreak_video.py \
  --input "$VALID/frames/raw/dambreak2d_front_0000.png" \
  --input "$VALID/frames/raw/dambreak2d_front_0050.png" \
  --input "$VALID/frames/raw/dambreak2d_front_0100.png" \
  --input "$VALID/frames/raw/dambreak2d_front_0150.png" \
  --frames-dir "$VALID/frames/final" \
  --output "$VALID/dambreak2d_frontview_preview.mp4" \
  --title "DualSPHysics To Headless Blender" \
  --subtitle "Small dam-break visualization-pipeline demo, not production CFD validation" \
  --closing-title "DualSPHysics CUDA -> VTK -> Python -> Headless Blender -> MP4" \
  --closing-subtitle "Frames 0000-0150; frame 0200 excluded after QA" \
  --title-duration 6 \
  --closing-duration 5 \
  --sim-frame-duration 1.0 \
  --fps 24 \
  --width 1280 \
  --height 720 \
  --particle-text "Particles: small prepared VTK subset" \
  --platform-text "DualSPHysics CUDA 12.8 | RTX 5070 Laptop GPU" \
  --render-text "Python legacy VTK parser | Headless Blender render"
```

For the final overnight video, 76 source frames from `0000-0150` step `2` were
rendered front-orthographic and interpolated to 24 fps before HUD/card assembly.
The MP4 stays in a local generated-artifact directory outside Git and is not
committed.

## Reproducible Pipeline

```text
DualSPHysics XML case
        |
        v
GenCase geometry/particle generation
        |
        v
DualSPHysics GPU run via CUDA 12.8 wrapper
        |
        v
Small VTK/output subset export
        |
        v
Python legacy VTK parser inside portable Blender
        |
        v
Headless Blender PNG renders
        |
        v
Python HUD/title/closing card assembly
        |
        v
MP4 for manual external hosting
```

## Scripts

- `scripts/run_smoke_case.sh`: run a small DualSPHysics smoke case through the
  CUDA 12.8 wrapper.
- `scripts/export_vtk_subset.sh`: copy a bounded number of small VTK files into
  a local output subset for visualization testing.
- `scripts/blender_headless_smoke.py`: minimal Blender Python smoke script for
  isolated add-on install/enable checks.
- `scripts/blender_import_legacy_vtk.py`: direct Blender fallback importer for
  small legacy DualSPHysics VTK `POLYDATA` previews.
- `scripts/assemble_dambreak_video.py`: assemble rendered PNG frames into a
  title/HUD/closing-card MP4.

## Data Policy

Do not commit generated datasets above 20 MB. Large VTK, CSV, logs, MP4, render
frames, `.blend` files, and simulation outputs are ignored by `.gitignore` and
should remain under a local generated-artifact directory or another documented
external output directory.

## Current External Reports

Small summaries are kept in `reports/`. Full logs remain outside this repo in
local generated-artifact directories. Example report directory names:

- `20260606-1952-dualsphysics-benchmark-rerun/report.md`
- `20260606-2248-visualsphysics-preflight/report.md`
- `20260606-2252-visualsphysics-headless-smoke/report.md`
- `20260606-2311-blender-vtk-fallback/report.md`
- `20260607-0219-dambreak-frontview-final-video/report.md`
