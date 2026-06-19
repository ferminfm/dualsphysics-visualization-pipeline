# Basilisk Atomisation / VOF Route

## Purpose

This route is the next physics-oriented branch after the DualSPHysics
visualization demos. It uses Basilisk VOF to exercise liquid-gas interface
breakup tooling, preliminary geometry diagnostics, and visualization handoff.

The current result is a bounded atomisation-route demonstration only. It is not
physical validation, not production CFD, not experimental agreement, not
statistically stationary spray data, and not a final atomisation prediction.

The cross-route diagnostics harness is documented in
`docs/basilisk_diagnostics_harness.md`. It consolidates the 2D scout, 3D
rectangular-slot, official-wrapper, micro-translation, and adaptive-refinement
results into a consistent conservative classification table.

The route-level synthesis across DualSPHysics, OpenFOAM, and Basilisk is
summarized in `docs/spray_route_synthesis_decision.md`. The current decision is
that Basilisk remains the most relevant liquid-gas interface route, but current
3D rectangular-slot branches are negative unless a materially different
formulation or future evidence changes the classification.

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

## Rectangular-Slot Morphology Escalation - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation
```

Reusable case:

```text
cases/basilisk/rectangular_slot_morphology_escalation.c
```

This scan escalates the previous negative `We_g = 50` rectangular-slot result
using a parametric case with shorter external domain, high slot resolution,
post-exit-only `tag()` diagnostics, higher gas-Weber targets, stronger
perturbation, and one controlled gas-crossflow proxy. It remains a bounded
physics-route experiment, not public media polish.

Run summary:

| Case | Purpose | Status | `We_g` | Slot resolution | Result |
| --- | --- | --- | ---: | --- | --- |
| A | Longer high-resolution near-exit run | timeout at `t = 1.8` | `50` | about `38 x 26` | one connected post-exit component |
| B | Higher gas-Weber forcing | timeout at `t = 0.643` | `100` | about `43 x 28` | one connected post-exit component |
| C | Stronger instability-proxy forcing | completed to `t = 0.6` | `150` | about `43 x 28` | one connected post-exit component |
| D | Controlled `+y` gas crossflow proxy | timeout before post-exit window | `100` | about `43 x 28` | runtime-limited crossflow attempt |

Main local diagnostics:

```text
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/metrics/morphology_escalation_summary.json
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/metrics/morphology_escalation_case_summary.csv
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/metrics/morphology_escalation_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/metrics/morphology_escalation_component_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/metrics/morphology_escalation_slice_occupancy.csv
```

Decision artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/artifacts/case_A_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/artifacts/case_B_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation/artifacts/case_C_native_vof.mp4
```

No case passed the breakup-proxy gate. The maximum credible post-exit
`tag()` component count remained `1`, and detached-volume proxy count remained
`0`. The result is a useful negative and cost-limiting decision point: before
another expensive 3D maxlevel-9/10 run, use a lower-cost 2D/axisymmetric or
reduced-domain scout to find an instability range for gas shear and surface
tension. Connected waviness is still not atomization.

## 2D/Planar Shear-Sigma Scout - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout
```

Reusable case:

```text
cases/basilisk/planar_slot_shear_sigma_scout.c
```

This branch is a reduced 2D/planar parameter scout, not a faithful 3D
rectangular-slot result. It was added after the expensive 3D morphology
escalation remained negative. The goal is to identify whether any low-cost
gas-Weber, surface-tension, gas-shear, or perturbation setting produces
roll-up, necking, ligament-like elongation, detached components, persistent
credible `tag()` components greater than one, or strong interface-length growth.

Run summary:

| Case | Purpose | Status | `We_g` | Resolution | Result |
| --- | --- | --- | ---: | --- | --- |
| `A_baseline` | 2D sanity and baseline morphology | completed | `80` | about `64` cells across sheet | rolled-up rim with detached-component proxies |
| `E_repeat_A_refine` | maxlevel-11 repeat/refinement of Case A | completed | `80` | about `128` cells across sheet | repeated rolled-up rim and detached-component proxies |

Main local diagnostics:

```text
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/metrics/scout_case_summary.csv
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/metrics/scout_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/metrics/scout_component_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/metrics/scout_parameter_map.json
```

Decision artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/artifacts/A_baseline_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/artifacts/A_baseline_contact_sheet.png
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/artifacts/E_repeat_A_refine_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout/artifacts/E_repeat_A_refine_contact_sheet.png
```

