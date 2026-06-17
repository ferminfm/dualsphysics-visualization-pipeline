# DualSPHysics Rectangular High-Speed Jet Proxy

This document records a modified DualSPHysics inlet-jet geometry proxy derived
from the official `06_Box4Inlet3D` example. The purpose is to create a
non-circular, higher-speed inlet-boundary visualization and geometry-metrics
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
- retained geometry: one rectangular imposed inlet boundary only
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
- retained geometry: one rectangular imposed inlet boundary only
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

## v3 Streamwise-Gravity Rebuild

The v3 rebuild supersedes v2 for the rectangular-jet geometry-proxy workflow.
It keeps the same one-rectangular-inlet framing, but changes the case so gravity
is aligned with the streamwise jet direction instead of pulling the jet across
the render frame.

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v3-streamwise-gravity
```

Final showcase root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v3-streamwise-gravity/showcase
```

Key setup changes relative to v2:

- profile: `v3`
- particle spacing: `dp = 0.025`
- inlet speed: `20 m/s`
- gravity vector: `(9.81, 0, 0)`, aligned with the `+x` jet axis
- physical time: `0.85 s`
- output interval: `0.025 s`
- generated domain: approximately `x = -1.5` to `x = 40.5`
- simulation bounds extended to about `x = 42.0`
- retained geometry: one rectangular imposed inlet boundary only
- post-processing: PartVTK, IsoSurface, pressure, velocity magnitude, and
  moving-slice diagnostics

Run command pattern for the final render package:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v3-streamwise-gravity/showcase \
  --profile v3 \
  --velocity 20 \
  --time-max 0.85 \
  --time-out 0.025 \
  --stations 20 \
  --max-render-frames 6 \
  --fps 6 \
  --velocity-color-max 45 \
  --pressure-color-max 50000 \
  --reuse-existing-run \
  --v3-render-package \
  --cycles-surface
```

Final solver/post-processing summary:

- particle VTK frames: `35`
- IsoSurface frames used for the package: `6`
- metric rows: `359`
- exported fluid particles: up to `291,550`
- exported fields: `Idp`, `Press`, `Rhop`, `Vel`
- axial coordinate range: about `-1.625` to `33.239`
- axial coverage: about `63.2` equivalent nozzle diameters, using the
  rectangular inlet area proxy `0.6 * 0.4`
- pressure view: available from exported `Press`
- velocity-fluctuation energy proxy: computed from per-slice velocity component
  standard deviations; this is not a true turbulence quantity

Final v3 artifacts:

- final stitched MP4:
  `showcase/rectangular_jet_v3_streamwise_gravity_scientific_demonstration.mp4`
- particle provenance MP4:
  `showcase/rectangular_jet_v3_particle_provenance_clean.mp4`
- transparent-water surface-wide MP4:
  `showcase/rectangular_jet_v3_tinted_water_surface_wide_clean.mp4`
- transparent-water surface-hero MP4:
  `showcase/rectangular_jet_v3_tinted_water_surface_hero_clean.mp4`
- velocity-magnitude MP4:
  `showcase/rectangular_jet_v3_velocity_magnitude_clean.mp4`
- pressure MP4:
  `showcase/rectangular_jet_v3_pressure_clean.mp4`
- moving-slice diagnostics MP4:
  `showcase/rectangular_jet_v3_moving_slice_cross_section.mp4`
- moving-slice diagnostics CSV:
  `showcase/metrics/rectangular_jet_v3_moving_slice_diagnostics.csv`
- multiview contact sheet:
  `showcase/rectangular_jet_v3_multiview_contact_sheet.png`
- acceptance checklist:
  `/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v3-streamwise-gravity/acceptance_checklist.md`

The v3 surface pass tested both clear/glass-like and lightly tinted
transparent-water material variants in Blender. The final hero segment uses the
lightly tinted transparent-water material because it reads more clearly than
near-clear water while avoiding an opaque blue/cyan surface. Cycles was used for
the transparent-water surface render. The result should be described as a more
realistic transparent-water render, not as photorealistic fluid.

## v4 Extended-Surface Rebuild

The v4 rebuild is the current extended-duration rectangular-jet proxy package.
It keeps the v3 streamwise-gravity convention but doubles physical duration,
extends the downstream domain, improves the transparent-water render context,
and adds true surface-cut diagnostics driven by a traced particle ID.

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v4-extended-surface
```

