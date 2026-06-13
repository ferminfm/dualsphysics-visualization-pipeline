# DualSPHysics Rectangular High-Speed Jet Proxy

This document records a modified DualSPHysics inlet-jet geometry proxy derived
from the official `06_Box4Inlet3D` example. The purpose is to create a
non-circular, higher-speed inlet/nozzle visualization and geometry-metrics
workflow using official DualSPHysics tools, not to claim spray validation.

Required caveat: this is a modified DualSPHysics inlet-jet geometry proxy. It is
not a fully atomized spray simulation, not validation, not production CFD, and
not experimental agreement.

## Base Case

- Official package:
  `/home/franco/opt/dualsphysics-full-package-20260611/DualSPHysics_v5.4`
- Base XML:
  `examples/inletoutlet/06_Box4Inlet3D/CaseBox4Inlet3D_Def.xml`
- Selected base reason: `Box4Inlet3D` defines four rectangular inlet seed blocks
  and matching in/out zones. Keeping one seed block and one in/out zone is a
  cleaner rectangular proxy than modifying the multi-shape `05_ShapesInlet3D`
  case.

## Modified Case

Generated case work:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-highspeed-jet/case_work
```

Key XML changes applied by
`scripts/run_rectangular_highspeed_jet_proxy.py`:

- case name: `CaseRectangularHighspeedJetProxy`
- retained only `mkfluid="0"` from `Box4Inlet3D`
- retained only the first matching `inoutzone`
- rectangular inlet seed:
  - point `(-1.5, -1.4, 0.2)`
  - size `(0, 0.6, 0.4)`
  - direction `right`, interpreted as positive `x`
- inlet velocity increased from `2 m/s` to `4 m/s`
- `TimeMax` reduced to `0.8 s`
- `TimeOut` set to `0.02 s`

Run command pattern:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-highspeed-jet \
  --velocity 4.0 \
  --time-max 0.8 \
  --time-out 0.02 \
  --solver-timeout 900 \
  --post-timeout 300 \
  --iso-timeout 180 \
  --render-timeout 300 \
  --max-render-frames 12 \
  --max-surface-frames 8 \
  --stations 12 \
  --fps 6
```

If the solver outputs already exist and only rendering/metrics should be
repeated:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-highspeed-jet \
  --reuse-existing-run
```

## Run Result

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-highspeed-jet
```

Observed solver summary:

- solver exit code: `0`
- physical time: `0.800116 s`
- PART files: `41`
- maximum particles: `21,105`
- fluid particles exported by PartVTK: `702` to `8,190`
- excluded particles: `0`
- total runtime: about `4.92 s`
- solver-reported GPU memory: about `5.09 MiB`

Post-processing outputs:

- particle VTK:
  `case_work/CaseRectangularHighspeedJetProxy_out/particles/PartFluid_0000.vtk`
  through `PartFluid_0040.vtk`
- IsoSurface subset:
  `surface_vtk/Surface_0000.vtk` through selected frames up to
  `Surface_0035.vtk`
- metrics CSV:
  `metrics/rectangular_highspeed_jet_slice_metrics.csv`
- metrics summary:
  `metrics/rectangular_highspeed_jet_metrics_summary.json`
- clean MP4:
  `rectangular_highspeed_jet_proxy_clean.mp4`
- titled showcase MP4:
  `rectangular_highspeed_jet_proxy_showcase.mp4`
- contact sheet:
  `rectangular_highspeed_jet_proxy_contact_sheet.png`

All generated BI4, VTK, PNG, MP4, log, and manifest files remain outside Git.

## Metrics

The script extracts preliminary particle-slice metrics from `PartFluid_*.vtk`.
The jet axis is treated as positive `x`; cross-section coordinates are `y` and
`z`. The output is a geometry proxy for workflow testing.

Metric fields include:

- `frame`
- axial coordinate `z` stored as the mean `x` coordinate of the slice
- `particle_count`
- `centroid_y`, `centroid_z`
- `width_y`, `width_z`
- `area_proxy`
- `Ahat`, using the rectangular inlet area proxy `0.6 * 0.4 = 0.24`
- `aspect_ratio`
- `orientation_deg_yz`
- `u_axial_mean`, `u_axial_std`
- `speed_mean`, `speed_std`
- `quality_flags`

Run result:

- frames parsed: `41`
- metric rows: `380`
- particle count range per frame: `702` to `8,190`
- axial coordinate range: about `-1.77` to `1.56`

## Visualization

The runner renders a bounded subset of frames with the existing headless Blender
legacy VTK importer. It uses fixed `isometric` camera framing, velocity-magnitude
coloring with a deterministic `0` to `6 m/s` range, and optional IsoSurface
overlay when a matching surface frame exists.

MP4 verification:

- titled showcase: `1280 x 720`, H.264/yuv420p, `6 fps`, `60` frames,
  about `10 s`
- clean animation: `1280 x 720`, H.264/yuv420p, `6 fps`, `12` frames,
  about `2 s`

Visual-quality classification: internal technical evidence / early public
preview candidate. The case shows a single rectangular inlet stream and derived
geometry/velocity outputs, but it remains a single-phase SPH inlet proxy.

## Limitations

- The case is modified from an educational inlet/outlet example.
- It is single-phase SPH and does not model gas-phase breakup or surface-tension
  atomization.
- The "area" metric is a particle cross-section proxy, not a resolved
  experimental or VOF interface area.
- The run is short and is not a statistically stationary spray dataset.
- Higher speed here means a modest increase from the official `2 m/s` to
  `4 m/s`, bounded to keep the smoke run stable.

## Next Step Toward True Atomization

Use this proxy as a geometry/data-contract exercise only. The next serious
atomization route should use a solver and setup that can represent liquid-gas
interface breakup, such as a bounded Basilisk atomisation-derived VOF workflow,
or a documented OpenFOAM/Basilisk jet case with explicit resolution, threshold,
and post-transient studies.
