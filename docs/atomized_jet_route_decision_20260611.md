# Atomized Jet Route Decision - 2026-06-11

## Purpose

Identify the shortest credible path from the current official DualSPHysics
inlet visualization success toward an actual atomized, liquid-gas, or
spray-like jet simulation on this workstation.

No solver, compiler, renderer, downloader, installer, or heavy workflow was run
for this memo. This is an inspection and route decision only.

## Current Milestone

Achieved milestone:

- Official DualSPHysics full package:
  `/home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4`
- Official run output root:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-official`
- Render output root:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-render`
- Fixed MP4:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-render/dualsphysics_official_inlet3d_showcase_fixed.mp4`
- Repo commit documenting the MP4 repair:
  `d975bdf Fix DualSPHysics inlet MP4 assembly`

This is a real official DualSPHysics v5.4 GPU run and a repaired MP4 assembly.
The run reached `All done`, exported `PartFluid_0000.vtk` through
`PartFluid_0100.vtk`, and exported outlet/excluded particle VTKs through
`PartFluidOut_0100.vtk`.

## Why ShapesInlet3D Is Not A Spray Result

`05_ShapesInlet3D` is valuable as a 3D inlet/open-boundary visualization proof:
it injects and exports a growing SPH particle field from official DualSPHysics
case files. It is not a fully atomized spray result because:

- it uses the standard `DualSPHysics5.4_linux64` path, not the liquid-gas
  multiphase executable;
- it does not include a gas phase, phase interface model, surface tension
  breakup model, droplet tagging, or droplet statistics;
- it has no stationarity window, time averaging, grid/particle sensitivity, or
  validation against experiment;
- the visual can look spray-like, but the honest claim is "official 3D inlet
  particle visualization", not atomization physics.

## Official DualSPHysics Inventory

Inspected package areas:

- `examples/mphase_liquidgas`
- `examples/inletmesh`
- `examples/inletoutlet/08_ImpingingJet`
- package-wide filename/content hits for `jet`, `spray`, `liquidgas`,
  `mphase`, `inlet`, `outflow`, `droplet`, `impact`, `nozzle`, `atomiz`,
  and `breakup`
- `src_mphase/DSPH_v4.0_LiquidGas`
- `bin/linux`
- `bin/linux/DSNNewtonian`

Key finding: I did not find an official DualSPHysics example that combines a
liquid-gas multiphase solver with a jet inlet/nozzle atomization setup.
The package has two separate families:

- liquid-gas examples using `DualSPHysics4.0_LiquidGas_linux64`;
- jet/inlet/open-boundary examples using standard `DualSPHysics5.4_linux64`.

### Candidate Routes

| Candidate | Official path | What it is | Closest target | Main limitation |
| --- | --- | --- | --- | --- |
| Basilisk official atomisation reference | `/home/franco/opt/basilisk-survey-20260606/basilisk/src/examples/atomisation.c` | Pulsed dense liquid jet in lighter phase, surface tension, VOF, droplet tagging, Basilisk View movie output | Actual atomization physics | Not DualSPHysics; default case is not bounded by an explicit stop event and needs a safe wrapper/settings before running |
| Basilisk tiny repo export | `cases/basilisk/tiny_atomisation3d_export.c` | Bounded 3D VOF jet/export case derived from the atomisation structure | Fast liquid-gas jet proxy and Blender data path | Deliberately coarse, short, not validated, not stationary |
| DualSPHysics `mphase_liquidgas/06_SurfaceTension` | `examples/mphase_liquidgas/06_SurfaceTension` | Heavy-water sphere in water, `FlowType=2`, `surfcoef=0.5`, `TimeMax=0.5` | Surface-tension droplet/interface behavior | No gas phase in this case and no jet/nozzle |
| DualSPHysics `mphase_liquidgas/02_ObstacleImpact` | `examples/mphase_liquidgas/02_ObstacleImpact` | Water/air impact with obstacle, `FlowType=2`, `TimeMax=3` | Liquid-gas impact/splash proxy | Transient impact, not inlet jet or atomization |
| DualSPHysics `mphase_liquidgas/01_DamBreak` | `examples/mphase_liquidgas/01_DamBreak` | Water/air dam-break, `FlowType=2`, `TimeMax=3` | Liquid-gas free-surface proxy | Dam-break, not jet/spray |
| DualSPHysics `mphase_liquidgas/03_WetDamBreak` | `examples/mphase_liquidgas/03_WetDamBreak` | Water/air wet dam-break, `TimeMax=0.7` | Liquid-gas transient proxy | Dam-break, not jet/spray |
| DualSPHysics `mphase_liquidgas/04_SloshingTank` | `examples/mphase_liquidgas/04_SloshingTank` | Water/air sloshing, `TimeMax=8.35` | Liquid-gas interface benchmark | Long and not jet-like |
| DualSPHysics `inletoutlet/08_ImpingingJet` | `examples/inletoutlet/08_ImpingingJet` | 2D top inlet at `20 m/s`, left/right outlets, `TimeMax=0.1` | Fast official impinging jet visual | Single-phase SPH/open-boundary case, no atomization |
| DualSPHysics `inletmesh/01_Basic/CaseJet3dMeshVel1` | `examples/inletmesh/01_Basic` | 3D mesh-data inlet jet, magnitude velocity CSV, `TimeMax=5` | 3D jet/inletmesh visual | Single-phase SPH, no gas/surface tension |
| DualSPHysics `inletmesh/01_Basic/CaseJet3dMeshVelDir` | `examples/inletmesh/01_Basic` | 3D mesh-data inlet jet, vector velocity CSV, `TimeMax=8` | 3D directional inlet proxy | Single-phase SPH, no gas/surface tension |
| DualSPHysics `inletmesh/01_Basic/CaseJet3dMeshZsurf` | `examples/inletmesh/01_Basic` | 3D inlet with variable Z-surface mesh data, `TimeMax=6` | 3D inlet/free-surface visual | Single-phase SPH, no atomization |
| OpenFOAM VOF route | local OpenFOAM v2406 | CPU/MPI VOF path for custom jet work | Applied CFD fallback | Longer case setup; no current local direct spray-jet pipeline in this repo |

## Rankings

### A. Most Physically Relevant

1. Basilisk official `atomisation.c`, wrapped safely or adapted from the repo
   tiny case. It directly models a pulsed liquid jet in a lighter phase with
   VOF, surface tension, and droplet tagging.
2. DualSPHysics `mphase_liquidgas/02_ObstacleImpact` or
   `06_SurfaceTension`, because they exercise liquid-gas or surface-tension
   machinery, but they are not jets.
3. OpenFOAM custom VOF jet, because it can be physically relevant but requires
   more setup before it is a local, bounded, reproducible path.
4. DualSPHysics `08_ImpingingJet` and `inletmesh/01_Basic`, because they are
   jet-like but not liquid-gas atomization cases.

### B. Fastest To Visually Compelling MP4

1. DualSPHysics `inletoutlet/08_ImpingingJet`: official, short `TimeMax=0.1`,
   standard postprocessing to particle VTKs, likely fastest official
   DualSPHysics follow-up. Claim only "2D impinging jet visualization".
2. Basilisk tiny repo export: already has bounded CSV to VTK to Blender to MP4
   plumbing and prior regenerated evidence.
3. DualSPHysics `inletmesh/01_Basic/CaseJet3dMeshVel1`: official 3D jet-like
   inletmesh path, but longer than the 2D impinging jet and not atomization.
4. DualSPHysics liquid-gas examples: physically more relevant than standard
   SPH, but not visually aligned with a jet/spray portfolio target.

### C. Best For SprayGeo Geometry Metrics

1. Basilisk tiny repo export: already emits VOF-cell CSV, VTK point frames, and
   reduced slice metrics with `physical_validation=false`.
2. Basilisk official `atomisation.c` after a bounded export wrapper: best future
   source for droplet counts, interface geometry, and post-transient metrics.
3. DualSPHysics 3D inlet/inletmesh VTKs: good particle geometry source, but
   needs a clear particle-to-area proxy and should not be treated as liquid-gas
   interface area.
4. DualSPHysics `08_ImpingingJet`: fast visual source, weak SprayGeo value
   because it is 2D and impinging, not a stationary free jet.
5. OpenFOAM VOF: good future source, but slower to reach the current repo's
   existing metrics/render pipeline.

### D. Lowest Hardware Risk

1. Basilisk tiny repo export at `maxlevel=5`, `end_time=0.14`, timeout 180 s:
   prior regenerated output exists and the case has an explicit stop event.
2. DualSPHysics `08_ImpingingJet`: official `TimeMax=0.1` and standard v5.4
   GPU path, but it should still run only from a copied tree under
   `/home/franco/stack-validation`.
3. DualSPHysics `06_SurfaceTension`: short liquid-gas/surface-tension case, but
   it uses the older `DualSPHysics4.0_LiquidGas_linux64` executable that has not
   been validated here as recently as the v5.4 inlet path.
4. OpenFOAM custom VOF jet: CPU/MPI route, low GPU risk but higher setup risk.

## Recommendation

Use **Basilisk next** for the first honest move toward actual liquid-gas
atomization.

Recommended next executable case:

- Start with the repo's bounded `cases/basilisk/tiny_atomisation3d_export.c`
  route, not the unbounded official `atomisation.c` as-is.
- Use the existing runner:
  `scripts/run_basilisk_jet_showcase.py`
- Run with conservative settings:
  `--maxlevel 5 --end-time 0.14 --output-interval 0.035 --threshold 0.08 --timeout-seconds 180`
- Write all raw outputs outside Git under a fresh
  `/home/franco/stack-validation/YYYYMMDD-HHMM-basilisk-atomisation-route`
  directory.

Why this recommendation:

- It is the shortest path that is actually liquid-gas/interface based.
- It already has a bounded stop event and CSV/VTK/metrics export.
- It can feed Blender and SprayGeo-style geometry metrics immediately.
- It avoids claiming that a single-phase SPH inlet visual is atomization.

DualSPHysics should still be used next if the immediate goal is an **official
DualSPHysics visual follow-up** rather than atomization physics. In that case,
run `examples/inletoutlet/08_ImpingingJet` first, because it is official,
jet-named, short, and uses the standard postprocessing path. Label it as a 2D
impinging-jet/open-boundary visualization, not a spray or atomization result.

OpenFOAM should not be the next step for this specific portfolio path unless
the goal changes to applied VOF case construction. It is better kept as the
CPU/MPI backup after Basilisk has provided a bounded atomization-like interface
dataset.

## Expected Output From The Recommended Next Case

Exact expected output, using the existing repo runner:

- `log.compile.txt`
- `log.run.txt`
- `basilisk3d_jet_frame_0000.csv` through about `0004.csv`
- `data/basilisk3d_jet_cells.csv`
- `vtk/basilisk_jet_points_0000.vtk` through about `0004.vtk`
- `metrics/basilisk3d_jet_slice_metrics.csv`
- `showcase_summary.json`
- optional Blender frames under `render_frames/`
- optional MP4/contact sheet if the render/ffmpeg step is explicitly included

Prior regenerated evidence from the same bounded route produced:

- 5 CSV frames
- 1162 raw VOF-cell rows
- 5 VTK point frames
- 25 reduced metric rows
- 1280x720 MP4 under
  `/home/franco/stack-validation/20260609-basilisk-jet-showcase-regenerated`

These are pipeline and geometry-proxy outputs only. They are not validation,
stationarity, or production atomization evidence.

## Risk And Runtime Estimate

| Route | Expected runtime class | Hardware risk | Scientific risk |
| --- | --- | --- | --- |
| Basilisk tiny bounded route | Low; existing runner uses 180 s timeout for solver stage | Low | Medium if overclaimed; safe if labeled as coarse VOF interface proxy |
| Basilisk official `atomisation.c` as-is | Medium to high without a stop wrapper; previous local L5 runs used timeout artifacts | Medium | Low-to-medium physically, but unsafe operationally until bounded |
| DualSPHysics `08_ImpingingJet` | Low-to-medium; official `TimeMax=0.1`, but still a GPU/SPH case | Low-to-medium | High if called atomization |
| DualSPHysics `mphase_liquidgas/06_SurfaceTension` | Low-to-medium; short `TimeMax=0.5` | Medium until v4.0 LiquidGas path is revalidated | Medium because it is surface-tension interface behavior, not jet |
| OpenFOAM custom VOF jet | Medium | Low GPU risk; CPU/MPI only unless proven otherwise | Medium until setup and validation plan exist |

## Next Prompt To Run The Selected Case

```text
Work only in:
/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio

TASK:
Run a bounded Basilisk atomisation-route smoke/export case toward the
stationary spray geometry pipeline. Do not run any DualSPHysics case in this
turn.

Constraints:
- no sudo
- no installs
- no downloads
- no push
- keep all raw CSV, VTK, PNG, MP4, logs, and binaries outside Git under:
  /home/franco/stack-validation/YYYYMMDD-HHMM-basilisk-atomisation-route
- do not claim validated atomization or stationarity

Run:
- preflight qcc path and repo case source
- python3 scripts/run_basilisk_jet_showcase.py with:
  --maxlevel 5
  --end-time 0.14
  --output-interval 0.035
  --threshold 0.08
  --timeout-seconds 180
- inspect showcase_summary.json and metrics CSV row counts
- optionally render Blender frames and MP4 only if the solver/export result is
  nonempty

Verification:
- git diff --check
- python3 -m py_compile scripts/*.py
- bash -n scripts/*.sh
- tracked heavy artifact scan
- git status --short --branch

Report:
- exact output root
- row/frame/VTK/metric counts
- whether MP4 was produced
- caveats
- no push confirmation
```

## Stop Rules

- Do not rerun `05_ShapesInlet3D` for this route decision.
- Do not run official Basilisk `atomisation.c` without adding an explicit
  bounded stop or using a strict timeout plan.
- Do not merge DualSPHysics inlet and liquid-gas XML concepts by hand and call
  it official.
- Do not use dam-break, sloshing, impact, or inlet-only visuals as a substitute
  for stationary atomization metrics.
- Keep `physical_validation=false` until a validation protocol exists.
