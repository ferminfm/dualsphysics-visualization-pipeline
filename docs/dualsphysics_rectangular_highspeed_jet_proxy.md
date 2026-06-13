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

## Upgraded Long-Domain Run

A follow-up run used the same official `06_Box4Inlet3D` base but switched the
runner to the `upgraded` profile. The goal was to turn the first coarse proxy
into a more useful single-rectangular-inlet geometry demonstration with a longer
development distance, higher speed, finer particle spacing, and separate
particle, surface, and velocity-view render segments.

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-upgrade
```

Final showcase output:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-upgrade/showcase
```

Key setup changes:

- profile: `upgraded`
- particle spacing: `dp = 0.03`
- inlet speed: `12 m/s`
- physical time: `0.9 s`
- output interval: `0.02 s`
- retained geometry: one rectangular inlet/nozzle only
- larger computational domain, with the downstream simulation limit raised to
  include the generated boundary extents
- inherited central educational obstacle removed from the modified XML
- fixed-camera render package with separate particle, IsoSurface, and velocity
  post-processing views

Staged execution:

| Stage | Purpose | Status | Notes |
| --- | --- | --- | --- |
| Smoke | GenCase plus short GPU run | success after one domain-limit patch | Initial `simdomain` maximum did not include the generated downstream boundary; the copied case was patched from `x = 13.0` to `x = 14.0`. |
| Medium | Higher-resolution stability check | success | `dp = 0.03`, `12 m/s`, `0.36 s`, 13 particle VTK frames. |
| Showcase | Final bounded demonstration run | success | `0.9 s`, 46 particle VTK frames, 18 IsoSurface frames, 54 rendered PNG frames. |

Showcase solver summary:

- physical time reached: about `0.900023 s`
- solver steps: `30,746`
- PART files: `46`
- maximum simulation particles: `465,042`
- exported fluid-particle range: `1,890` to `115,290`
- excluded particles: `0`
- total solver runtime: about `70.65 s`
- solver-reported GPU memory: about `91.30 MiB`

Generated upgraded artifacts:

- particle provenance MP4:
  `showcase/rectangular_jet_upgrade_particle_provenance_clean.mp4`
- surface hero MP4:
  `showcase/rectangular_jet_upgrade_surface_hero_clean.mp4`
- velocity post-processing MP4:
  `showcase/rectangular_jet_upgrade_velocity_postprocess_clean.mp4`
- stitched scientific-demonstration MP4:
  `showcase/rectangular_jet_upgrade_scientific_showcase.mp4`
- multiview contact sheet:
  `showcase/rectangular_jet_upgrade_multiview_contact_sheet.png`
- metrics CSV:
  `showcase/metrics/rectangular_highspeed_jet_slice_metrics.csv`
- metrics summary JSON:
  `showcase/metrics/rectangular_highspeed_jet_metrics_summary.json`

The upgraded output root is about `1.2G` on disk and is intentionally not
tracked by Git.

Compared with the first proxy, the upgraded run increased the inlet speed from
`4 m/s` to `12 m/s`, reduced particle spacing from `0.05` to `0.03`, increased
maximum simulated particles from `21,105` to `465,042`, increased exported fluid
particles from `8,190` to `115,290`, and extended the observed downstream range
from about `x = 1.56` to about `x = 13.45`. The latest frames approach the
downstream boundary, so the render package emphasizes the pre-boundary
development window and the result should still be read as a bounded jet-geometry
proxy.

## Accepted v2 Rebuild

The v2 rebuild is the accepted review package for this rectangular proxy. It
keeps the same scientific caveat, but fixes the main presentation failures of
the first two attempts: weak downstream framing, coarse appearance, possible
downstream wall interpretation, single-view presentation, and lack of a clear
surface-centered render.

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v2
```

Final showcase root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v2/showcase
```

Key setup changes relative to the first upgraded run:

- profile: `v2`
- particle spacing: `dp = 0.025`
- inlet speed: `15 m/s`
- physical time: `0.70 s`
- output interval: `0.025 s`
- retained geometry: one rectangular inlet/nozzle only
- generated tank boundary: `bottom | left | front | back`, leaving the
  downstream/right side open in the copied case
- larger generated box: about `x = -1.5` to `x = 26.0`
- raised inlet near `z = 3.8` to delay immediate floor interaction
- corrected temporal frame selection so late downstream-development frames are
  included in render packages
- accepted render package with particle provenance, surface-wide, surface-hero,
  and velocity-front views

Run command pattern:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v2/showcase \
  --profile v2 \
  --dp 0.025 \
  --velocity 15 \
  --time-max 0.70 \
  --time-out 0.025 \
  --solver-timeout 7200 \
  --post-timeout 1800 \
  --iso-timeout 1200 \
  --render-timeout 1200 \
  --max-render-frames 20 \
  --stations 28 \
  --min-particles-per-slice 20 \
  --fps 8 \
  --velocity-color-max 22 \
  --v2-render-package \
  --force
