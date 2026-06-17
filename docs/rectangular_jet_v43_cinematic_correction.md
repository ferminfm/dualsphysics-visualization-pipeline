# Rectangular Jet v4.3 Cinematic / Cross-Section Correction

This document records the v4.3 render and analysis correction package for the
DualSPHysics rectangular jet proxy. It reuses existing v4.2 PartVTK and
IsoSurface outputs and does not rerun DualSPHysics.

Required caveat: this remains a modified single-phase DualSPHysics rectangular
inlet jet geometry proxy. It is not a fully atomized spray simulation, not
physical validation, not production CFD, not experimental agreement, not a gas
phase result, and not a true turbulence result.

## Output Root

```text
/home/franco/stack-validation/20260617-rectangular-jet-v43-cinematic-correction
```

Source data:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v42-extended-cinematic/medium
```

## What v4.3 Fixes

The v4.3 pass addresses the remaining presentation and diagnostic issues in the
rectangular jet sequence:

- rectangular nozzle/aperture pre-roll before outflow;
- all available v4.2 data frames rendered;
- presentation interpolation for smoother viewing, without implying additional
  solver frames;
- brighter floor, wall, grid, and nozzle/test-rig context;
- stronger key/fill/rim lighting;
- readable transparent-water surface material;
- real curved probe-camera fly-through over the final frozen IsoSurface frame;
- corrected Eulerian cross-section diagnostics at fixed downstream stations;
- velocity magnitude, pressure, and velocity-fluctuation energy proxy views.

The source v4.2 medium set has 18 paired particle/IsoSurface frames. v4.3 uses
all 18 frames and records that limitation explicitly.

## Final Artifacts

All generated videos, frames, CSVs, logs, and contact sheets remain outside Git.

```text
showcase/rectangular_jet_v43_scientific_demonstration.mp4
showcase/rectangular_jet_v43_clean_all_frames.mp4
showcase/rectangular_jet_v43_surface_hero.mp4
showcase/rectangular_jet_v43_curved_probe_flythrough.mp4
showcase/rectangular_jet_v43_surface_cross_section_evolution.mp4
showcase/rectangular_jet_v43_velocity_magnitude.mp4
showcase/rectangular_jet_v43_pressure.mp4
showcase/rectangular_jet_v43_velocity_fluctuation_proxy.mp4
showcase/rectangular_jet_v43_contact_sheet.png
showcase/artifact_manifest.txt
```

The main scientific-demonstration video is a public-preview candidate, not
validation media.

## Cross-Section Correction

Previous tracked-particle cuts were useful diagnostics but not a stable
Eulerian cross-section story because the station followed a drifting material
particle. v4.3 instead computes fixed `x`-station intersections of the
reconstructed IsoSurface with planes normal to the `+x` jet axis. It also
records particle-slab centroid/count comparisons at the same stations.

Metrics:

```text
metrics/rectangular_jet_v43_eulerian_surface_cross_sections.csv
metrics/rectangular_jet_v43_eulerian_surface_cross_sections.json
metrics/rectangular_jet_v43_velocity_fluctuation_proxy.csv
```

The velocity-fluctuation energy quantity is a derived proxy from exported
particle velocities. It is not a true turbulence field.

## Renderer Support

`scripts/blender_import_legacy_vtk.py` includes reusable options used by v4.3:

- `--add-nozzle-aperture`
- `--add-floor-grid`
- `--camera-offset`
- `--fill-light-energy`
- `--rim-light-energy`
- `--surface-material scientific-water`

These keep the correction reproducible without tracking generated media.
