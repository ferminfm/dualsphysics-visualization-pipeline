# Final Layer 1 Handoff - Basilisk Jet Site Publication

Layer 1 should use this handoff to review the completed Basilisk jet site publication batch.

## Current Public State

- Published route: <https://personal-ai-scientific-computing-si.vercel.app/projects/basilisk-jet-benchmark>
- Production deployment URL: <https://personal-ai-scientific-computing-site-qdf4z6qrd.vercel.app>
- Vercel inspect URL: <https://vercel.com/ferminfm-9008s-projects/personal-ai-scientific-computing-site/EJEfRWeC44CkkxsVGSRA8CPX9zHQ>
- Site PR: <https://github.com/ferminfm/personal-ai-scientific-computing-site/pull/6>
- Site main SHA after merge: `ef5a4f28c166d176fd07e9e1ad8b065258191e61`
- Evidence branch: `review/basilisk-jet-portfolio-20260702`

## What Completed

- Final site copy gate passed.
- PR #6 merged to site `main` by squash.
- Production Vercel deploy completed.
- Production route and project index returned HTTP 200 without Vercel authentication blocking.
- Evidence repo publication status and closure notes were committed and pushed.

## Claim Boundary To Preserve

- `fit_ready=false`
- no validation claim
- no production-CFD claim
- no atomisation-prediction claim
- no pressure-nozzle modeling claim
- no internal-nozzle-flow claim for the rectangular route
- no fit-ready reduced-model claim

## Layer 1 Decisions

1. Decide whether the current public page can remain as-is.
2. Decide whether to request small public copy polish, such as replacing remaining process-oriented "page draft" wording.
3. Decide whether to create a separate runtime pressure-export task.
4. Decide whether to create a separate Q/lambda2 gradient-validation task.
5. Decide whether to create a separate media-polish task.

Recommended decision: close this publication phase as complete, then handle scientific/media upgrades as separate evidence-gated tasks.

## Local-Only Artifacts Not Synced To GitHub

The following local outputs remain outside GitHub by design:

- `/home/franco/stack-validation/20260709-basilisk-jet-site-publication-batch/`
- `/home/franco/stack-validation/20260702-basilisk-jet-portfolio-batch/`
- `/home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/`
- `/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/`
- `/home/franco/stack-validation/20260627-basilisk-long-benchmark-v31-visual-field-cleanup/`

These include local reports, full media, rendered outputs, and generated diagnostic artifacts. The GitHub packet intentionally contains only compact review/status artifacts.
