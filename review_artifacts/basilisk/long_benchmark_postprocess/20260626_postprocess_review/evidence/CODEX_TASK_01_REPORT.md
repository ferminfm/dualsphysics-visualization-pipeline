# Codex Task 01 Report

Task: `01_physical_framing_claim_strategy`

Status: `success`

Final marker:

`TASK_01_PHYSICAL_FRAMING_WRITTEN: /home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/01_physical_framing_claim_strategy/CODEX_TASK_01_REPORT.md`

## Scope

Executed the documentation-only Task 01. No simulations, renders, compiles, field exports, downloads, pushes, merges, or slash-command orchestration were used.

## Inputs Read

- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/tasks/01_physical_framing_claim_strategy/CODEX_TASK_INSTRUCTIONS.md`
- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/COMMON_GUARDRAILS.md`
- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/BATCH_MANIFEST.json`
- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/tasks/01_physical_framing_claim_strategy/TASK_CONTRACT.json`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/README_LAYER1_REVIEW.md`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/ARTIFACT_MANIFEST.json`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/PUBLIC_PACKAGING_BLOCKERS.md`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/evidence/CLAIM_BOUNDARY.md`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/evidence/LONG_ROUTE_SUMMARY.md`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/evidence/LAYER1_DECISION.md`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/evidence/MASTER_RESULT_EXTRACT.json`
- `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/metrics/selected_metrics_and_decisions.json`
- `docs/basilisk_rectangular_pulsed_profile_benchmark.md`
- `docs/basilisk_rectangular_pulsed_profile_long_benchmark_status.md`
- `review_artifacts/README.md`
- `review_artifacts/TEMPLATE_LAYER1_REVIEW_PACKET.md`
- `cases/basilisk/official_rectangular_pulsed_atomisation.c`

## Outputs Written

- `PHYSICAL_FRAMING_NOTE.md`
- `TWO_PHASE_INTERPRETATION_NOTE.md`
- `INDUSTRIAL_RELEVANCE_NOTE.md`
- `FUTURE_GRAVITY_BRANCH_SPEC.md`
- `CLAIM_LANGUAGE_MATRIX.md`
- `CODEX_TASK_01_REPORT.md`
- `CODEX_TASK_01_SUMMARY.json`

All outputs are under:

`/home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/01_physical_framing_claim_strategy`

## Main Findings

The current long benchmark is a nondimensional two-phase VOF pulsed-jet benchmark with:

- `Re=5800`;
- surface-tension coefficient `sigma=3e-5`;
- density ratio `rho1/rho2=27.84`;
- `u0=1`;
- pulse amplitude `0.05`;
- pulse period `0.1`;
- no active gravity/body-force term;
- official circular route `round_official_top_hat`;
- secondary rectangular route `C1_rect_area_top_hat` / `rect_area_top_hat`.

The official circular control is the internal visual/scientific lead candidate. The rectangular top-hat route is a secondary imposed-inlet comparison and remains resolution-sensitive. Poiseuille-series profiles were implemented and tested but were not selected.

## Claim Boundary

The notes keep the persistent gates:

- `fit_ready=false`
- `public_ready=false`

They prohibit validation, production CFD, experimental agreement, stationary spray, pressure-atomized-nozzle validation, internal-nozzle flow for the rectangular route, droplet-statistics claims, fit readiness, public readiness, and ordinary room-condition water-in-air framing.

## Future Gravity Branch

The gravity branch is specified only as a future design. No branch was created and no gravity case was run. The spec requires explicit gravity vector reporting, nondimensional `g_star`, no-gravity parity, boundary-clearance audit, and no silent changes to geometry, profile, density, Re, sigma, or boundary conditions.

## Validation

Validation performed after writing:

- JSON summary parsed with `python3 -m json.tool`.
- Markdown/output files were checked with `git diff --check --no-index` fallback against `/dev/null` for whitespace where applicable.
- Repository status was inspected before and after writing.

No solver or render validation was run because Task 01 prohibits solver and render execution.

## Next Step

Proceed to Task 02 only if Layer 2 accepts this conservative framing. Task 02 must preserve the no-overclaim boundaries and must not treat the rectangular route as internal-nozzle flow or public-ready evidence.
