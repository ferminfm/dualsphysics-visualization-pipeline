# Final Morning Handoff - Stationary Jet Geometry Data Route - 2026-06-09

## Result

Real progress was made on the data-generation handoff without claiming physical
validation:

- SprayGeo now has a stricter bridge metadata/test gate for Ideal Momentum Jet
  Explorer overlays.
- Ideal Momentum Jet Explorer documentation now states how to interpret the
  SprayGeo `fit_readiness` metadata without duplicating SprayGeo extraction or
  fitting logic.
- DualSPHysics was re-audited for safe 3D inlet/open-boundary jet cases and
  remains blocked because official example XML directories are absent locally.

## DualSPHysics Status

No safe official or near-official 3D inlet smoke case is currently available in
the local DualSPHysics trees. Only dam-break XMLs and XML-format templates were
found. No simulation was run.

Blocked input:

```text
examples/main/inletoutlet/05_SHAPESINLET3D/
examples/main/inletoutlet/06_BOX4INLET3D/
examples/main/inletoutlet/8_IMPINGINGJET/
```

Next DualSPHysics action: manually recover the official v5.4 full-package
examples outside Git, inspect `05_SHAPESINLET3D`, and only then run a bounded
smoke case.

## SprayGeo Handoff Status

SprayGeo remains the producer of stationary geometry metrics and Ideal Explorer
overlay CSVs. The bridge metadata now distinguishes:

- `bridge_smoke_only`
- `blocked_pending_stationary_window`
- `overlay_ready_for_exploratory_fit_only`
- `overlay_ready_with_validation_protocol`

This is a metadata gate only; it does not add a second fitting workflow.

## Ideal Momentum Jet Explorer Status

Ideal Explorer remains the reduced-order visualization and fitting surface. The
SprayGeo import documentation now tells operators to check `fit_readiness`
before quantitative comparison.

## Next Solver Route

If DualSPHysics examples are not recovered first, the next practical route is a
small Basilisk/VOF interface-geometry pass through SprayGeo. Label outputs as
VOF/interface geometry proxies, not validated atomization or production CFD.

## Do Not Claim

- Validated atomization
- Experimental agreement
- Production CFD
- Statistically stationary behavior without documented post-transient windows
- DualSPHysics liquid-gas/multiphase validation from the current wrapper
