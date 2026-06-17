# Basilisk Atomisation / VOF Route

## Purpose

This route is the next physics-oriented branch after the DualSPHysics
visualization demos. It uses Basilisk VOF to exercise liquid-gas interface
breakup tooling, preliminary geometry diagnostics, and visualization handoff.

The current result is a bounded atomisation-route demonstration only. It is not
physical validation, not production CFD, not experimental agreement, not
statistically stationary spray data, and not a final atomisation prediction.

## Local Run - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-atomisation-route
```

Selected route:

```text
existing bounded 3D VOF export case
  -> qcc compile
  -> short smoke run
  -> bounded visual run
  -> CSV/VTK/metrics export
  -> native draw_vof check
  -> Blender fallback render and ffmpeg packaging
```

Primary case source:

```text
cases/basilisk/tiny_atomisation3d_export.c
```

The generated working copies and executables are local artifacts under
`stack-validation`; they are not tracked in Git.

## Commands

The bounded visual run used the existing runner:

```bash
python3 scripts/run_basilisk_jet_showcase.py \
  --qcc /home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  --work-dir /home/franco/stack-validation/20260618-basilisk-atomisation-route/visual_run \
  --maxlevel 6 \
  --end-time 0.24 \
  --output-interval 0.02 \
  --uemax 0.05 \
  --timeout-seconds 900 \
  --threshold 0.08 \
  --z-bins 18 \
  --max-points-per-frame 1400
```

The native Basilisk View path requires explicit local view libraries:

```bash
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -grid=octree basilisk_atomisation_bounded_view_demo.c \
  -o basilisk_atomisation_bounded_view_demo \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

Without the `-L.../gl -lglutils -lfb_tiny` flags, the official
`examples/atomisation.c` view path fails at link time on OpenGL/Basilisk View
symbols.

## Results

Bounded visual run:

| Item | Value |
| --- | --- |
| Max level | `6` |
| End time | `0.24` |
| Output interval | `0.02` |
| Runtime | about `51 s` |
| CSV frames | `13` |
| Exported VOF-cell rows | `25,192` |
| VTK point frames | `13` |
| Slice-metric rows | `148` |
| Frame diagnostics | `13` rows |

Main local artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-atomisation-route/basilisk_atomisation_route_vof_demo_slow.mp4
/home/franco/stack-validation/20260618-basilisk-atomisation-route/basilisk_atomisation_route_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-atomisation-route/basilisk_atomisation_route_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-atomisation-route/basilisk_atomisation_route_native_vof_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-atomisation-route/metrics/basilisk3d_jet_slice_metrics.csv
/home/franco/stack-validation/20260618-basilisk-atomisation-route/metrics/basilisk3d_interface_frame_diagnostics.csv
```

The native `draw_vof` pass succeeded for a short five-frame run and proves that
the local Basilisk View route is available when linked correctly. The longer
13-frame Blender render remains more informative for this pass because it uses
all exported VTK frames.

## Metrics Status

The metrics are preliminary VOF/interface diagnostics:

- frame and time
- streamwise station proxy
- area proxy
- centroid
- major/minor extent and aspect ratio
- axial velocity mean and standard deviation
- frame-wise active-cell extent
- coarse connected-component proxy

They are not model-ready spray statistics. The connected-component count is a
cell-adjacency proxy, not a validated droplet counter. No statistically
stationary window was identified.

## Comparison With DualSPHysics Demos

DualSPHysics remains the stronger branch for GPU SPH visualization workflow,
surface reconstruction packaging, and rectangular geometry-proxy handoff.
Basilisk is the more relevant branch for liquid-gas interface evolution,
surface-tension VOF behavior, and future droplet/tagging diagnostics.

The next useful Basilisk step is a bounded native-view wrapper around the
official atomisation-style case with explicit stop time, frame cadence,
`tag()`-based connected-component output, and either a longer stable 3D run or a
carefully labeled 2D/axisymmetric reduction if 3D cost becomes limiting.

## Official-Style Wrapper - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper
```

Reusable wrapper:

```text
cases/basilisk/basilisk_official_atomisation_bounded.c
```

This wrapper adapts the local official Basilisk example:

```text
/home/franco/opt/basilisk-survey-20260606/basilisk/src/examples/atomisation.c
```

It keeps the official atomisation-style ingredients: dense liquid jet into a
lighter phase, VOF, surface tension, sinusoidally modulated inlet velocity,
Basilisk View `draw_vof()` frames, and `tag()` connected-component diagnostics.
It adds explicit bounded controls for `maxlevel`, end time, output interval,
velocity-adaptation tolerance, and frame-count target.

