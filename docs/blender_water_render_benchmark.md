# Blender Water Render Benchmark

This note records the render-quality benchmark used to improve the water-like
IsoSurface presentation for the rectangular jet proxy. It is a rendering and
post-processing benchmark only; it does not rerun DualSPHysics and does not
change the scientific status of the case.

Output root:

```text
/home/franco/stack-validation/20260612-blender-water-render-benchmark
```

Primary benchmark files:

- `render_benchmark_preflight.md`
- `blender_capability_report.md`
- `render_variant_matrix.csv`
- `render_benchmark_contact_sheet.png`
- `best_render_recipe.md`
- `water_render_benchmark_mini_animation.mp4`
- `water_render_benchmark_mini_contact_sheet.png`
- `best_recipe_1920_frame_0014.png`

## Main Finding

The strongest improvement came from treating camera framing as part of the
water material recipe. Wide full-domain camera references made the reconstructed
surface appear as a thin line even when the material and lighting were improved.
Close or segment-local camera windows are required for a readable transparent
surface.

Selected recipe:

- render engine: Cycles
- material: `review-water`
- environment: bright studio floor/back/side walls
- light: large area light, high energy
- color management: Filmic, medium high contrast, positive exposure
- surface modifier: `smooth-weighted`
- camera: close, segment-local/current-frame bounds

Reusable command pattern:

```bash
/home/franco/bin/blender-portable --background \
  --python scripts/blender_import_legacy_vtk.py -- \
  --fluid <PartFluid_####.vtk> \
  --iso <Surface_####.vtk> \
  --output <output.png> \
  --style-preset polished \
  --no-caption \
  --render-engine cycles \
  --surface-material review-water \
  --samples 96 \
  --resolution 1280 \
  --camera-preset close \
  --camera-span-scale 0.26 \
  --camera-target-x-fraction 0.42 \
  --camera-target-y-fraction 0.50 \
  --camera-target-z-fraction 0.52 \
  --background-color '#EDF2F4FF' \
  --add-studio-walls \
  --floor-color '#E2E0D8FF' \
  --back-wall-color '#F5EEE4FF' \
  --side-wall-color '#C7D8DEFF' \
  --light-energy 13000 \
  --light-size 4.6 \
  --light-offset=-0.35,-0.68,1.45 \
  --view-transform Filmic \
  --view-look 'Medium High Contrast' \
  --exposure 1.15 \
  --iso-color '#FFFFFFFF' \
  --surface-smoothing smooth-weighted \
  --surface-smooth-factor 0.10 \
  --surface-smooth-iterations 1 \
  --hide-fluid
```

## Limitations

This benchmark produced a better transparent-water inspection recipe, not a
photorealistic render. Existing IsoSurface resolution and sparse reconstructed
geometry still limit surface smoothness. Current-frame camera bounds are useful
for material inspection, but production videos should convert the recipe into
segment-local fixed cameras or deliberate camera paths to avoid unintentional
auto-framing.

The rectangular jet remains a modified single-phase DualSPHysics geometry
proxy. It is not atomized spray simulation, physical validation, production CFD,
or experimental agreement.
