# Layer-1 Review Prompt — Basilisk Jet Portfolio Batch

Review the GitHub branches and local reports for the Basilisk jet portfolio batch.

Evidence branch: `review/basilisk-jet-portfolio-20260702`
Site branch: `review/basilisk-jet-portfolio-site-20260702`
Review packet: `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/`
Execution root: `/home/franco/stack-validation/20260702-basilisk-jet-portfolio-batch`

Primary decision: decide whether the non-deployed Basilisk jet benchmark page draft is ready for a human visual/copy review PR or needs more internal media polish first.

Constraints to preserve:

- no validation claim;
- no production CFD claim;
- no atomisation prediction claim;
- no pressure-nozzle modeling claim;
- no fit-readiness claim;
- `public_ready=false` until a separate publication task approves it;
- rectangular route is `C1_rect_area_top_hat`, a 2:1 rectangular top-hat imposed-inlet comparison, not Poiseuille and not internal-nozzle flow;
- pressure panels are blocked until a valid nonzero runtime pressure export exists.

Inspect first:

1. `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/LAYER1_HANDOFF.md`
2. `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/ARTIFACT_MANIFEST.json`
3. `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/PUBLIC_USE_CAVEATS.md`
4. `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/videos_proxy/long_primary_route_blender_sequence_v31.mp4`
5. `review_artifacts/basilisk/jet_portfolio/20260702_round_rect_review/videos_proxy/round_vs_rectangular_split_screen_v31.mp4`
6. Site branch file `src/app/projects/basilisk-jet-benchmark/page.tsx`

Return a decision on: keep/swap lead assets, keep/remove rectangular comparison from page, authorize pressure-export branch, open site PR, or defer deployment.
