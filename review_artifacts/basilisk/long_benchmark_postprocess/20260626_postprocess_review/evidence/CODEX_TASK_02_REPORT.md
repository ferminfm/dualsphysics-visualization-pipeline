# Codex Task 02 Report

Task: `02_field_export_diagnostic_extraction`

Status: `partial_success`

Final marker:

`TASK_02_FIELD_EXTRACTION_WRITTEN: /home/franco/stack-validation/20260626-basilisk-long-benchmark-postprocess-publicprep-batch/02_field_export_diagnostic_extraction/CODEX_TASK_02_REPORT.md`

## Scope

Audited existing saved Basilisk long-benchmark data and exported compact diagnostic fields from saved checkpoints only. No CFD time advancement, rendering, repository commit, push, merge, deployment, download, or package install was performed.

## Inputs Read

- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/tasks/02_field_export_diagnostic_extraction/CODEX_TASK_INSTRUCTIONS.md`
- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/COMMON_GUARDRAILS.md`
- `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/TASK_RESULT_SCHEMA.json`
- `/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio/cases/basilisk/official_rectangular_pulsed_atomisation.c`
- Official round and rectangular top-hat checkpoint, frame, surface, and raw diagnostic manifests under the 20260625 long showcase batch.
- Existing review packet manifests and Task 01 framing outputs.

## Outputs Written

- `FIELD_AVAILABILITY_AUDIT.md`
- `FIELD_EXTRACTION_PLAN.json`
- `field_exports_manifest.json`
- `FIELD_VISUALIZATION_FEASIBILITY_DECISION.md`
- `CODEX_TASK_02_REPORT.md`
- `CODEX_TASK_02_SUMMARY.json`
- Restore-only sampler source/binary under `scripts/`
- Compact selected-frame CSV/JSON exports under `field_exports/`
- Per-export stdout/stderr logs under `logs/`

## Selected Exports

| Export | Source time | CSV rows | Interface rows | Liquid rows | Ambient rows | Pressure visualizable |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| official_round_control__early__t00p1 | 0.1 | 1924 | 924 | 312 | 688 | False |
| official_round_control__onset_nearest_checkpoint__t00p5 | 0.5 | 8820 | 5950 | 929 | 1941 | False |
| official_round_control__mid__t01p0 | 1 | 21078 | 13819 | 1667 | 5592 | False |
| official_round_control__safe_hero_proxy_checkpoint__t01p9 | 1.9 | 39632 | 27640 | 3038 | 8954 | False |
| official_round_control__final__t02p0 | 2 | 41336 | 29195 | 3300 | 8841 | False |
| rectangular_top_hat_comparison__early__t00p1 | 0.1 | 1944 | 904 | 224 | 816 | False |
| rectangular_top_hat_comparison__onset_nearest_checkpoint__t00p6 | 0.6 | 10246 | 6715 | 904 | 2627 | False |
| rectangular_top_hat_comparison__mid__t01p0 | 1 | 19642 | 12688 | 1596 | 5358 | False |
| rectangular_top_hat_comparison__safe_hero_proxy_checkpoint__t01p9 | 1.9 | 39277 | 25099 | 2823 | 11355 | False |
| rectangular_top_hat_comparison__final__t02p0 | 2 | 41051 | 26535 | 3011 | 11505 | False |

## Main Decision

Existing saved data can support internal diagnostic media for phase, velocity, speed, and vorticity magnitude. Pressure media are blocked because restored `p` has zero range in all selected checkpoint exports. Lambda2/Q-like criteria are intentionally not exported in this task because their adaptive-octree gradient convention was not validated here.

Per-export source times and iterations are manifest-derived; the sampler records Basilisk's post-restore event `t/i` separately so restored-field provenance is not inferred from the postprocess event clock.

## Claim Boundary

`fit_ready=false` and `public_ready=false` remain unchanged. The rectangular route remains a 2:1 area-matched rectangular top-hat imposed-inlet comparison, not internal-nozzle flow and not validation evidence.

## Recommended Next Step

Task 05 may consume phase, velocity, speed, and vorticity-magnitude CSVs for internal diagnostic panels; it must not create pressure, lambda2, or Q-like media unless a later validated export provides nonzero/valid fields.
