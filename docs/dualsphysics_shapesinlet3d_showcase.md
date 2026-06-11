# DualSPHysics Official 05_ShapesInlet3D Showcase Run

## Purpose
Official DualSPHysics v5.4 3D inlet/open-boundary showcase case run for credible solver-generated VTK particle data suitable for Blender visualization pipeline. This is part of the public scientific-computing / CFD visualization portfolio.

This is an official DualSPHysics 3D inlet/open-boundary visual showcase and geometry-extraction preparation step only. Not production CFD, not validated atomization, not statistically stationary spray validation, and not experimental agreement.

## Package and Paths
- Official full package (source of examples + binaries):
  `/home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4`
- Stable working copy root (preserves official relative paths like `../../../bin/linux/...`):
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official`
- Case working directory (run location):
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/DualSPHysics_v5.4/examples/inletoutlet/05_ShapesInlet3D`
- Full run log:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/xCaseShapesInlet3D_linux64_GPU.log`
- Artifact manifest:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/artifact_manifest.txt`
- Generated outputs live under:
  `.../05_ShapesInlet3D/CaseShapesInlet3D_out/`

All heavy outputs (BI4, VTK, data/, logs) kept outside Git.

## Permission Fix (no sudo)
```bash
chmod +x /home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4/bin/linux/*
find /home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4/examples -type f -name 'xCase*_linux64*.sh' -exec chmod +x {} +
```
Verified:
- GenCase_linux64, DualSPHysics5.4_linux64, PartVTK_linux64, IsoSurface_linux64
- xCaseShapesInlet3D_linux64_GPU.sh

## Working Copy Creation
```bash
mkdir -p /home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official
rsync -a /home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4/ \
      /home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/DualSPHysics_v5.4/
```
Full tree copied (~1.7 GB) to keep official script relative paths stable. Original package modified only for +x.

## Run Command
```bash
cd /home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/DualSPHysics_v5.4/examples/inletoutlet/05_ShapesInlet3D
timeout 45m bash ./xCaseShapesInlet3D_linux64_GPU.sh < /dev/null \
  > /home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official/xCaseShapesInlet3D_linux64_GPU.log 2>&1
```

- GPU: NVIDIA GeForce RTX 5070 Laptop GPU (8151 MiB)
- OMP threads observed: 16 (solver)
- Completed to PART 0100
- Stdin redirection prevents "Press any key" hang at script end (script itself may exit 1 due to interactive pause; simulation pipeline reached "All done")

## What Succeeded
- GenCase v5.4.354.01: domain setup, boundary particles (no initial fluid per inlet design)
- DualSPHysics5 v5.4.355 (GPU): full simulation with inlet/outlet open boundaries, fluid particles injected and tracked to 100 parts
- Built-in post: PartVTK + PartVTKOut produced per-part VTKs for both fluid and excluded/out particles
- All steps completed; "All done" in log

## Key Outputs (see artifact_manifest.txt for full list + sizes)
- Main state: `CaseShapesInlet3D_out/CaseShapesInlet3D.bi4`
- Per-part binary data: `CaseShapesInlet3D_out/data/Part_00XX.bi4` (0000..0100)
- GenCase VTKs: `CaseShapesInlet3D_All.vtk`, `CaseShapesInlet3D_Bound.vtk`, config VTKs
- Particle VTKs (ready for Blender):
  - `CaseShapesInlet3D_out/particles/PartFluid_0000.vtk` .. `PartFluid_0100.vtk`
  - `CaseShapesInlet3D_out/particles/PartFluidOut_00XX.vtk` (outlet/excluded, increasing count late in run)
- Run metadata: `Run.csv`, `RunPARTs.csv`, `Run.out`, `CaseShapesInlet3D.xml`, `CaseShapesInlet3D.out`
- Full log and manifest at output root

Particle count grew from ~5k to >100k+ fluid as inlet operated (exact final in log/RunPARTs.csv).

## Caveats
- Visualization and pipeline showcase only. The XML and execution follow the official example exactly; no custom physics or validation performed here.
- Not suitable for claiming production CFD results, atomization fidelity, spray statistics, or experimental match.
- Uses official inlet/outlet 3D shapes example as the closest public 3D open-boundary inlet demo in the v5.4 package.
- Outputs are in the copied working tree under stack-validation/ (outside this repo).
- Original package left untouched except executable bits.

## Next Step: Blender Visualization
Use the generated `PartFluid_*.vtk` (and optionally PartFluidOut) as input to the existing legacy VTK Blender importer path in this repo:

- `scripts/blender_import_legacy_vtk.py` (or similar direct VTK point cloud loader)
- Headless Blender render to frames + MP4 (outside Git)
- Target: credible 3D inlet/jet particle visualization from official DualSPHysics solver data

Typical workflow (adapt paths):
```bash
# Example (outside Git output dir)
blender --background --python scripts/blender_import_legacy_vtk.py -- \
  --input-dir /path/to/CaseShapesInlet3D_out/particles \
  --pattern 'PartFluid_*.vtk' --frame-range 0 100 --step 10 ...
```

See prior docs for exact Blender headless patterns used on dam-break VTKs and Basilisk exports.

## Verification Commands Run Post-Run
- git status (clean before docs)
- df -h checks
- nvidia-smi
- Permission + executable verification
- Log inspection for "All done", particle VTK writes, no "aborted" or permission errors
- Tracked heavy-artifact scan (none in Git)
- bash -n / py_compile on repo scripts

## References
- Official case: `examples/inletoutlet/05_ShapesInlet3D`
- Script: `xCaseShapesInlet3D_linux64_GPU.sh`
- Tools: GenCase_linux64, DualSPHysics5.4_linux64, PartVTK_linux64, PartVTKOut (via script)

## Render Pipeline (Headless Blender VTK)

After solver success, rendered the 101 PartFluid VTK point clouds to PNG frames + MP4/contact sheet using the repo's existing legacy VTK Blender pipeline.

**Render output root (stable, outside Git):**
`/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-render`

**Key artifacts:**
- Frames (101): `frames/inlet3d_0000.png` ... `inlet3d_0100.png`
- Repaired animation-only MP4 (~11.22s @9fps, 101 frames, 1280x720, H.264 yuv420p): `dualsphysics_official_inlet3d_showcase_fixed.mp4`
- Repaired titled MP4 (~22.22s @9fps, 200 frames, 1280x720, H.264 yuv420p): `dualsphysics_official_inlet3d_showcase_fixed_titled_short.mp4`
- Original MP4 with assembly issue, kept for provenance: `dualsphysics_official_inlet3d_showcase.mp4`
- Contact sheet (3x3 key evolution): `inlet3d_official_contact_sheet.png`
- Previews (every-10th): `previews/inlet3d_preview_*.png`
- Logs + `artifact_manifest.txt`

**Render commands / params (used):**
- Preflight + inspect: `scripts/blender_import_legacy_vtk.py`, `assemble_dambreak_video.py`, `blender_render_basilisk_showcase.py` (reference), stable basilisk sh pattern.
- Preview (11 frames): loop over 0000/0010/.../0100 with `--camera-preset isometric --marker-scale 3.0 --fluid-stride 4 --resolution 1280 --style-preset polished --samples 32 --caption "Official DualSPHysics 3D inlet example — visualization demo, not validation"`
- Full (101 frames): same but `--fluid-stride 2 --samples 24 --marker-scale 2.5` (denser, 16:9 via patch to script default + y= *0.5625)
- Patch: minimal edit to `scripts/blender_import_legacy_vtk.py` (default res 1280, 16:9 ratio) for video-ready output.
- MP4 repair: canonical sequence created from `frames/inlet3d_*.png` as `frames_canonical/frame_%05d.png`, then encoded with:
  `ffmpeg -y -framerate 9 -i frames_canonical/frame_%05d.png -c:v libx264 -pix_fmt yuv420p dualsphysics_official_inlet3d_showcase_fixed.mp4`
- MP4 + titles/HUD: use the safer deterministic input resolver:
  `python3 scripts/assemble_dambreak_video.py --input-dir "$RENDER_ROOT/frames" --input-pattern 'inlet3d_*.png' --min-input-frames 101 --frames-dir "$RENDER_ROOT/frames_titled_fixed_short" --output "$RENDER_ROOT/dualsphysics_official_inlet3d_showcase_fixed_titled_short.mp4" --fps 9 --width 1280 --height 720 --sim-frame-duration 0.111111 ...`
- Contact: PIL grid (3x3) from key frames 0000,0012,...,0100 (resized tiles)

**MP4 repair note (2026-06-11):**
The first MP4 was diagnosed as an assembly issue, not a solver or Blender render failure. The true animation sequence `frames/inlet3d_*.png` contains 101 unique rendered frames. The generated `frames/frame_*.png` family used by the first assembly contained only three unique images because the assembly command effectively consumed too few source frames. `scripts/assemble_dambreak_video.py` now supports `--input-dir`, `--input-pattern`, `--input-glob`, and `--min-input-frames` so source frames are resolved deterministically inside Python rather than by fragile shell glob usage.

## Branded Showcase Render

