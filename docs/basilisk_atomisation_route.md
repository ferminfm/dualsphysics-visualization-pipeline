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
