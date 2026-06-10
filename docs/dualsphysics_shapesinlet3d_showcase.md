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
