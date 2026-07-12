# Task 06 scientific synthesis review packet

This compact packet is the permitted one-blocked-track synthesis for the
quarter-domain and internal-nozzle branches. It does not merge either physics
branch and it contains no new CFD execution.

## Decision in one paragraph

The tested quarter-domain acceleration is a quantitative no-go: although the
matched baseline completed and the quarter case was modestly faster, its final
four-times-quarter exit-flow error (`0.447098`) exceeded the `0.30` gate and
the selected near-exit geometry comparison also failed. The uninterrupted
full-domain internal-nozzle L7 reference is useful internal evidence for
scalar diagnostics, raw geometry, native VOF, and runtime pressure provenance.
That track remains on hold because the restored run has phase-shifted field
cadence, so there is no exact-time restored-field comparison; morphology is
`connected_waviness_not_atomization`, with no credible detached proxy.

## Review order

1. `SCIENTIFIC_ROUTE_MATRIX.md`
2. `PORTFOLIO_ASSET_SELECTION.md`
3. `PUBLIC_USE_CAVEATS.md`
4. `PRIVATE_SCIENTIFIC_DECISION.md`
5. `DEFERRED_SCIENTIFIC_ROADMAP.md`
6. `ARTIFACT_MANIFEST.json`
7. `metadata/SOURCE_METRICS.json`

## Packet boundary

- Eight non-repetitive compact artifacts are selected. Four existing tracked
  assets are referenced in place; two task-local media files are copied as
  compact proxies; two vector summaries are new derivatives.
- Raw fields, checkpoints, solver logs, native frames, and the approximately
  1.1 GiB Task 05 output package remain local outside Git.
- The quarter proxy is explicitly a mirrored display reconstruction of one
  simulated quadrant, not full-domain physics.
- The internal-nozzle proxy is from the uninterrupted full-domain L7 reference,
  not the restored run.
- `fit_ready=false`; `public_ready=false`.
