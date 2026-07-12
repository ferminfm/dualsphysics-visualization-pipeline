# Internal-Nozzle Instrumentation Decision

## Decision

The `W2_longer_duration` pressure-driven internal-nozzle lineage is ready for a
bounded Task 05 run, subject to the recipe and claim boundary in this repository.
Runtime pressure is available and nonzero. This is an internal instrumentation
decision only: `fit_ready=false` and `public_ready=false`.

## Source provenance

- Task 04 base commit: `34fe347e5571c91dcbd35e640f39578feb80f481`.
- Raw W2 export lineage: commit `12d9d18` and
  `cases/basilisk/rectangular_internal_nozzle_raw_export.c`.
- Restart/facet lineage: commit `41e51e3` and
  `cases/basilisk/rectangular_internal_nozzle_convergence_visual.c`.
- Selected pressure: `351.48`, inherited from `W2_longer_duration`.
- Geometry: pressure-driven plenum, smooth contraction, 10-Dh 2:1 rectangular
  straight section, embedded no-slip walls, and no imposed exit velocity.
- Gravity is absent from the case and remains off.

## Runtime pressure and field contract

`post_projection_fields (i++, last)` runs after `centered.h`'s `projection`,
`end_timestep`, and centered adapt hook. A `qcc -events` smoke trace verified
that order. Each selected frame exports phase fraction, velocity components and
magnitude, vorticity magnitude, cell-centered pressure, embedded-fluid
fraction, coordinates, resolution, and region labels.

Pressure provenance is
`runtime_cell_centered_p_after_centered_projection`. The gauge context is the
declared pressure boundary pair: `p=pressure_value` at the left boundary and
`p=0` at the right boundary, so values are outlet-gauge-relative.

The deterministic maxlevel-5 serial smoke produced three field frames at
`t=0`, `0.005`, and `0.01`. Their pressure ranges were approximately
`364.655`, `350.729`, and `351.657`; all were finite and nonzero. Field files
join station frames by `case_id`, `t`, and `i`, while each manifest retains its
own local frame index.

## Solver-behavior and restart checks

With `OMP_NUM_THREADS=1`, field export enabled and disabled runs had exact text
matches for every numeric column in `raw_frame_summary.csv`. The instrumentation
therefore did not change the checked solver diagnostics.

Fresh and checkpoint-restored runs produced nonzero dump files, monotone frame,
surface, field, and checkpoint indexes, and positive facet counts. The restored
continuation passed a declared one-percent envelope: maximum raw-diagnostic
absolute delta was about `0.0022741`, and maximum normalized field-summary delta
was about `0.0044441`. It was not bitwise-identical: the post-restore timestep
sequence ended at iteration 72 rather than 62. Do not claim exact replay.

## Boundaries

- Connected waviness is not atomisation or breakup.
- No long case, gravity case, validation claim, fit, or public-ready media was
  produced in Task 04.
- Use serial execution for restart-sensitive evidence. Re-benchmark OpenMP
  separately before using it for scientific comparisons.
- A continuation exceeding the one-percent restart envelope is a blocker, not
evidence to average away.