```

If the final solver outputs already exist and only the accepted render package
should be regenerated:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v2/showcase \
  --profile v2 \
  --dp 0.025 \
  --velocity 15 \
  --time-max 0.70 \
  --time-out 0.025 \
  --max-render-frames 20 \
  --stations 28 \
  --min-particles-per-slice 20 \
  --fps 8 \
  --velocity-color-max 22 \
  --v2-render-package \
  --reuse-existing-run
```

Staged execution:

| Stage | Purpose | Status | Notes |
| --- | --- | --- | --- |
| GenCase only | copied XML/domain sanity check | success | confirmed one inlet, open downstream boundary, and `15 m/s` inlet speed |
| Smoke | low-cost solver stability | success | `dp = 0.035`, `0.18 s`, `0` excluded particles |
| Medium | finer stability and axial-development check | success | `dp = 0.03`, `0.45 s`, about `22.8` equivalent nozzle diameters |
| Showcase | accepted render/metrics package | success | `dp = 0.025`, `0.70 s`, PartVTK, IsoSurface, metrics, accepted render package |

Final solver summary:

- PART files: `29`
- maximum simulation particles: `1,542,446`
- exported fluid particles: up to `181,050`
- excluded particles: `0`
- solver runtime: about `181.85 s`
- solver-reported GPU memory: about `339.93 MiB`

Accepted v2 artifacts:

- final stitched MP4:
  `showcase/rectangular_jet_v2_accepted_scientific_demonstration.mp4`
- particle provenance MP4:
  `showcase/rectangular_jet_v2_accepted_particle_provenance_clean.mp4`
- surface-wide MP4:
  `showcase/rectangular_jet_v2_accepted_surface_wide_clean.mp4`
- surface-hero MP4:
  `showcase/rectangular_jet_v2_accepted_surface_hero_clean.mp4`
- velocity post-processing MP4:
  `showcase/rectangular_jet_v2_accepted_velocity_postprocess_clean.mp4`
- curated multiview contact sheet:
  `showcase/rectangular_jet_v2_accepted_multiview_contact_sheet.png`
- metrics CSV:
  `showcase/metrics/rectangular_highspeed_jet_slice_metrics.csv`
- acceptance checklist:
  `/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v2/acceptance_checklist.md`

The accepted v2 output root is about `2.7G` on disk and is intentionally not
tracked by Git. The final stitched accepted MP4 is H.264/yuv420p, `1280 x 720`,
`8 fps`, `144` frames, and `18.0 s`.

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

Upgraded showcase metric result:

- frames parsed: `46`
- metric rows: `711`
- particle count range per frame: `1,890` to `115,290`
- axial coordinate range: about `-1.66` to `13.45`
- velocity fields: `u_axial_mean`, `u_axial_std`, `speed_mean`, and
  `speed_std` exported from the particle VTK vectors when available

Accepted v2 metric result:

- frames parsed: `29`
- metric rows: `434`
- particle count range per frame: `2,550` to `181,050`
- axial coordinate range: about `-1.625` to `17.554`
- axial coverage: about `34.7` equivalent nozzle diameters, using the
  rectangular inlet area proxy `0.6 * 0.4`

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

For the upgraded package, the recommended review artifact is the stitched
scientific-demonstration MP4 in the `showcase` directory. It combines a particle
provenance segment, a reconstructed-surface hero segment, and a velocity-colored
post-processing segment. This improves visual framing and data density compared
with the first proxy, but the scientific caveat is unchanged.

For the accepted v2 package, use the `rectangular_jet_v2_accepted_*` artifacts.
The `v2` render path uses a curated contact sheet and fixed views for particle
provenance, surface-wide, surface-hero, and velocity-front segments. The surface
hero is the main visual reference. The velocity segment is useful as a
post-processing view, but scalar contrast is limited because the coherent inlet
stream remains near high speed.

## Limitations

- The case is modified from an educational inlet/outlet example.
- It is single-phase SPH and does not model gas-phase breakup or surface-tension
  atomization.
- The "area" metric is a particle cross-section proxy, not a resolved
  experimental or VOF interface area.
- The first run is short and is not a statistically stationary spray dataset;
  the upgraded run is longer and better resolved, but it is still not a
  statistically stationary spray validation case.
- Higher speed here means a bounded inlet speed increase within the copied
  educational-example geometry, not a validated nozzle or atomizer setup.
- The upgraded run's late frames approach the downstream boundary. Downstream
  metrics near that limit should be treated as visualization/proxy evidence,
  not unconstrained free-jet data.

## Next Step Toward True Atomization

Use this proxy as a geometry/data-contract exercise only. The next serious
atomization route should use a solver and setup that can represent liquid-gas
interface breakup, such as a bounded Basilisk atomisation-derived VOF workflow,
or a documented OpenFOAM/Basilisk jet case with explicit resolution, threshold,
and post-transient studies.