The scout found a reduced-model instability candidate at `We_g = 80` with mild
transverse inlet perturbation and no gas-shear forcing. `A_baseline` reached an
active front of about `3.19 Dh`, with maximum post-exit `tag()` component count
`6`, detached-component proxy count `5`, and post-interface-length growth of
about `9.1x`. The maxlevel-11 repeat reached about `2.47 Dh`, with maximum
post-exit `tag()` component count `4`, detached-component proxy count `3`, and
post-interface-length growth of about `7.1x`.

This is a useful scout signal for the next physics-route decision, but it is
not 3D validation, not stationary spray data, not production CFD, not
experimental agreement, and not final atomisation prediction. The next step is
to translate the successful reduced-model controls back into a carefully
bounded 3D micro-branch, preserving the conservative breakup-proxy gate.

## 3D Micro-Translation of the 2D We_g = 80 Scout - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80
```

Reusable case:

```text
cases/basilisk/rectangular_slot_3d_micro_translation_we80.c
```

This branch translates the positive reduced 2D control window back into a
tightly bounded 3D rectangular-slot case. It preserves the central 2D scout
controls first: `We_g = 80`, mild coherent perturbation (`0.02 U_l`, period
`0.20`), no gas shear, short external domain, and native Basilisk `draw_vof()`
decision artifacts. The purpose is transfer evidence, not public video polish.

Run summary:

| Case | Purpose | Status | `We_g` | Slot resolution | Result |
| --- | --- | --- | ---: | --- | --- |
| `A_direct` | Direct maxlevel-9 translation | resource-limited at `t ~= 0.049` | `80` | about `64 x 43` | no useful post-exit window |
| `B_shorter_domain_prerefine` | Shorter maxlevel-9 domain with limited pre-refinement | runtime-limited at `t ~= 0.028` | `80` | about `80 x 53` | no useful post-exit window |
| `B_affordable_L8` | Affordable maxlevel-8 transfer case | timeout at `t ~= 1.41`, useful frames through `t = 1.35` | `80` | about `40 x 27` | one connected post-exit component |
| `C_seed_geometry_L8` | Seed-geometry sensitivity | timeout at `t ~= 1.14`, useful frames through `t = 1.05` | `80` | about `40 x 27` | one connected post-exit component |
| `D_we100_short_L8` | Small We/sigma sensitivity check | completed to `t = 1.0` | `100` | about `43 x 28` | one connected post-exit component |

Main local diagnostics:

```text
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/metrics/micro_translation_case_summary.csv
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/metrics/micro_translation_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/metrics/micro_translation_component_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/metrics/micro_translation_slice_occupancy.csv
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/metrics/micro_translation_parameter_map.json
```

Decision artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/artifacts/B_affordable_L8_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/artifacts/C_seed_geometry_L8_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80/artifacts/D_we100_short_L8_native_vof.mp4
```

The transfer result is negative for the tested bounded 3D cases. The useful
maxlevel-8 runs reached post-exit active fronts of about `0.91-1.47 Dh`, but
the maximum credible post-exit `tag()` component count remained `1` and the
detached-volume proxy count remained `0`. Interface-area growth occurred while
the liquid stayed connected, so it is recorded as connected waviness/bulging,
not as a 3D breakup-proxy candidate and not as atomization.

The decision point is now clearer: the positive 2D scout does not transfer to
this compact 3D setup under the tested cost bounds. Further 3D work should not
repeat the same `We_g = 80` mild-perturbation settings. A next branch should
either redesign cost control around a smaller physical window and targeted
interface refinement, or test a different gas-shear/coflow/crossflow route with
the same conservative breakup-proxy gate.

## 3D Adaptive Refinement / Sensitivity Map - 2026-06-18

Output root:

```text
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map
```

Reusable case:

```text
cases/basilisk/rectangular_slot_3d_adaptive_refinement_map.c
```

This branch reads the 3D micro-translation summary first and follows the
negative-transfer path. It tests whether a shorter domain, explicit
pre-refinement controls, mild sigma sensitivity, coherent perturbation changes,
and a minimal crossflow proxy can produce credible 3D breakup-proxy topology
around the positive 2D `We_g = 80` window.

Run summary:

| Case | Purpose | Status | `We_g` | Slot resolution | Result |
| --- | --- | --- | ---: | --- | --- |
| `N1_short_highres_L8` | Short-domain high-resolution repeat | timeout at `t ~= 0.116` | `80` | about `91 x 61` | cost-limited before useful post-exit window |
| `N2_sigma_we100_L7_feas` | Lower-burden sigma/We sensitivity | completed to `t = 0.65` | `100` | about `46 x 30` | one credible post-exit component |
| `N3_perturb_z2_L7_feas` | Coherent height-wave perturbation sensitivity | completed to `t = 0.65` | `80` | about `46 x 30` | one credible post-exit component |
| `N4_mild_crossflow_L7_feas` | Mild crossflow proxy | completed to `t = 0.65` | `80` | about `49 x 33` | one credible post-exit component |
| `N5_longer_we80_L7_feas` | Longer low-burden `We_g = 80` check | completed to `t = 1.2` | `80` | about `46 x 30` | connected front; one raw one-cell speck at final frame |

