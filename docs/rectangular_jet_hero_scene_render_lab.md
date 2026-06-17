# Rectangular Jet Hero Scene Render Lab

This note records a render-only hero-scene lab for the DualSPHysics
rectangular jet proxy. It reuses existing v4.2 particle and IsoSurface VTK
outputs and does not rerun DualSPHysics.

Required caveat: this remains a modified single-phase DualSPHysics rectangular
inlet jet geometry proxy. It is not a fully atomized spray simulation, not
physical validation, not production CFD, and not experimental agreement.

## Output Root

```text
/home/franco/stack-validation/20260612-rectangular-jet-hero-scene-render-lab
```

Source data:

```text
/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v42-extended-cinematic/medium
```

## Purpose

The v4.2 package is scientifically useful but its full-domain views can still
read as thin or visually flat. This lab shifts to a local hero scene:

- close-framed reconstructed surface
- brighter studio/test-rig environment
- floor, wall, grid, and rectangular nozzle context
- transparent water-like material variants
- fixed camera mini-animation from all available frames
- probe-camera inspection of the final reconstructed surface

The goal is public-review readability, not improved CFD fidelity.

## Reusable Renderer Changes

`scripts/blender_import_legacy_vtk.py` now includes render-lab controls:

- `--surface-material scientific-water`
- `--surface-material opaque-control`
- `--add-nozzle-block`
- `--add-floor-grid`
- `--nozzle-color`
- `--grid-color`
- `--fill-light-energy` / `--fill-light-offset`
- `--rim-light-energy` / `--rim-light-offset`

These options are optional and keep existing renderer defaults intact.

## Selected Recipe

Best local recipe:

- variant: `cam_scientific_water_close_side`
- material: `scientific-water`
- environment: `test_rig_warm_channel`
- render engine: Cycles
- resolution: `1280x720`
- camera: fixed side view with final-frame camera reference

The clear glass-like material was too faint for review; the opaque pale-blue
variant was useful as a control but read more like mesh/plastic than liquid.
The selected material is a lightly tinted transparent-water compromise.

## Local Artifacts

Key generated artifacts:

- still matrix CSV:
  `hero_render_variant_matrix.csv`
- still contact sheet:
  `hero_render_contact_sheet.png`
- best recipe:
  `best_hero_scene_recipe.md`
- acceptance checklist:
  `acceptance_checklist.md`
- mini-animation:
  `rectangular_jet_hero_scene_mini_animation.mp4`
- probe-camera preview:
  `rectangular_jet_hero_probe_preview.mp4`

All generated images, videos, logs, and manifests remain outside Git.

## Limitations

- The source v4.2 medium package provides 18 paired particle/IsoSurface frames;
  all 18 were rendered, but the preferred 20-40 frame mini-animation target was
  not reachable without padding or rerunning simulation.
- The probe preview is a moving camera over the final reconstructed surface
  frame, not additional solver time.
- The result improves lighting, material readability, and camera framing only.
  It does not address the single-phase physics limitation.
