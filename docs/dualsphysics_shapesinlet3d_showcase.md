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

**Visual notes:**
- Isometric oblique camera + faceted point markers (scale 2.5-3) produce legible 3D jet/lobe structures evolving over time (compact inlet → multi-finger spray-like).
- Not sparse dots; chunky visible particle volumes.
- Caption included on frames.
- 1280x720 16:9, clean for portfolio.
- The repaired MP4 has a normal size for this frame sequence and verifies as 101 unique encoded frames.

**Caveats (repeated):**
This is official DualSPHysics solver-generated 3D inlet particle visualization preparation. Not production CFD, not validated atomization/spray, no experimental agreement. For public portfolio pipeline demo only. Heavy outputs (frames, MP4, contact, logs, .blend if any) stay outside Git under the stable render root.

**Public preview candidate:** Yes — the MP4 + contact sheet + selected frames provide a credible first visual of the official 3D inlet case for the visualization portfolio. Update README if one-sentence link added.

**Next:** Optional tighter camera crop, higher quality samples, or VisualSPHysics if built later; or Basilisk cross-comparison.

## Verification (post-render)
- git diff --check, py_compile scripts/*.py, bash -n scripts/*.sh (after patch)
- ffprobe on MP4 (1280x720 h264 yuv420p confirmed)
- artifact_manifest.txt (217 entries)
- heavy scan (no new .mp4/.png etc committed to Git)
- git status clean on main (docs + 1 small script patch only)