Main local diagnostics:

```text
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/metrics/adaptive_case_summary.csv
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/metrics/adaptive_frame_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/metrics/adaptive_component_diagnostics.csv
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/metrics/adaptive_parameter_map.json
```

Decision artifacts:

```text
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/artifacts/N2_sigma_we100_L7_feas_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/artifacts/N3_perturb_z2_L7_feas_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/artifacts/N4_mild_crossflow_L7_feas_native_vof.mp4
/home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map/artifacts/N5_longer_we80_L7_feas_native_vof.mp4
```

The adaptive map remains negative under the conservative breakup-proxy gate.
The longer low-burden case reached about `1.10 Dh` active front and showed
interface-area growth, but the liquid front stayed connected. A raw `tag()`
count of `2` appeared only at the final frame as a one-cell, tiny-volume side
speck; after a minimum cell-count and volume credibility gate, the maximum
credible post-exit component count remained `1` and the credible detached
proxy count remained `0`.

The decision is now stronger than the first 3D micro-translation: the
high-resolution short-domain branch is still cost-limited on this workstation,
and lower-burden sigma, perturbation, crossflow, and longer-window checks did
not produce credible 3D detached-volume or ligament morphology. The next
physics branch should either change the 3D formulation more substantially,
use targeted interface-window refinement, test different gas-shear forcing, or
move to another solver route, rather than repeating equivalent `We_g = 80`
settings.

## Quasi-2D Periodic-Span Liquid-Sheet Bridge - 2026-06-19

Output root:

```text
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge
```

Reusable case:

```text
cases/basilisk/periodic_span_sheet_bridge.c
```

This branch tests a materially different bridge from the finite-width
rectangular-slot cases. It removes finite side-edge effects by using a compact
3D liquid sheet with a periodic spanwise direction, while preserving the
positive 2D scout controls first: `We_g = 80`, reduced-model surface-tension
scaling, mild coherent perturbation (`0.02 U_l`, period `0.20`), and native
Basilisk `draw_vof()` decision frames. The simple Basilisk octree setup uses a
cubic domain, so span length is tied to domain length; this is documented as a
cost and geometry limitation of this bridge case.

Run summary:

| Case | Purpose | Status | `We_g` | Effective sheet/span resolution | Result |
| --- | --- | --- | ---: | --- | --- |
| `A_direct_periodic_L4` | Direct higher-resolution periodic-span bridge | timeout at `t ~= 0.47`, frames through `t = 0.4` | `80` | about `64` across sheet, `256` across span | insufficient post-exit window |
| `B_shorter_span_L3` | Shorter compact span/domain at maxlevel 8 | manually stopped as cost-limited before next frame | `80` | about `85` across sheet, `256` across span | insufficient post-exit window |
| `D_compact_L3_level7` | Affordable direct periodic bridge | completed to `t = 1.2` | `80` | about `43` across sheet, `128` across span | one connected post-exit component |
| `C_spanwise_seed_level7` | Weak spanwise-seed sensitivity | completed to `t = 1.2` | `80` | about `43` across sheet, `128` across span | one connected post-exit component |
| `E_mild_crossflow_level7` | Mild gas-crossflow proxy | completed to `t = 1.0` | `80` | about `43` across sheet, `128` across span | one connected post-exit component |

Main local diagnostics:

```text
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/metrics/periodic_bridge_case_summary.csv
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/metrics/periodic_bridge_frame_diagnostics.csv
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/metrics/periodic_bridge_component_diagnostics.csv
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/metrics/periodic_bridge_parameter_map.json
```

Decision artifacts:

```text
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/artifacts/D_compact_L3_level7_vof.mp4
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/artifacts/C_spanwise_seed_level7_vof.mp4
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/artifacts/E_mild_crossflow_level7_vof.mp4
/home/franco/stack-validation/20260619-basilisk-periodic-span-sheet-bridge/artifacts/periodic_bridge_contact_sheet.png
```

No periodic-span case passed the conservative bridge gate. The useful compact
runs reached post-exit active fronts of about `0.93-1.12` sheet thicknesses,
but the maximum credible post-exit `tag()` component count stayed `1` and the
credible detached-volume proxy count stayed `0`. The contact sheet shows a
coherent sheet/surface, not ligaments, roll-up with detached structures, or a
3D breakup-proxy candidate. This is a negative transfer result for the tested
periodic-span bridge, not atomization evidence.