Final showcase root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v4-extended-surface/showcase
```

Key setup:

- profile: `v4`
- particle spacing: `dp = 0.025`
- inlet speed: `20 m/s`
- gravity vector: `(9.81, 0, 0)`, aligned with the `+x` jet axis
- physical time: `1.70 s`
- output interval: `0.05 s`
- generated domain: approximately `x = -1.5` to `x = 84.5`
- simulation bound: about `x = 86.0`
- retained geometry: one rectangular imposed inlet boundary only
- rendering: transparent-water IsoSurface with studio floor/back/side walls
- diagnostics: pressure, velocity magnitude, velocity-fluctuation energy proxy,
  tracked-particle surface cuts, and final-frame surface inspection

Run command pattern for the final package:

```bash
python3 scripts/run_rectangular_highspeed_jet_proxy.py \
  --output-root /home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v4-extended-surface/showcase \
  --profile v4 \
  --velocity 20 \
  --time-max 1.7 \
  --time-out 0.05 \
  --stations 24 \
  --max-render-frames 8 \
  --fps 6 \
  --velocity-color-max 55 \
  --pressure-color-max 55000 \
  --reuse-existing-run \
  --v4-render-package \
  --cycles-surface
```

Final solver/post-processing summary:

- particle VTK frames: `35`
- IsoSurface frames used for package: `8`
- metric rows: `414`
- exported fluid particles: up to `580,550`
- exported fields: `Idp`, `Press`, `Rhop`, `Vel`
- axial coordinate range: about `-1.625` to `74.748`
- axial coverage: about `138` equivalent nozzle diameters, using
  `sqrt(4A/pi)` with rectangular inlet area proxy `A = 0.24`
- true surface cuts: `8` plane/IsoSurface intersections
- tracked particle ID used for cuts: `5307451`

Final v4 artifacts:

- final stitched MP4:
  `showcase/rectangular_jet_v4_extended_surface_scientific_demonstration.mp4`
- particle provenance MP4:
  `showcase/rectangular_jet_v4_particle_provenance_clean.mp4`
- transparent-water surface-wide MP4:
  `showcase/rectangular_jet_v4_transparent_water_surface_wide_clean.mp4`
- transparent-water surface-hero MP4:
  `showcase/rectangular_jet_v4_transparent_water_surface_hero_clean.mp4`
- velocity-magnitude MP4:
  `showcase/rectangular_jet_v4_velocity_magnitude_clean.mp4`
- pressure MP4:
  `showcase/rectangular_jet_v4_pressure_clean.mp4`
- velocity-fluctuation proxy diagnostic MP4:
  `showcase/rectangular_jet_v4_moving_slice_cross_section.mp4`
- true surface-cut MP4:
  `showcase/rectangular_jet_v4_surface_cut_cross_sections.mp4`
- final-frame inspection MP4:
  `showcase/rectangular_jet_v4_final_surface_inspection_clean.mp4`
- contact sheet:
  `showcase/rectangular_jet_v4_multiview_contact_sheet.png`
- surface-cut CSV:
  `showcase/metrics/rectangular_jet_v4_surface_cut_diagnostics.csv`
- acceptance checklist:
  `/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v4-extended-surface/acceptance_checklist.md`

The v4 surface-cut method parses the reconstructed IsoSurface triangle mesh and
intersects it with planes normal to the `+x` jet axis. Plane stations are driven
by the traced `Idp` trajectory when available. The result is a literal
surface-intersection diagnostic, not only a fitted rectangle. The
velocity-fluctuation energy view remains a proxy and is not a true turbulence
quantity.

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
- `u_y_mean`, `u_y_std`, `u_z_mean`, `u_z_std`
- `speed_mean`, `speed_std`
- `pressure_mean`, `pressure_std` when `Press` is exported
- `velocity_fluctuation_energy_proxy`, computed from exported velocity
  component spreads and not a true turbulence quantity
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

v3 metric result:

- frames parsed: `35`
- metric rows: `359`
- particle count range per frame: `2,550` to `291,550`
- axial coordinate range: about `-1.625` to `33.239`
- axial coverage: about `63.2` equivalent nozzle diameters
- pressure, velocity magnitude, and velocity-fluctuation proxy diagnostics are
  available from exported particle fields

v4 metric result:

- frames parsed: `35`
- metric rows: `414`
- particle count range per frame: `2,550` to `580,550`
- axial coordinate range: about `-1.625` to `74.748`
- axial coverage: about `138` equivalent nozzle diameters
- tracked-particle surface-cut rows: `8`
- pressure, velocity magnitude, velocity-fluctuation proxy, and surface-cut
  diagnostics are available

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

For the v3 package, use the `rectangular_jet_v3_*` artifacts. The final stitched
video combines particle provenance, transparent-water IsoSurface wide and hero
views, velocity magnitude, pressure, and a moving downstream cross-section
diagnostic. The moving-slice segment follows a diagnostic sampling station in
the metrics, not tagged material particles.

For the v4 package, use the `rectangular_jet_v4_*` artifacts. The final stitched
video adds the longer run, studio-environment transparent-water views, velocity
and pressure views, proxy-energy diagnostics, true plane/IsoSurface
cross-section cuts, and a final-frame surface inspection sequence.

For the v4.1 render-polish package, use:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v41-render-polish
```

