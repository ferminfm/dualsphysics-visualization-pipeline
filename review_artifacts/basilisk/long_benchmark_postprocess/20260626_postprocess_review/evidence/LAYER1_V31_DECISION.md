# Layer-1 V3.1 Decision

Layer-1 decision date: 2026-06-27

Reviewed head: `e16c7e97c37c7012cd9a6dd32cdd98b6144a1bf6`

## Decision

- The official circular route is accepted as the internal visual lead.
- The rectangular top-hat route is accepted only as a secondary caveated imposed-inlet comparison.
- The V3.1 primary sequence, split-screen comparison, and field reels are accepted for internal review.
- `merged_smooth_normals` is accepted as the full-sequence render default.
- Pressure visualization remains blocked because the restored pressure field has zero range.
- Pressure panels have been removed from review media.
- Q/lambda2 visualization remains blocked pending validated gradient-tensor export.
- The gravity branch is deferred.
- Public packaging remains blocked.
- `fit_ready=false`.
- `public_ready=false`.

## Required Claim Boundary

The selected rectangular route is `C1_rect_area_top_hat` / `rect_area_top_hat`, a 2:1 rectangular top-hat imposed-inlet comparison. It is not a selected Poiseuille route and does not resolve internal-nozzle flow.

Do not claim validation, production CFD, stationary spray, experimental agreement, true atomisation, pressure-atomized-nozzle validation, final predictive modeling, fit readiness, or public readiness.

## Next Decision

Keep PR #2 as a draft review branch. A separate explicit public-packaging task is required before any site move, deployment, publication, or public-ready wording.
