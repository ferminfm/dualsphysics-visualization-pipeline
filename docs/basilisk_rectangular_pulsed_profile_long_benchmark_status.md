
# Basilisk Rectangular Pulsed-Profile Long Benchmark Status

Status: `v31_layer1_decision_recorded_public_packaging_blocked`

This document summarizes the 2026-06-25 long benchmark batch for internal scientific review. It is not public release copy. Keep `fit_ready=false` and `public_ready=false`.

## Source State

- Branch: `review/basilisk-rectangular-poiseuille-atomisation-20260625` (historical review-branch name; the selected rectangular route is not Poiseuille)
- Source HEAD at status write: `3ec1f7868db46bcddc5ac8af529b567c8764c298`
- Remote target SHA at status write: `3ec1f7868db46bcddc5ac8af529b567c8764c298`
- Stacked base branch SHA at status write: `34fe347e5571c91dcbd35e640f39578feb80f481`
- Review packet: `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review`

## Route Definitions

- Official circular control: `round_official_top_hat`, matching the local Basilisk `examples/atomisation.c` defaults with `Re=5800`, `sigma=3e-5`, density ratio `27.84`, `u0=1`, pulse amplitude `0.05`, and period `0.1`.
- Rectangular comparison: case `C1_rect_area_top_hat`, profile `rect_area_top_hat`, a 2:1 area-matched rectangular top-hat imposed-inlet comparison with area `A0=0.02181661564992912`, width `W=0.20888568955258338`, height `H=0.10444284477629169`, and hydraulic diameter `0.1392571263683889`.
- The rectangular velocity is imposed at the inlet plane. It is not an internal-nozzle-flow simulation.
- Poiseuille-series profiles were implemented and tested in the canonical source and profile validator, but they were not selected by the bounded candidate gate.

## Long-Run Results

| Route | Final time | Physical frames | Checkpoint chain | Onset | Max credible components | Classification |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| Official circular control | 2.0 | 101 | `True` | 0.48 | 172 | `official_round_benchmark_candidate_supported` |
| Rectangular top-hat imposed inlet | 2.0 | 101 | `True` | 0.56 | 120 | `rectangular_candidate_resolution_sensitive` |

Task 05 selected `official_round_control` as the primary media route. The rectangular route is retained as a caveated comparison because the bounded L9 confirmation did not pass quantitative resolution invariance.

## Asset Availability

- Scientific media ready: `True`
- Blender assets ready: `True`
- Corrected primary Blender sequence: `videos_proxy/long_primary_route_blender_sequence_v2.mp4` in the review packet, generated from all 101 official circular physical frames.
- Corrected split-screen comparison: `videos_proxy/round_vs_rectangular_split_screen_v2.mp4`, with separate left/right compositor panels rather than a shared 3D room.
- Corrected safe-frame flythrough: `videos_proxy/final_complex_geometry_flythrough_v2.mp4`, using official-round frame 98 at `t=1.96`.
- Boundary clearance audit: `evidence/BOUNDARY_CLEARANCE_AUDIT.md`.
- Flythrough mask/raycast visibility QA: `evidence/FLYTHROUGH_VISIBILITY_QA.md`.
- Native circular and rectangular sequences: available as compact packet MP4s.
- Round-versus-rectangular comparison: available as exact-time scientific media; corrected review media uses synchronized split-screen composition, not a shared 3D room.

## Human Decisions Required

Layer-1 decision recorded in `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/evidence/LAYER1_DECISION.md`:

1. The official circular route is accepted as the internal visual/scientific lead candidate.
2. The rectangular route may be shown only as a secondary caveated comparison.
3. The selected rectangular route is `C1_rect_area_top_hat` / `rect_area_top_hat`, a 2:1 rectangular top-hat imposed-inlet comparison.
4. Poiseuille-series profiles were implemented/tested but were not selected.
5. Public packaging remains blocked until direct human visual review and a separate public-packaging task pass.

Remaining decisions:

1. Review v2 videos directly for public visual suitability.
2. Review public wording and final site asset selection.
3. Decide whether a dedicated rectangular resolution study is needed before stronger claims.
4. Decide whether the stacked PR should remain draft, be split, or proceed after review.

## Claim Boundary

Do not claim validation, production CFD, stationary spray, experimental agreement, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, public readiness, or internal-nozzle atomisation for the rectangular route. Component counts are thresholded diagnostics, not validated droplet statistics.

## 2026-06-26 Postprocess Public-Prep Packet

A follow-up postprocess/public-prep review packet was added at `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/`.

- Lead route remains the official circular control.
- Rectangular comparison remains secondary and caveated as `C1_rect_area_top_hat` / `rect_area_top_hat`, a 2:1 top-hat imposed-inlet comparison.
- Diagnostic field media are available for phase, speed, finite-difference vorticity magnitude, and ambient-VOF complement.
- Pressure visualization is blocked by zero-range restored pressure exports.
- Lambda2/Q-like visualization is blocked pending a validated gradient-tensor export.
- `fit_ready=false`; `public_ready=false`.

## 2026-06-27 V3.1 Visual and Field-Panel Cleanup

The postprocess review packet was updated in place with V3.1 internal-review proxies.

- Full-sequence surface recipe default: `merged_smooth_normals`.
- `merged_weighted_normals` is not the full-sequence default because Task 04 observed late-frame Blender instability; it remains optional for stills/short clips only after frame tests pass.
- `limited_laplacian_smooth` and subdivision remain rejected as defaults because they alter geometry/topology diagnostics.
- V3.1 primary sequence: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/videos_proxy/long_primary_route_blender_sequence_v31.mp4`.
- V3.1 split-screen comparison: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/videos_proxy/round_vs_rectangular_split_screen_v31.mp4`.
- V3.1 field reel without pressure panel: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/videos_proxy/task05_field_visualization_reel_v31_no_pressure.mp4`.
- Retained flythrough: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/videos_proxy/final_complex_geometry_flythrough_v3.mp4`.
- Pressure visualization remains blocked: restored `p` has zero range, so no pressure heatmap or blank pressure panel is included.
- `fit_ready=false`; `public_ready=false`.

## 2026-06-27 Layer-1 V3.1 Decision

Layer-1 V3.1 decision: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/evidence/LAYER1_V31_DECISION.md`.

- Official circular route accepted as internal visual lead.
- Rectangular top-hat route accepted only as a secondary caveated imposed-inlet comparison.
- V3.1 primary, split-screen, and no-pressure field reels accepted for internal review.
- `merged_smooth_normals` accepted as the full-sequence render default.
- Pressure visualization remains blocked and pressure panels remain removed.
- Q/lambda2 remains blocked pending validated gradient-tensor export.
- Gravity branch deferred.
- Public packaging remains blocked.
- `fit_ready=false`; `public_ready=false`.
