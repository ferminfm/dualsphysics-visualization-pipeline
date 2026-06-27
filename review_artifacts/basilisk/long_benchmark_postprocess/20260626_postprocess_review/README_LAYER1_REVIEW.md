# Layer-1 Review Packet: Long Benchmark Postprocess/Public-Prep Batch

Generated at UTC: `2026-06-26T19:48:09+00:00`

This packet exists so Layer 1 can review the current postprocessed Basilisk long-benchmark evidence through GitHub without reading local stack-validation outputs directly. It is a private/internal review packet, not final showcase publication.

## Inspect First

1. `TASK_RESULT_INVENTORY.json`
2. `evidence/TASK02_FIELD_AVAILABILITY_AUDIT.md`
3. `evidence/TASK05_PRESSURE_VISUALIZATION_BLOCKED.md`
4. `evidence/SURFACE_RECIPE_DECISION_V31.md`
5. `evidence/FIELD_PANEL_CORRECTION_V31.md`
6. `videos_proxy/long_primary_route_blender_sequence_v31.mp4`
7. `videos_proxy/round_vs_rectangular_split_screen_v31.mp4`
8. `videos_proxy/task05_field_visualization_reel_v31_no_pressure.mp4`
9. `evidence/TASK06_RELEASE_BLOCKERS.md`

## Current Decision State

- Lead visual/scientific route: official circular control.
- Secondary comparison: `C1_rect_area_top_hat` / `rect_area_top_hat`, a 2:1 area-matched rectangular top-hat imposed-inlet comparison.
- The rectangular route is not a selected Poiseuille route and does not resolve internal-nozzle flow.
- Task 05 field media are diagnostic only. Pressure visualization is blocked because restored pressure exports are zero-range; lambda2/Q-like vortex media are blocked pending validated gradient-tensor export.
- `fit_ready=false`; `public_ready=false`.

## V3.1 Correction Pass

The V3.1 packet update uses `merged_smooth_normals` as the full-sequence default surface recipe. `merged_weighted_normals` remains optional for stills or short clips only after frame tests because earlier full-sequence rendering showed late-frame Blender instability. `limited_laplacian_smooth` and subdivision remain rejected as defaults because they alter topology/geometry diagnostics.

The pressure placeholder panels from the Task 05 field media were removed. The V3.1 field reels show only real available fields: phase indicator, velocity magnitude, diagnostic vorticity magnitude, and ambient-phase speed/context. Pressure visualization remains blocked because the restored pressure field has zero range.

## Claim Boundary

Do not claim validation, production CFD, stationary spray, experimental agreement, true atomisation, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, or public readiness.
