# CODEX TASK 04 REPORT

Task: `04_blender_material_camera_v3`

Status: `success`

Final marker:

`TASK_04_BLENDER_V3_WRITTEN: /home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/CODEX_TASK_04_REPORT.md`

## Scope

Rendered v3 internal-review Blender media from existing Basilisk facet surfaces. No CFD solver was run, no checkpoint was advanced, no public upload/deploy/push was performed, and readiness remains `public_ready=false`, `fit_ready=false`.

## Inputs

- Task 04 runbook snapshot under `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/runbook_snapshot/basilisk/20260626-long-benchmark-postprocess-publicprep-batch`
- Task 03 recipe: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/03_smooth_render_surface_pipeline/SMOOTH_RENDER_SURFACE_RECIPE.json`
- Official round surfaces: `/home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/03_long_official_round_control/surfaces`
- Rectangular comparison surfaces: `/home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/04_long_rectangular_production/surfaces`

## Outputs

- Primary v3 sequence: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/long_primary_route_blender_sequence_v3.mp4`
- Round/rectangular v3 comparison: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/round_vs_rectangular_split_screen_v3.mp4`
- Flythrough v3: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/final_complex_geometry_flythrough_v3.mp4`
- Asset manifest: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/TASK04_ASSET_MANIFEST.json`
- Visual gate: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/TASK04_VISUAL_GATE.md`
- Frame mapping: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/manifests/TASK04_FRAME_MAPPING.csv`
- Contact sheets: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/contact_sheets`
- Stills: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/stills`
- ffprobe JSON: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/metadata`
- Render logs: `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/logs`

## Render Decisions

The v3 pass improved material and overlays with a nonmetallic transparent-liquid material, moderated specular response, brighter studio lighting, staged flythrough camera, and final ffmpeg-burned readable caveat panels.

Task 03's selected `merged_weighted_normals` recipe was used for primary frames 0-57. Blender segfaulted on weighted-normal rendering at frame 58, so the documented Task 03 fallback `raw_flat_facets` was used for primary frames 58-100, all comparison frames, and the static-frame flythrough. This keeps coordinates and topology unchanged and preserves raw facets as the scientific reference.

## Validation

- Primary sequence: 101 frames, 1920x1080, H.264, yuv420p.
- Comparison sequence: 101 exact-time pairs, 1920x1080, H.264, yuv420p.
- Flythrough: 72 frames, 1920x1080, H.264, yuv420p.
- Flythrough visibility gate passed with 0 failed frames and max consecutive low-visibility frames of 0.
- JSON outputs parse with `python3 -m json.tool`.
- Visual check performed on the primary still and flythrough contact sheet after overlay correction.

## Warnings

- Weighted-normal rendering became unstable on late complex official-round frame 58 in Blender 4.5.10. The fallback is explicitly documented and render-only; it does not alter scientific diagnostics.
- The comparison remains a visual comparison only. It is not a resolution-invariance proof and does not make the rectangular route public-ready.

## Recommended Next Step

Proceed to Task 05 field-visualization media using Task 02's field availability limits. Keep pressure visualization blocked unless a valid nonzero pressure range is recovered.