Compile pattern:

```bash
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -grid=octree basilisk_official_atomisation_bounded.c \
  -o basilisk_official_atomisation_bounded \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

Medium bounded run:

```bash
timeout 1200 ./basilisk_official_atomisation_bounded 8 0.5 0.025 0.08 21
```

Run summary:

| Item | Value |
| --- | --- |
| Wrapped source | Basilisk `examples/atomisation.c` structure |
| Max level | `8` |
| End time | `0.5` |
| Output frames | `21` |
| Native rendering | `draw_vof()` PNG frames |
| Component diagnostics | `tag()` CSV frames |
| Max interface-cell rows | `9869` |
| Max tagged components | `7` |
| Final tagged components | `3` |
| Max streamwise extent proxy | about `0.457` Basilisk units |

Main local artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper/basilisk_official_atomisation_medium_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper/basilisk_official_atomisation_medium_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper/metrics/basilisk_official_atomisation_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper/metrics/basilisk_official_atomisation_diagnostics_summary.json
```

This is a real advance beyond the previous voxel/point export proof: native
Basilisk VOF surface frames work, and `tag()` reports late multi-component
interface breakup. It is still internal technical evidence rather than a
public-ready video. The default official camera leaves the interface small in
the frame, the run is short/coarse, no stationary window is defined, and the
component counts are preliminary VOF connected components rather than validated
droplet statistics.

## Rectangular-Slot Gas-Weber Scan - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan
```

Reusable case:

```text
cases/basilisk/rectangular_slot_gas_weber_proxy.c
```

This case uses the official atomisation wrapper only as a template. It changes
the geometry to a short rectangular slot/duct issuing into an external gas
region, and it chooses surface tension from a gas-side Weber-number target. The
design is explicitly a breakup-proxy experiment. Scaled gas density, reduced
surface tension, and imposed transverse inlet perturbations are proxy choices,
not calibrated experimental conditions.

Design summary:

| Item | Value |
| --- | --- |
| Slot size | `W = 1.2`, `H = 0.8`, `W/H = 1.5` |
| Hydraulic diameter | `Dh = 0.96` |
| Internal duct | `10 Dh` |
| External gas region | `20 Dh` |
| Total streamwise domain | `30 Dh` |
| Density ratio | `rho_l/rho_g = 20` |
| Viscosity ratio | `mu_l/mu_g = 25` |
| Target and achieved `We_g` | `50` |
| Achieved `We_l` | about `1000` |
| `Re_l`, `Re_g`, `Oh_l` | `1200`, `1500`, about `0.026` |
| Perturbation | transverse inlet perturbation, amplitude `0.08 U_l`, period `0.18` |

Compile pattern:

```bash
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -grid=octree rectangular_slot_gas_weber_proxy.c \
  -o rectangular_slot_gas_weber_proxy \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

Primary bounded run:

```bash
timeout 1800 ./rectangular_slot_gas_weber_proxy 9 2.0 0.1 50 21
```

Run summary:

| Item | Value |
| --- | --- |
| Primary maxlevel | `9` |
| Slot resolution at maxlevel 9 | about `21 x 14` cells |
| Short maxlevel 10 feasibility | about `43 x 28` cells across slot |
| Primary output frames | `21` |
| Primary time range | `0` to `2.0` |
| Maximum post-exit front | about `1.69 Dh` |
| Maximum `tag()` component count | `1` |
| Detached-volume proxy count | `0` |
| Morphology classification | connected waviness, not atomization |

Main local artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/basilisk_rect_slot_gas_weber_long_vof.mp4
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/basilisk_rect_slot_gas_weber_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/basilisk_rect_slot_gas_weber_projection_diagnostic.mp4
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/basilisk_rect_slot_gas_weber_projection_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/metrics/basilisk_rect_slot_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/metrics/basilisk_rect_slot_component_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/metrics/basilisk_rect_slot_slice_occupancy.csv
/home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan/metrics/basilisk_rect_slot_diagnostics_summary.json
```

The native `draw_vof()` frames were generated successfully, but the large cubic
domain makes the interface small in the native contact sheet. The additional
projection diagnostic is derived from exported VOF cells and is clearer for
reviewing the duct, visual exit plane, and connected post-exit front. It is a
diagnostic projection, not a replacement for a true facet/surface render.

This scan did not produce detached liquid volumes. It is useful as a bounded
negative result: the rectangular-slot geometry, `We_g = 50` setting, and
transverse perturbation produced connected near-exit waviness/bulging over the
available downstream development, not ligament breakup or atomization.