This is a render/post-production pass only. It reuses accepted v4 particle VTK,
IsoSurface VTK, metrics, and diagnostic frames; it does not rerun DualSPHysics,
GenCase, PartVTK, or IsoSurface. The pass adds a clearer `review-water`
transparent material, brighter color management, stronger studio lighting,
light neutral floor/back/side materials, cleaner segment labels, and brighter
diagnostic panels.

Main v4.1 artifacts:

- final scientific-demonstration MP4:
  `rectangular_jet_v41_scientific_demonstration.mp4`
- clean surface/analysis animation:
  `rectangular_jet_v41_clean.mp4`
- contact sheet:
  `rectangular_jet_v41_contact_sheet.png`
- report:
  `CODEX_RECTANGULAR_JET_V41_REPORT.md`
- summary:
  `CODEX_RECTANGULAR_JET_V41_SUMMARY.json`

Visual-quality classification: public-preview candidate. The v4.1 contact-sheet
mean luminance is higher than v4 (`66.18` versus `52.19` in the local check),
and the full-resolution surface/cross-section panels are more legible. The
scientific caveat is unchanged.

The accepted v4.1 freeze is:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v41-accepted-v1
```

Final acceptance classification: `accepted_public_preview_candidate`. The
accepted root freezes the final MP4, clean companion MP4, contact sheet,
ffprobe output, SHA256 checksums, artifact manifest, acceptance note, and
YouTube/web metadata draft. Heavy media are not tracked in Git; upload or host
the MP4 externally before embedding it in a public website.

## v4.2 Cinematic-Analysis Pass

The v4.2 pass is a partial follow-up to the accepted v4/v4.1 data package. It
adds a `v42` runner profile, corrected surface-cut centroid diagnostics, a
phase-field inventory, all-available-frame segment rendering, and a final-frame
transparent-surface flyby. It does not supersede the accepted v4.1 freeze
because the intended `3.4 s` longer run was not completed.

Output root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v42-extended-cinematic
```

