# Alignment Audit

## Summary

A no-solver audit found a real station-schedule mismatch between the existing L7 and L8 exports. L7 was exported with an older station schedule, while L8 used the required schedule. However, using the full existing L8 raw export through `t=0.18` recovers `12` valid common station/time pairs, so a new L7 solver run is not required for this decision.

## Physical Controls

- Pressure: `351.48` in both L7 and L8 summaries.
- Domain: full-domain internal nozzle.
- Exit velocity imposed: `false` in both raw manifests.
- Geometry: same W/H/Dh/A0/nozzle exit in both raw manifests.
- Diagnostic cadence: `0.03`.
- Visual cadence: `0.005`.
- Checkpoint cadence: `0.03`.
- Maxlevel differs as intended: L7 versus L8.

## Station Schedule Difference

- L7 fixed xi exported: `0.25, 0.50, 0.75, 1.00, 1.50`.
- L8 fixed xi exported: `0.10, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00`.
- L7 front-relative exported: `0.50, 0.90`.
- L8 front-relative exported: `0.25, 0.50, 0.75, 0.90`.

The missing L7 stations were not interpolated or manufactured.

## Re-Extraction Result

- Matched times: `[0.03, 0.06, 0.09, 0.12, 0.15, 0.18]`.
- Valid station/time pairs: `12`.
- Threshold pass fraction: `0.25`.
- Convergence passed: `False`.
- Failure cause classification: `schedule_misalignment_resolved_but_resolution_sensitive`.

The unchanged convergence gates still fail, especially mean-exit-velocity and active-front agreement. This indicates that the original failed gate was partly affected by station coverage, but the aligned existing-data comparison still shows resolution-sensitive behavior.

## Decision

- No L7 rerun performed.
- No L8 rerun performed.
- No human authorization required for L8.
- `fit_ready=false`.
- `public_ready=false`.
- Morphology remains `connected_waviness_not_atomization`.
