
# Basilisk Rectangular Poiseuille Layer-1 Review Packet

This packet is a compact GitHub-visible review packet for the 2026-06-25 Basilisk rectangular Poiseuille atomisation showcase batch. It is private/internal working evidence for Layer 1, not final public media.

## Inspect First

1. `ARTIFACT_MANIFEST.json` for source paths, hashes, media metadata, and claim boundaries.
2. `videos_proxy/official_round_full_length_native.mp4` for the native VOF primary scientific reference.
3. `videos_proxy/long_primary_route_blender_sequence.mp4` for the primary Blender/Cycles portfolio candidate.
4. `videos_proxy/round_vs_rectangular_time_aligned.mp4` for exact-time circular versus rectangular scientific comparison.
5. `videos_proxy/final_complex_geometry_flythrough.mp4` and `contact_sheets/final_complex_geometry_flythrough_multiview.png` for final-frame visual review.
6. `metrics/selected_metrics_and_decisions.json`, `evidence/SCIENTIFIC_DECISION_MATRIX.md`, and `evidence/CLAIM_BOUNDARY.md` before making publication decisions.

## Current Scientific Result

- Official circular route: primary full-length internal atomisation-style benchmark candidate, `t=2.0`, 101 physical frames, checkpoint chain valid.
- Rectangular route: completed 2:1 area-matched imposed inlet-boundary benchmark, `t=2.0`, 101 physical frames, mass-flow validation passed.
- Resolution audit: rectangular route remains `rectangular_candidate_resolution_sensitive`; L9 confirms detached topology qualitatively but not onset/component-count invariance.
- Blender assets: internal visual review assets are available, but portfolio use still requires human review.
- `fit_ready=false` and `public_ready=false`.

## Public/Private Boundary

Do not present this packet as validation, production CFD, stationary spray evidence, experimental agreement, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, or public readiness.

The rectangular route imposes a velocity profile at the inlet plane. It is not internal-nozzle flow and does not resolve plenum, contraction, wall boundary layers, or natural nozzle-exit development.

## Recommended Layer-1 Decisions

1. Decide whether the official circular control can remain the primary portfolio lead after visual review.
2. Decide whether the rectangular imposed-inlet comparison should be shown at all, and if so, what caveat text is mandatory.
3. Decide whether the resolution-sensitive rectangular result needs a dedicated later resolution study before any stronger claim.
4. Decide whether the stacked PR should stay draft, be split, or be prepared for merge after review.
5. Keep publication blocked until a separate public packaging task passes.