Showcase root:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v42-extended-cinematic/showcase
```

Key setup and execution notes:

- profile: `v42`
- particle spacing: `dp = 0.025`
- inlet speed: `20 m/s`
- configured gravity: `(9.81, 0, 0)` using the `+x` jet-axis convention
- generated long-domain box: approximately `181 m` streamwise extent
- staged runs completed: GenCase-only, `0.25 s` smoke, and `0.85 s` medium
- intended `3.4 s` longer run: not run in this pass because the full-wall
  domain creates about `12.7M` fixed boundary particles and the smoke/medium
  runtimes made a 2x-v4 all-frame package unreasonable
- exported fields: `Idp`, `Press`, `Rhop`, and `Vel`
- phase status: no separate gas/liquid phase indicator was found, so the
  package remains single-phase geometry-proxy evidence
- preserved solver warning: DualSPHysics reports that only Z gravity is used in
  some inlet/outlet hydrostatic calculations

Main v4.2 artifacts:

- final scientific-demonstration MP4:
  `showcase/rectangular_jet_v42_scientific_demonstration.mp4`
- clean all-frame MP4:
  `showcase/rectangular_jet_v42_clean_all_frames.mp4`
- transparent surface hero MP4:
  `showcase/rectangular_jet_v42_surface_hero.mp4`
- final-frame flyby MP4:
  `showcase/rectangular_jet_v42_cinematic_flyby.mp4`
- true surface-cut cross-section MP4:
  `showcase/rectangular_jet_v42_cross_section_evolution.mp4`
- contact sheet:
  `showcase/rectangular_jet_v42_contact_sheet.png`
- phase inventory:
  `v42_phase_field_inventory.md`
- cross-section audit:
  `v42_cross_section_audit.md`
- acceptance checklist:
  `acceptance_checklist.md`

The v4.2 visual package is a public-preview candidate with a duration blocker.
It improves the cinematic inspection and diagnostic communication, but it is
not a longer-duration accepted replacement for v4.1.

## Hero Scene Render Lab

A follow-up render-only lab reuses the v4.2 medium VTK/IsoSurface frames and
focuses on a local, close-framed hero scene instead of another full-domain
sequence.

```text
$HOME/stack-validation/20260612-rectangular-jet-hero-scene-render-lab
```

The lab adds optional renderer controls for brighter studio/test-rig context,
including a procedural floor grid, rendered inlet-reference block, fill/rim lights,
and material presets for a lightly tinted transparent-water surface and an
opaque control. The selected recipe is a Cycles `scientific-water` material in a
warm test-rig environment with a fixed side camera that keeps the rectangular
inlet reference visible. It produces a still matrix, contact sheet, short mini-animation
from all 18 available v4.2 medium frames, and a final-frame probe-camera
preview.

This pass improves render readability only. It does not rerun the solver,
extend physical duration, or change the single-phase proxy limitation.

## v4.3 Cinematic / Cross-Section Correction

The v4.3 correction package reuses the v4.2 medium PartVTK/IsoSurface frames and
does not rerun DualSPHysics:

```text
$HOME/stack-validation/20260617-rectangular-jet-v43-cinematic-correction
```

Key corrections:

- procedural rendered inlet-boundary reference pre-roll before outflow;
- all 18 available v4.2 paired data frames rendered;
- presentation interpolation for smoother viewing, with the real data-frame
  count documented;
- brighter floor/wall/grid/inlet-boundary context and stronger key/fill/rim lighting;
- improved transparent-water surface presentation;
- 84-frame curved probe fly-through over the final frozen IsoSurface frame;
- fixed Eulerian `x`-station IsoSurface cross-sections normal to the `+x` jet
  axis, with particle-slab centroid/count comparison;
- velocity magnitude, pressure, and velocity-fluctuation energy proxy views.

Final local artifacts:

- `showcase/rectangular_jet_v43_scientific_demonstration.mp4`
- `showcase/rectangular_jet_v43_clean_all_frames.mp4`
- `showcase/rectangular_jet_v43_surface_hero.mp4`
- `showcase/rectangular_jet_v43_curved_probe_flythrough.mp4`
- `showcase/rectangular_jet_v43_surface_cross_section_evolution.mp4`
- `showcase/rectangular_jet_v43_contact_sheet.png`

The cross-section correction demotes the tracked-particle cut to a diagnostic
and uses fixed downstream station cuts for the main geometric story. The
velocity-fluctuation energy panel is a derived proxy, not true turbulence. The
v4.3 package is a public-preview candidate, not validation media.

## Final-Polish v2 Multilingual Publication Package

Before freezing a public artifact, the v2 final-polish pass reuses the v4.3
video segments and generates one single multilingual EN/JA/ES video with
publication-oriented cards and metadata:

```text
$HOME/stack-validation/20260617-rectangular-jet-final-polish-v2-multilingual
```

Outputs include:

- `rectangular_jet_final_polished_multilingual.mp4`
- `rectangular_jet_final_polished_multilingual_clean_visuals.mp4`
- `rectangular_jet_final_polished_multilingual_contact_sheet.png`
- `YOUTUBE_AND_WEB_METADATA_MULTILINGUAL.md`
- `multilingual_card_text_v2.md`
- `pressure_velocity_window_explanation.md`
- `acceptance_checklist.md`

The v2 package adds longer English, Japanese, and Spanish cards in one video;
makes the single-phase SPH method boundary explicit; clarifies that no
gas-phase field or liquid-gas identifier is present; documents that the
rectangular inlet is an imposed boundary condition rather than a resolved
internal nozzle flow; and labels the visible pressure/velocity rectangular
marker as a rendered inlet-boundary reference frame. It is recommended as a
public-preview scientific-computing workflow artifact only.

## Inlet-Marker Audit Correction

The marker-audit correction package should supersede the pre-audit v2 MP4 for
manual upload or freeze decisions:

```text
$HOME/stack-validation/20260617-rectangular-jet-inlet-marker-audit
```

The audit checks the v4.2 XML, v4.3 render logs, and Blender importer behavior.
It classifies the visible pressure/velocity rectangular region as a rendered
inlet-boundary reference frame. It is not a gas phase, measurement window,
solver-resolved physical nozzle, or evidence of internal nozzle flow.

## SprayGeo / Ideal Explorer Metrics Handoff

The v4.1 particle-slab geometry metrics were converted into an analysis-ready
handoff package:

```text
$HOME/stack-validation/20260612-rectangular-jet-metrics-handoff
```

The handoff contains:

- `rectangular_jet_proxy_spraygeo_metrics.csv`: full 414-row
  SprayGeo-compatible solver-proxy metric table.
- `rectangular_jet_proxy_spraygeo_metadata.json`: source metadata, caveats, and
  fit-readiness state.
- `rectangular_jet_proxy_ideal_overlay_area.csv`: 24-station late-frame
  `Ahat(zeta)` overlay for Ideal Momentum Jet Explorer import testing.
- `rectangular_jet_proxy_ideal_overlay_metadata.json`: overlay metadata with
  `fit_readiness = blocked_pending_stationary_window`.
- `metrics_audit.md`: row counts, source columns, axial/time ranges, and
  overlay decision.

The committed SprayGeo repo keeps only a tiny overlay sample under
`results/dualsphysics_rectangular_proxy_handoff/`; the full solver-proxy metric
handoff remains outside Git. The overlay is not stationary, not fit-ready, and
does not perform a model fit. It exists to exercise the cross-repo data
contract from solver-generated metrics into the existing Ideal Momentum Jet
Explorer import surface.

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
- The v3 run aligns gravity with the streamwise direction and extends the
  downstream development window, but it remains a single-phase geometry proxy.
- The v3 pressure and velocity-fluctuation diagnostics are post-processing
  quantities from exported particle fields. The fluctuation-energy value is a
  proxy, not a validated turbulence or atomization metric.
- The v4 run extends duration and domain and adds true surface intersections,
  but it remains a single-phase SPH geometry proxy. The tracked-particle cuts
  depend on reconstructed IsoSurface quality and should be interpreted as
  visualization/geometry diagnostics, not experimental cross-sections.
- The v4.2 package improves all-frame rendering and surface-cut diagnostics,
  but the completed run is `0.85 s`, not the intended `3.4 s` longer run. It is
  therefore a partial cinematic-analysis package, not a new accepted
  longer-duration result.
- The hero-scene render lab improves local lighting, material readability, and
  camera framing only; it should not be presented as better physics or
  validation evidence.
- The v4.3 cinematic/cross-section correction improves presentation and
  diagnostic consistency, but still uses 18 real v4.2 data frames with
  presentation interpolation; it is not new solver evidence.
- The final-polish v2 package improves cards, multilingual metadata, gas-phase
  clarification, and publication readiness only; it does not add new solver
  evidence, gas-phase physics, internal-nozzle resolution, or validation.

## Next Step Toward True Atomization

Use this proxy as a geometry/data-contract exercise only. The next serious
atomization route should use a solver and setup that can represent liquid-gas
interface breakup, such as a bounded Basilisk atomisation-derived VOF workflow,
or a documented OpenFOAM/Basilisk jet case with explicit resolution, threshold,
and post-transient studies.
