# Basilisk Jet Portfolio Batch Status

Status: Tasks 01-09 prepared; final push pending when this status file is committed.
Evidence branch: `review/basilisk-jet-portfolio-20260702`
Site branch: `review/basilisk-jet-portfolio-site-20260702`

## Review Packet

`review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/`

## Site Draft

- Branch: `review/basilisk-jet-portfolio-site-20260702`
- Route: `/projects/basilisk-jet-benchmark`
- Deployment: not performed.

## Route Decisions

- Lead: official circular two-phase VOF benchmark.
- Secondary: `C1_rect_area_top_hat`, a 2:1 rectangular top-hat imposed-inlet comparison.
- The selected rectangular route is not Poiseuille and not resolved internal-nozzle flow.

## Scalar Decisions

- Phase/speed/vorticity diagnostic media are available through existing V3.1 no-pressure assets.
- Pressure visualization remains blocked because existing restored pressure had zero range and no validated runtime pressure export exists in this batch.
- Q/lambda2 remain blocked pending validated gradient-tensor export.

## Claim Boundary

- `fit_ready=false`
- `public_ready=false`
- no validation, production CFD, atomisation prediction, pressure-nozzle modeling, experimental agreement, or fit-readiness claim.

## Next Step

Layer 1 should inspect the review packet and site draft, then decide whether to open/merge/deploy through a separate publication task or request more media work.
