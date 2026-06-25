
# Basilisk Rectangular Pulsed-Profile Long Benchmark Status

Status: `layer1_internal_review_packet_prepared_pending_layer2_push`

This document summarizes the 2026-06-25 long benchmark batch for internal scientific review. It is not public release copy. Keep `fit_ready=false` and `public_ready=false`.

## Source State

- Branch: `review/basilisk-rectangular-poiseuille-atomisation-20260625`
- Source HEAD at status write: `3ec1f7868db46bcddc5ac8af529b567c8764c298`
- Remote target SHA at status write: `3ec1f7868db46bcddc5ac8af529b567c8764c298`
- Stacked base branch SHA at status write: `34fe347e5571c91dcbd35e640f39578feb80f481`
- Review packet: `review_artifacts/basilisk/rectangular_poisseuille_atomisation/20260625_long_showcase_review`

## Route Definitions

- Official circular control: `round_official_top_hat`, matching the local Basilisk `examples/atomisation.c` defaults with `Re=5800`, `sigma=3e-5`, density ratio `27.84`, `u0=1`, pulse amplitude `0.05`, and period `0.1`.
- Rectangular modified benchmark: `rect_area_top_hat`, a 2:1 area-matched rectangle with area `A0=0.02181661564992912`, width `W=0.20888568955258338`, height `H=0.10444284477629169`, and hydraulic diameter `0.1392571263683889`.
- The rectangular velocity is imposed at the inlet plane. It is not an internal-nozzle-flow simulation.

## Long-Run Results

| Route | Final time | Physical frames | Checkpoint chain | Onset | Max credible components | Classification |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| Official circular control | 2.0 | 101 | `True` | 0.48 | 172 | `official_round_benchmark_candidate_supported` |
| Rectangular imposed inlet | 2.0 | 101 | `True` | 0.56 | 120 | `rectangular_candidate_resolution_sensitive` |

Task 05 selected `official_round_control` as the primary media route. The rectangular route is retained as a caveated comparison because the bounded L9 confirmation did not pass quantitative resolution invariance.

## Asset Availability

- Scientific media ready: `True`
- Blender assets ready: `True`
- Primary Blender sequence: `long_primary_route_blender_sequence.mp4` in the review packet.
- Native circular and rectangular sequences: available as compact packet MP4s.
- Round-versus-rectangular comparison: available as exact-time scientific media and Blender comparison media.

## Human Decisions Required

1. Confirm whether the official circular route can be the portfolio lead.
2. Confirm whether the rectangular imposed-inlet comparison is scientifically useful enough to show.
3. Decide whether a dedicated rectangular resolution study is needed before stronger claims.
4. Review overlays, contrast, framing, and caveat readability before any public packaging.
5. Decide whether the stacked PR should remain draft, be split, or proceed after review.

## Claim Boundary

Do not claim validation, production CFD, stationary spray, experimental agreement, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, public readiness, or internal-nozzle atomisation for the rectangular route. Component counts are thresholded diagnostics, not validated droplet statistics.