Output root:
`/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-branded-render`

This pass re-rendered the same 101 official `PartFluid_*.vtk` frames, with no
solver rerun. It uses a cleaner camera/framing setup, no in-scene caption, a
brighter cyan water material, and the new optional `--marker-style icosahedron`
particle marker for a less faceted particle-cloud look.

Branding is restricted to intro/outro cards so no text overlaps the active
fluid view:

- `Fermín Franco-Medrano, Ph.D.`
- `Computational Scientist | UABC Ensenada Campus · IMI, Kyushu University`
- `Official DualSPHysics 3D inlet example`
- `GPU SPH visualization workflow — not validation`

Artifacts:

- Main branded MP4: `dualsphysics_shapesinlet3d_branded_showcase.mp4`
- Clean no-text animation: `dualsphysics_shapesinlet3d_clean_animation.mp4`
- Branded contact sheet: `dualsphysics_shapesinlet3d_branded_contact_sheet.png`
- Diagnosis/report files: `visual_quality_diagnosis.md`, `CODEX_BRANDED_RENDER_REPORT.md`

Render parameters:

- `--marker-style icosahedron`
- `--marker-scale 2.0`
- `--fluid-stride 3`
- `--camera-preset isometric`
- `--camera-lens 70`
- `--samples 96`
- `--fluid-color "#42C7FFFF"`
- `--background-color "#071018FF"`
- `--no-caption`

Verification:

- Clean animation: 101 frames, 101 unique encoded frame hashes, 1280x720,
  H.264/yuv420p, 12 fps, about 8.42 s.
- Branded version: 137 frames including title/outro cards, 1280x720,
  H.264/yuv420p, 12 fps, about 11.42 s.

Public-use classification: **public preview candidate**. It is stronger and
cleaner than the first technical render, but it is still a particle-cloud
visualization. Closer-to-photorealistic water would require surface
reconstruction, a denser/spray-oriented simulation, or a solver output that
provides a clean interface/mesh field.

## Multiview Showcase v2

Output root:
`/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-showcase-v2`

This second polish pass supersedes the first branded preview as the recommended
public review artifact. It still uses only the existing official
`PartFluid_*.vtk` frames; DualSPHysics was not rerun.

Changes from the first branded render:

- Fixed camera bounds from `PartFluid_0100.vtk` to remove auto-follow /
  auto-crop motion.
- Three fixed camera views:
  - View A: oblique hero angle.
  - View B: side/profile angle.
  - View C: top/plan view.
- Dam-break-style dark title/section/outro cards with cyan accent color.
- Intro card includes software, hardware, pipeline, case summary, and caveat.
- Outro card includes frame count, final particle count, rendered views,
  classification, and caveat.
- Optional analysis segment uses VTK `Vel` FIELD data binned by velocity
  magnitude. This is an analysis visualization cue, not a validation result.

Artifacts:

- Clean fixed-camera multiview animation:
  `dualsphysics_shapesinlet3d_multiview_clean.mp4`
- Branded multiview showcase:
  `dualsphysics_shapesinlet3d_multiview_showcase.mp4`
- Contact sheet:
  `dualsphysics_shapesinlet3d_multiview_contact_sheet.png`
- Handoff:
  `CODEX_SHOWCASE_V2_REPORT.md`, `CODEX_SHOWCASE_V2_SUMMARY.json`

Verification:

- Clean multiview clip: 303 frames, 303 unique encoded frame hashes,
  1280x720, H.264/yuv420p, 12 fps, 25.25 s.
- Branded showcase: 489 frames, 1280x720, H.264/yuv420p, 12 fps,
  40.75 s.
- Analysis coloring: `Vel` FIELD data present in VTK and rendered as binned
  velocity-magnitude colors for a short segment.

Public-use classification: **public preview candidate**. The v2 clip is a
stronger presentation artifact than the earlier single-view render, but it is
still a solver-generated visualization demo, not fully atomized spray
validation, statistically stationary spray validation, production CFD, or
experimental agreement.

**Visual notes:**
- The original render used faceted point markers and an in-frame caption; it is
  useful as technical evidence but less polished.
- The branded render uses smoother icosahedron markers and removes in-scene
  captions, keeping title/identity text on intro/outro cards only.
- Isometric oblique camera placement keeps the three inlet shapes readable while
  showing downstream particle-cloud evolution.
- 1280x720 16:9, H.264/yuv420p, clean for local portfolio review.
- The repaired and branded MP4s verify as ordered, non-static sequences.

