# Basilisk Jet Portfolio Batch Status

Status: Site page merged and production deployed through the July 9, 2026 publication batch.
Evidence branch: `review/basilisk-jet-portfolio-20260702`
Site branch: `review/basilisk-jet-portfolio-site-20260702`

## Review Packet

`review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/`

## Publication Status Packet

`review_artifacts/basilisk/jet_portfolio/20260709_site_publication_status/`

## Published Site

- Branch: `review/basilisk-jet-portfolio-site-20260702`
- PR: <https://github.com/ferminfm/personal-ai-scientific-computing-site/pull/6>
- Site main SHA after merge: `ef5a4f28c166d176fd07e9e1ad8b065258191e61`
- Route: `/projects/basilisk-jet-benchmark`
- Production alias: <https://personal-ai-scientific-computing-si.vercel.app>
- Published route: <https://personal-ai-scientific-computing-si.vercel.app/projects/basilisk-jet-benchmark>
- Deployment: production deployment completed; access check returned HTTP 200 without a Vercel authentication wall.

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

Layer 1 should inspect the published route and publication-status packet, then decide whether any follow-up copy polish or separate scientific upgrade task is needed.
