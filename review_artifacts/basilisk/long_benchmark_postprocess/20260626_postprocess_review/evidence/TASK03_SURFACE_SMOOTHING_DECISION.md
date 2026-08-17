# Surface Smoothing Decision

Task: `03_smooth_render_surface_pipeline`

Decision: use `merged_weighted_normals` as the Task 04 render-only recipe.

This recipe keeps the raw Basilisk `output_facets(f)` coordinates unchanged,
merges exactly coincident vertices only in the Blender presentation mesh, sets
smooth normals, and applies Blender weighted normals. It is not diagnostic
geometry. All scientific metrics and claim gates must continue to use raw
facets.

## Tested Frames

| Route | Selected frames | Purpose |
| --- | --- | --- |
| Official circular control | 25, 50, 98, 100 | onset-near, mid-run, safe hero, final |
| Rectangular top-hat comparison | 30, 50, 98, 100 | onset-near, mid-run, safe hero, final |

Both routes had 101 existing facet frames. No solver run or time advancement was
performed.

## Variant Gate

| Variant | Safe frames | Max bbox drift | Max area drift | Decision |
| --- | ---: | ---: | ---: | --- |
| `raw_flat_facets` | 8/8 | 0 | 0 | Scientific/reference fallback |
| `merged_smooth_normals` | 8/8 | 0 | 0 | Safe, but weighted normals are preferred |
| `merged_weighted_normals` | 8/8 | 0 | 0 | Selected render-only recipe |
| `simple_subdivision_weighted_normals` | 0/8 | 0 | 4.578e-8 | Rejected as default: changes mesh density and component counts |
| `limited_laplacian_smooth` | 0/8 | 2.513e-3 | 2.655e-1 | Rejected: moves coordinates and erodes surface-area proxy |

The selected recipe had zero bbox drift, zero surface-area proxy drift, zero
absolute-volume-proxy drift, no coordinate-component-count delta, and no face
count delta on all eight metric frames.

## Visual Check

Contact sheets:

- `contact_sheets/official_round_frame_0025_variant_contact_sheet.jpg`
- `contact_sheets/official_round_frame_0050_variant_contact_sheet.jpg`
- `contact_sheets/official_round_frame_0098_variant_contact_sheet.jpg`
- `contact_sheets/rectangular_frame_0098_variant_contact_sheet.jpg`

Visual review of the safe-hero sheets showed that normal-only options reduce
faceting/shimmer without changing silhouette. Simple subdivision and Laplacian
smoothing did not add enough visible value to justify default use. The
Laplacian smooth variant is visibly similar at small scale but is rejected
because it moves geometry and changes the area proxy by about 26%.

## Task 04 Instruction

Task 04 may use `SMOOTH_RENDER_SURFACE_RECIPE.json` and the
`merged_weighted_normals` operation for presentation renders only.

If Blender instability recurs in long multi-frame loops, render one still or one
short frame batch per Blender process. If the weighted-normal modifier itself is
unstable on a future frame, fall back to `raw_flat_facets` with improved
material, camera, and lighting.
