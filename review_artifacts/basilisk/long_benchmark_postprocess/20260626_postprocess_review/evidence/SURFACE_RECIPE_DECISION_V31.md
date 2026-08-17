# V3.1 Surface Recipe Decision

Decision: use `merged_smooth_normals` as the full-sequence default for V3.1 review media.

Rationale:

- `merged_smooth_normals` is topology-preserving on the Task 03 metric frames: exact-vertex merge for coincident vertices, smooth normals, no coordinate smoothing, no remeshing, no subdivision, no decimation.
- `merged_weighted_normals` remains visually useful, but Task 04 documented a late-frame Blender segfault at official-round frame 58, forcing raw-facet fallback for frames 58-100 and other assets. It is therefore not the V3.1 full-sequence default.
- `merged_weighted_normals` may be used only for stills or short clips after explicit frame tests pass.
- `limited_laplacian_smooth` is rejected because it moves coordinates and changed the area proxy in Task 03.
- Subdivision/remeshing is rejected as a default because it changes mesh density/component counts.

Scientific boundary: raw Basilisk `output_facets(f)` remains the diagnostic geometry. The V3.1 surface recipe is a render-only presentation recipe; it does not create new solver data or new physical frames.
