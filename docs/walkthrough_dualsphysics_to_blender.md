# Walkthrough: DualSPHysics To Blender

This walkthrough explains the developer-facing workflow behind the hosted
DualSPHysics visualization demos:

```text
GPU SPH simulation -> VTK / IsoSurface -> headless Blender -> ffmpeg -> hosted video
```

It is a visualization and post-processing demonstration, not physical
validation, production CFD validation, atomization validation, or experimental
agreement.

## What You Build

The goal is a reproducible media pipeline that a technical reader can inspect:

- run or reuse a bounded DualSPHysics example,
- export particle or surface data into a visualization-friendly format,
- render the data with a deterministic headless Blender script,
- assemble frames into H.264 MP4 with `ffmpeg`,
- keep heavy generated files outside Git,
- publish only lightweight docs, scripts, thumbnails, and hosted video links.

Hosted examples:

- [3D Inlet-Flow Scientific Demonstration](https://youtu.be/eMUbVgLRkHY)
- [DualSPHysics Dam-Break Visualization](https://youtu.be/EDUGMpGn5MI)

## Stable Output Pattern

Use a stable validation root rather than `/tmp` for final artifacts:

```bash
RUN_ROOT="$HOME/stack-validation/YYYYMMDD-dualsphysics-example-name"
RENDER_ROOT="$HOME/stack-validation/YYYYMMDD-dualsphysics-example-name-render"
mkdir -p "$RUN_ROOT" "$RENDER_ROOT"
```

Keep these outside Git:

- BI4 data,
- VTK/VTP exports,
- Blender frame PNGs,
- MP4/MOV/AVI files,
- `.blend` files,
- logs and raw solver output.

Commit only source scripts, documentation, and intentionally small preview
assets.

## Step 1: Produce Or Reuse Solver Output

For the accepted `05_ShapesInlet3D` demonstration, the official case came from
the DualSPHysics full package. The source-only GitHub clone did not contain all
official example XML directories.

The reliable pattern was:

```bash
chmod +x /path/to/DualSPHysics_v5.4/bin/linux/*
find /path/to/DualSPHysics_v5.4/examples -type f -name 'xCase*_linux64*.sh' -exec chmod +x {} +

RUN_ROOT="$HOME/stack-validation/YYYYMMDD-dualsphysics-shapesinlet3d-official"
mkdir -p "$RUN_ROOT"
rsync -a /path/to/DualSPHysics_v5.4/ "$RUN_ROOT/DualSPHysics_v5.4/"

cd "$RUN_ROOT/DualSPHysics_v5.4/examples/inletoutlet/05_ShapesInlet3D"
timeout 45m bash ./xCaseShapesInlet3D_linux64_GPU.sh < /dev/null \
  > "$RUN_ROOT/xCaseShapesInlet3D_linux64_GPU.log" 2>&1
```

The script produced `PartFluid_*.vtk` frames through the official post-process
path. Do not commit those frames.

## Step 2: Render Particle Data

The direct fallback renderer reads legacy VTK point data and renders it in
portable/headless Blender:

```bash
blender --background --python scripts/blender_import_legacy_vtk.py -- \
  --input-dir "$RUN_ROOT/DualSPHysics_v5.4/examples/inletoutlet/05_ShapesInlet3D/CaseShapesInlet3D_out/particles" \
  --input-pattern 'PartFluid_*.vtk' \
  --output-dir "$RENDER_ROOT/frames" \
  --width 1280 \
  --height 720
```

Particle rendering is useful because it preserves SPH provenance. It can look
coarse when particle density is low or when particles are rendered as visible
markers.

## Step 3: Render Reconstructed Surface Data

For `05_ShapesInlet3D`, a later pass used the DualSPHysics
`IsoSurface_linux64` postprocessor to reconstruct a smoother free surface from
existing solver outputs. This produced a more fluid-like view for the accepted
scientific-demonstration video.

Surface rendering is visually stronger, but it is still a post-processing
choice. It does not turn an official visualization example into validated
spray, atomization, or production CFD evidence.

## Step 4: Assemble Frames Deterministically

Avoid fragile shell globs for final MP4 assembly. Use ordered source-frame
resolution and a canonical frame directory when needed:

```bash
python3 scripts/assemble_dambreak_video.py \
  --input-dir "$RENDER_ROOT/frames" \
  --input-pattern 'inlet3d_*.png' \
  --frames-dir "$RENDER_ROOT/frames_canonical" \
  --output "$RENDER_ROOT/dualsphysics_showcase.mp4" \
  --fps 12 \
  --width 1280 \
  --height 720
```

Verify with `ffprobe` and a visual review before publishing. The repaired
ShapesInlet3D MP4 issue was an assembly/frame-selection problem, not a solver
failure.

## Step 5: Publish Links, Not Media

The public repo should link to hosted videos and small thumbnails, not carry
large media:

```markdown
[3D Inlet-Flow Scientific Demonstration](https://youtu.be/eMUbVgLRkHY)

[![Front-view dam-break video thumbnail](assets/dambreak_frontview_video_thumbnail.png)](https://youtu.be/EDUGMpGn5MI)
```

Keep the caveat close to the link:

```text
Visualization and post-processing demonstration; not physical validation.
```

For the dam-break video:

```text
GPU SPH to Blender workflow demonstration; not production CFD validation.
```

## Developer Takeaway

The useful artifact is not just the final video. It is the reproducible path:

- stable output roots,
- command-line solver and post-processing steps,
- deterministic frame handling,
- headless rendering,
- explicit caveats,
- small Git footprint,
- hosted media links for public review.
