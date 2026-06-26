# Task 04 Visual Gate

Status: `success`

No CFD was run. Rendering used existing Basilisk facet surfaces and Task 03's render-only recipe policy.

## Assets

| Asset | Frames | Resolution | Codec | Pixel format | Path |
| --- | ---: | --- | --- | --- | --- |
| `long_primary_route_blender_sequence_v3` | 101 | 1920x1080 | h264 | yuv420p | `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/long_primary_route_blender_sequence_v3.mp4` |
| `round_vs_rectangular_split_screen_v3` | 101 | 1920x1080 | h264 | yuv420p | `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/round_vs_rectangular_split_screen_v3.mp4` |
| `final_complex_geometry_flythrough_v3` | 72 | 1920x1080 | h264 | yuv420p | `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/04_blender_material_camera_v3/media/final_complex_geometry_flythrough_v3.mp4` |

## Recipe Decision

- Primary sequence: used Task 03 `merged_weighted_normals` through frame 57.
- Late primary frames 58-100: used Task 03 `raw_flat_facets` fallback after weighted-normal Blender segfaults on frame 58.
- Comparison and flythrough: used `raw_flat_facets` fallback with the v3 material, camera, and overlay pass.
- Raw `output_facets(f)` geometry remains the scientific reference.

## Flythrough QA

- visibility_passed: `True`
- failed_frame_count: `0`
- max_fluid_occupancy: `0.6746`
- maximum_consecutive_low_visibility_frames: `0`

## Claim Boundary

`public_ready=false`; `fit_ready=false`; not validation; not production CFD; rectangular route remains a 2:1 rectangular top-hat imposed-inlet comparison, not internal-nozzle flow.
