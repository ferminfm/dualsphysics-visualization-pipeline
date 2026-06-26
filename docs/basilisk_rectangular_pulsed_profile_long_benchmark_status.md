
# Basilisk Rectangular Pulsed-Profile Long Benchmark Status

Status: `layer1_internal_review_packet_under_visual_correction`

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

1. Confirm whether the official circular route can be the portfolio lead.
2. Confirm whether the rectangular imposed-inlet comparison is scientifically useful enough to show.
3. Decide whether a dedicated rectangular resolution study is needed before stronger claims.
4. Review overlays, contrast, framing, and caveat readability before any public packaging.
5. Decide whether the stacked PR should remain draft, be split, or proceed after review.

## Claim Boundary

Do not claim validation, production CFD, stationary spray, experimental agreement, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, public readiness, or internal-nozzle atomisation for the rectangular route. Component counts are thresholded diagnostics, not validated droplet statistics.