**Caveats (repeated):**
This is official DualSPHysics solver-generated 3D inlet particle visualization preparation. Not production CFD, not validated atomization/spray, no experimental agreement. For public portfolio pipeline demo only. Heavy outputs (frames, MP4, contact, logs, .blend if any) stay outside Git under the stable render root.

**Public preview candidate:** Yes — the MP4 + contact sheet + selected frames provide a credible first visual of the official 3D inlet case for the visualization portfolio. Update README if one-sentence link added.

**Next:** Optional tighter camera crop, higher quality samples, or VisualSPHysics if built later; or Basilisk cross-comparison.

## Surface Render Pass

Output root:
`/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-surface-render`

This pass uses only the existing successful official `05_ShapesInlet3D` outputs.
DualSPHysics was not rerun. The official `IsoSurface_linux64` postprocessor
reads the existing `Part_*.bi4` files and writes legacy VTK polygon meshes,
which are rendered by the same headless Blender fallback importer using
`--iso` and `--hide-fluid`.

Primary command:

```bash
python3 scripts/run_shapesinlet3d_surface_showcase.py \
  --frames 20:100:4 \
  --fps 3 \
  --samples 48 \
  --resolution 1280
```

Artifacts:

- Clean surface animation:
  `dualsphysics_shapesinlet3d_surface_clean.mp4`
- Branded surface showcase:
  `dualsphysics_shapesinlet3d_surface_showcase.mp4`
- Surface contact sheet:
  `dualsphysics_shapesinlet3d_surface_contact_sheet.png`
- Generated surface VTK files:
  `surface_vtk/Surface_0020.vtk` ... `Surface_0100.vtk`
- Handoff:
  `CODEX_SURFACE_RENDER_REPORT.md`, `CODEX_SURFACE_RENDER_SUMMARY.json`

Verification:

- IsoSurface frame subset: 21 frames (`0020, 0024, ..., 0100`)
- Clean animation: 21 frames, 1280x720, H.264/yuv420p, 3 fps, 7.0 s
- Branded showcase: 48 frames including title/outro, 1280x720,
  H.264/yuv420p, 3 fps, 16.0 s

Visual-quality verdict: **public preview candidate**. The surface render is
more fluid-like than the particle-cloud render because it hides marker faceting
and reconstructs continuous inlet columns and the downstream free surface. It
still shows interpolation texture and sparse-data limitations, so the strongest
public story remains a visualization workflow rather than physical validation.

Recommended use:

- Use the v2 multiview particle showcase when the goal is solver provenance and
  raw SPH particle evolution.
- Use the surface render when the goal is a smoother, more water-like portfolio
  preview.
- A final public video could combine both: raw particle view followed by
  reconstructed surface view.

## Final Scientific-Demonstration Package

Output root:
`/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-final-package`

This package combines the strongest already-generated views into one polished
scientific-demonstration video. It does not rerun the solver or regenerate
Blender views. It uses:

- raw particle provenance from the fixed-camera v2 particle render,
- reconstructed free-surface frames from the IsoSurface render pass, and
- velocity-magnitude analysis frames from existing VTK `Vel` field data.

Primary command:

```bash
python3 scripts/build_shapesinlet3d_final_package.py
```

Artifacts:

- Main final video:
  `dualsphysics_shapesinlet3d_final_scientific_demo.mp4`
- Clean companion video:
  `dualsphysics_shapesinlet3d_final_clean.mp4`
- Final contact sheet:
  `dualsphysics_shapesinlet3d_final_contact_sheet.png`
- Handoff:
  `CODEX_FINAL_PACKAGE_REPORT.md`, `CODEX_FINAL_PACKAGE_SUMMARY.json`

Verification:

- Main final video: 417 frames, 1280x720, H.264/yuv420p, 12 fps,
  34.75 s.
- Clean companion video: 261 frames, 1280x720, H.264/yuv420p, 12 fps,
  21.75 s.
- Segment structure: intro card, raw particle provenance, reconstructed
  surface, velocity-magnitude analysis, outro summary.

Recommended public-use classification: **public showcase candidate after manual
review**. It is the best single artifact for explaining the simulation-to-
visualization workflow because it includes solver provenance, surface
reconstruction, and analysis-oriented coloring. It remains a scientific
demonstration and workflow artifact, not atomization validation, statistically
stationary spray validation, production CFD, or experimental agreement.

## Verification (post-render)
- git diff --check, py_compile scripts/*.py, bash -n scripts/*.sh (after patch)
- ffprobe on MP4 (1280x720 h264 yuv420p confirmed)
- artifact_manifest.txt (217 entries)
- heavy scan (no new .mp4/.png etc committed to Git)
- git status clean on main (docs + 1 small script patch only)
