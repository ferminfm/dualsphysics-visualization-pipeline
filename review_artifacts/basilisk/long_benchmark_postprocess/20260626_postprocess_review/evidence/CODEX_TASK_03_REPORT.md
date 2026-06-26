# Codex Task 03 Report

Task: `03_smooth_render_surface_pipeline`

Status: `success`

Final marker:

`TASK_03_SURFACE_PIPELINE_WRITTEN: /home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/03_smooth_render_surface_pipeline/CODEX_TASK_03_REPORT.md`

## Scope

Built and tested a render-only smoothing/normal workflow for existing Basilisk
VOF facet frames. No CFD solver was run, no checkpoint was advanced, no raw
surface folder was committed, no push was performed, and no public/fit readiness
claim was changed.

The scientific reference remains the raw `output_facets(f)` geometry.

## Inputs Read

- Parent repo instructions from `/home/franco/Documents/GitHub/AGENTS.md`
- Task 03 runbook snapshot:
  `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/runbook_snapshot/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/tasks/03_smooth_render_surface_pipeline/CODEX_TASK_INSTRUCTIONS.md`
- Common guardrails:
  `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/runbook_snapshot/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/COMMON_GUARDRAILS.md`
- Existing long official circular and rectangular top-hat surface manifests and
  selected facet files under:
  `/home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/`
- Task 02 summary and report for dependency status.
- Existing Blender renderer:
  `/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio/scripts/blender_rectangular_atomisation_showcase.py`

## Outputs Written

- `SURFACE_INPUT_INVENTORY.json`
- `SMOOTH_RENDER_SURFACE_RECIPE.json`
- `SURFACE_SMOOTHING_DECISION.md`
- `metrics/SURFACE_SMOOTHING_COMPARISON.csv`
- `metrics/SURFACE_SMOOTHING_COMPARISON.json`
- `contact_sheets/*.jpg`
- `renders/**/*.png`
- `renders/render_records_all.json`
- `scripts/task03_surface_metrics.py`
- `scripts/task03_render_surface_variants.py`
- `logs/*.log`
- `CODEX_TASK_03_REPORT.md`
- `CODEX_TASK_03_SUMMARY.json`

## Tested Variants

| Variant | Operation | Result |
| --- | --- | --- |
| `raw_flat_facets` | Direct raw facet import, flat normals | Kept as scientific/reference fallback |
| `merged_smooth_normals` | Exact coincident-vertex merge plus smooth normals | Safe, zero coordinate/area drift |
| `merged_weighted_normals` | Exact coincident-vertex merge plus smooth normals and weighted normals | Selected Task 04 render-only recipe |
| `simple_subdivision_weighted_normals` | Simple level-1 subdivision plus weighted normals | Rejected as default because mesh density and component counts change |
| `limited_laplacian_smooth` | Deduped mesh with two iterations of factor-0.08 Laplacian smoothing | Rejected because it moves coordinates and changes surface-area proxy |

## Main Decision

Use `merged_weighted_normals` for Task 04 presentation renders only.

The selected recipe showed:

- 8/8 safe metric frames;
- max bbox relative drift: `0`;
- max surface-area proxy drift: `0`;
- max absolute-volume proxy drift: `0`;
- max coordinate-component-count delta: `0`;
- max face-count delta: `0`.

The raw-facet fallback remains `raw_flat_facets`. If the weighted-normal modifier
is unstable on a future frame, Task 04 should keep raw facets and improve only
material, lighting, camera, and overlays.

## Rejected Options

`simple_subdivision_weighted_normals` preserved bbox but changed render mesh
density substantially, with max face-count delta `116718` and max
coordinate-component-count delta `16`. It is rejected as the default recipe.

`limited_laplacian_smooth` moved vertices, with max bbox relative drift
`0.002512774145077893`, max surface-area proxy drift `0.2655255813226679`, and
max absolute-volume proxy drift `0.2892427376920381`. It is rejected.

## Visual Review

Rendered 20 selected stills and 4 contact sheets:

- `contact_sheets/official_round_frame_0025_variant_contact_sheet.jpg`
- `contact_sheets/official_round_frame_0050_variant_contact_sheet.jpg`
- `contact_sheets/official_round_frame_0098_variant_contact_sheet.jpg`
- `contact_sheets/rectangular_frame_0098_variant_contact_sheet.jpg`

Visual inspection confirmed that normal-only variants reduce visible
triangulation without changing silhouette. The geometric smoothing variants did
not provide enough presentation benefit to justify default use.

## Commands Run

- `df -BG /home /home/franco/stack-validation`
- `git status --short --branch`
- `blender --version`
- `python3 scripts/task03_surface_metrics.py --output-root ...`
- `blender --background --python scripts/task03_render_surface_variants.py -- ...`
- filtered one-still Blender reruns for missing safe-hero variants
- `montage ... contact_sheets/*.jpg`
- `identify contact_sheets/*.jpg`
- `python3 -m json.tool ...`
- `git diff --check`

## Warnings

An initial combined Blender metrics script segfaulted before rendering. Metrics
were therefore computed in normal Python from facet coordinates.

A long single-process Blender render loop also segfaulted after partial output.
Filtered one-still or one-frame rendering succeeded and produced the required
contact-sheet assets. Task 04 should prefer bounded frame batches or one
Blender process per high-risk still if this instability recurs.

The generated stills, contact sheets, logs, scripts, and metrics are local under
`stack-validation`; they were not committed or pushed.

## Claim Boundary

`fit_ready=false` and `public_ready=false` remain unchanged. The rectangular
route remains a 2:1 rectangular top-hat imposed-inlet comparison, not
internal-nozzle flow and not validation evidence.

## Recommended Next Step

Task 04 should consume `SMOOTH_RENDER_SURFACE_RECIPE.json`, use
`merged_weighted_normals` for render-only presentation meshes, and keep raw
facets as the fallback/reference geometry.
