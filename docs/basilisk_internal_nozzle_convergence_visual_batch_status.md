# Basilisk Internal-Nozzle Convergence Visual Batch Status

This is a compact, GitHub-visible internal status index for the 2026-06-22
Basilisk internal-nozzle convergence and visual batch. It is not a public-ready
claim, not validation, and not fit-ready reduced-model evidence.

## Branch And Scope

- Review branch: `review/basilisk-internal-nozzle-and-periodic-span-20260621`
- PR: https://github.com/ferminfm/dualsphysics-visualization-pipeline/pull/1
- Scope: internal scientific review status only.
- Publication gate: `public_ready=false`.
- Fit gate: `fit_ready=false`.

## Task Statuses

| Task | Status | Classification | QA |
| --- | --- | --- | --- |
| 01_visual_output_checkpoint_pipeline | success | pipeline_ready_checkpoint_restore_verified | `true` |
| 02_execution_scaling_qualification | success | execution_mode_selected_blender_gpu_qualified | `true` |
| 03_full_domain_l7_reference | success | l7_reference_ready | `true` |
| 04_full_domain_l8_convergence | success | l8_preferred_convergence_package_ready | `true` |
| 05_quarter_domain_visual_recovery | success | quarter_scout_comparable | `true` |
| 06_convergence_geometry_model_refresh | success | negative_convergence_decision_overlay_refreshed | `true` |
| 07_gpu_blender_portfolio_assets | complete | internal-only connected-jet/VOF prototype evidence; not atomisation validation | `true` |

## Execution Mode

OpenMP 4 threads for Basilisk CPU solve; Blender OptiX GPU render qualified; no GPU CFD solver used.

No GPU CFD solver was used.

## Scientific Result

- L7 full-domain final time: `0.3`.
- L8 full-domain final time: `0.18`.
- Quarter-domain final time: `0.3`.
- Convergence gate matched times: `[0.03, 0.06, 0.09, 0.12]`.
- Convergence verdict: `failed_conservative_matched_cadence_gate`.
- Convergence passed: `false`.
- Morphology: `connected_waviness_not_atomization`.

The current result remains a connected-waviness prototype. It is not
atomisation, breakup, pressure-atomized-nozzle validation, production CFD,
experimental agreement, stationary spray data, or final predictive modeling.

## Model And Overlay Readiness

- Metrics ready: `true`.
- Overlay ready: `true`.
- Exploratory fit ready: `false`.
- Fit ready: `false`.
- Public ready: `false`.

Reason: Mean-exit-velocity, active-front, Ahat, thickness, aspect, and warp thresholds did not all pass; station coverage remains limited.

## Asset Availability

Native and Blender assets exist for internal review, but generated media are not
committed here and are not public-ready.

Descriptive asset labels:

- `internal_nozzle_l7_full_domain_native_vof.mp4`
- `internal_nozzle_l8_full_domain_native_vof.mp4`
- `internal_nozzle_l7_l8_side_by_side.mp4`
- `internal_nozzle_full_domain_blender_physics_sequence.mp4`
- `internal_nozzle_l7_l8_scientific_comparison.mp4`
- `internal_nozzle_quarter_symmetry_blender_diagnostic.mp4`

Quarter-domain media remains a mirrored scout/comparison diagnostic only.

## Repository-Relative Evidence

- `cases/basilisk/rectangular_internal_nozzle_convergence_visual.c`
- `cases/basilisk/rectangular_internal_nozzle_quarter_symmetry.c`
- `cases/basilisk/rectangular_internal_nozzle_raw_export.c`
- `scripts/analyze_internal_nozzle_convergence.py`
- `scripts/blender_internal_nozzle_surface_sequence.py`
- `scripts/assemble_internal_nozzle_native_video.py`
- `docs/basilisk_internal_nozzle_claim_boundary.md`
- `docs/basilisk_internal_nozzle_visual_output_pipeline.md`

## Human Decision Points

- Accept or reject the failed conservative convergence verdict.
- Accept or reject overlay-only model readiness and exploratory-fit deferral.
- Inspect native and Blender media before any portfolio use.
- Decide whether PR #1 should merge, remain draft, or be split.
- Authorize or defer future schedule-aligned L7 raw export or HPC/breakup work.


## Layer-1 Review Packet

A compact private/internal review packet is available at:

`review_artifacts/basilisk/internal_nozzle/20260622_convergence_visual_review/`

Start with `review_artifacts/basilisk/internal_nozzle/20260622_convergence_visual_review/README_LAYER1_REVIEW.md` and `review_artifacts/basilisk/internal_nozzle/20260622_convergence_visual_review/ARTIFACT_MANIFEST.json`.

The review-artifact workflow and promotion rules are documented in
`docs/layer1_layer2_review_artifact_workflow.md`.

This packet is for Layer-1 review only. It does not change `fit_ready=false` or `public_ready=false`.


## Schedule-Aligned Convergence Update - 2026-06-23

A no-solver alignment audit and re-extraction packet is available at:

`review_artifacts/basilisk/internal_nozzle/20260623_schedule_aligned_convergence_review/`

Start with `review_artifacts/basilisk/internal_nozzle/20260623_schedule_aligned_convergence_review/README_LAYER1_REVIEW.md` and `review_artifacts/basilisk/internal_nozzle/20260623_schedule_aligned_convergence_review/ARTIFACT_MANIFEST.json`.

Result:

- Existing data re-extraction recovered `12` valid station/time pairs using the existing full L8 raw export through `t=0.18`.
- Convergence still passed: `false`.
- Failure cause classification: `schedule_misalignment_resolved_but_resolution_sensitive`.
- No L7 solver rerun was performed.
- No L8 rerun was performed.
- `fit_ready=false`.
- `public_ready=false`.
- Morphology remains `connected_waviness_not_atomization`; no breakup claim is allowed.
