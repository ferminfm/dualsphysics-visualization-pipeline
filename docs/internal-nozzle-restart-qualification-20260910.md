# Restart qualification: bounded diagnostic result

The source executed for the final fresh/reference, both short restores and
instrumentation control is a1a03c724b842966d82e0110effb1d157c621baf. Later reader,
test and documentation publication does not relabel those runs or qualify a
new source commit automatically. No production certificate was issued.

The original terminal-event clock artifact is supported by the terminal versus
interior diagnostic and repaired through native-clock preservation and canonical
future-event lookahead. An additional terminal-summary callback-context defect
was repaired. Neither repair changes equations, BCs, physical resolution or
tolerances. Residual restart errors remain: 7 of 210 metrics fail at t_star=1,
5 of 210 at t_star=2. Original core tolerance 1e-7, profile/raw 1e-8, floor 1,
and exact-count requirements are unchanged.

Seven keyed field comparisons localize the first sampled physical difference
between before_advection_term and before_projection at the next common native
iteration. Inactive/coarse pressure/predictor state remains a hypothesis, not a
uniquely demonstrated cause. Unavailable values are explicitly counted; finite
subset equality is not full-field equivalence. Instrumentation mode 2 versus
0 passes all 210 metrics, and current sampled solver health is bounded.

The new accepted-step cumulative functional passes independent serial and
50-digit Decimal reconstruction plus exact checkpoint prefixes on the fresh
748-step trace and three 35-step restores. It remains separate from sparse and
historically failed output-driven coordinates. Relative/absolute tolerances
remain 5e-8 and 1e-12. Signed net flow and endpoint-clipped net flow are distinct
from a local positive-velocity flux. The native staggered field convention is
retained explicitly.

## Reproduction tools

Run commands from this scientific repository root, with explicit local evidence
paths supplied as arguments. No default machine-local root is embedded.

- audit_internal_nozzle_qualified_restart.py: exact source/runtime/checkpoint
  identities and all 210 comparisons; a failed comparison returns nonzero.
- audit_internal_nozzle_accepted_step_campaign.py: complete step traces and
  restart prefixes, with sparse reconstruction explicitly separate.
- audit_internal_nozzle_precursor_transfer_qualification.py: retained precursor
  and observed initial mapping/projection checks, not restart acceptance.
- audit_internal_nozzle_executed_solver_health.py: sampled native residuals and
  complete stderr scan, without invented unsampled observations.
- analyze_internal_nozzle_restart_trace.py and
  audit_internal_nozzle_field_event_identities.py: exact event/key joins and
  descriptive finite-field differences. The separate availability comparator
  never certifies a restart.
- reduce_internal_nozzle_keyed_hydraulics.py and
  check_internal_nozzle_same_snapshot_hydraulics.py: independent cross-section
  quadrature, tested against manufactured fields and actual retained snapshots.
- visualize_internal_nozzle_restart_diagnostic.py and
  visualize_internal_nozzle_qualification_audits.py: static evidence figures,
  not simulation, fitting or acceptance. For the actual 2:1, scale-3 plenum,
  the fixed transverse camera half-width is 2.25 hydraulic diameters.

Each script exposes its exact options through --help. Existing qualification
launcher and source/build sealing tools remain the only authorized solver path.
Missing, failed, stale or identity-mismatched qualification forbids production.
The test suite uses clearly synthetic fixtures, never scientific acceptance.

Ten full-resolution diagnostic starts were used; zero production starts. Only
two remain in the batch ceiling, fewer than a complete new-source fresh plus
two-location restart qualification. Clean A/B and stationarity remain not_run.
The precursor-effect question is unresolved. This is not convergence, physical
validation, a stationary model calibration dataset, or merge/release readiness.
