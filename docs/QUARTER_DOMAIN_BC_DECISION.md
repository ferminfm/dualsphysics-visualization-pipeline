# Quarter-domain boundary-condition decision

## Verdict

The quarter-domain route is admissible only as a reflection-symmetric scout and
cost benchmark. It is not a periodic radial model, an independent full-domain
sample, or a general breakup calculation. The matched full-domain control is
mandatory before any Task 03 performance conclusion.

The implemented source is
`cases/basilisk/rectangular_internal_nozzle_convergence_visual.c`. Its
`--domain quarter` and `--domain full` modes use the same pressure-driven W2
geometry, phase properties, surface tension, time controls, and numerical
settings. The domain flag is the only intended smoke-pair difference.

## Reflection conditions

Let `x` be streamwise, `y` widthwise, and `z` heightwise. For a field that is
reflection-symmetric about `y = 0`, the parity conditions are

```text
u_y = 0
partial_y u_x = partial_y u_z = 0
partial_y p = partial_y pf = partial_y f = 0
```

For reflection about `z = 0`, they are

```text
u_z = 0
partial_z u_x = partial_z u_y = 0
partial_z p = partial_z pf = partial_z f = 0
```

The Basilisk boundary mapping is therefore zero normal velocity and zero normal
gradient for both tangential velocity components, pressure/projection pressure,
and VOF fraction on `bottom` (`y = 0`) and `back` (`z = 0`). The embedded
nozzle wall remains no-slip. The inlet remains pressure-driven with liquid VOF;
no exit velocity is imposed.

The centered 2:1 rectangle, uniform pressure forcing, zero transverse initial
velocity, and zero-amplitude baseline perturbation are even under both
reflections. A later perturbation is compatible only if its prescribed parity
matches these conditions. An antisymmetric inlet disturbance, lateral forcing,
manufacturing asymmetry, or off-axis feature invalidates the quarter model by
design.

## Why radial periodicity is rejected

Periodicity identifies values on two separated faces by a translation. The
planes `y = 0` and `z = 0` are geometric reflection planes and require vector
parity: the normal velocity is odd while tangential components and scalar
fields are even. A periodic radial boundary would neither impose that parity
nor represent a repeated physical unit cell. The source therefore contains no
`periodic(bottom)` or `periodic(back)` call and records
`transverse_periodic_boundaries=false` in its manifest.

This does not contradict the repository's separate
`periodic_span_sheet_bridge.c`: that case intentionally models a translationally
periodic spanwise sheet. It is not provenance for radial periodicity in the
finite rectangular nozzle.

## Matched-control and evidence limits

For the smoke pair, the quarter and full modes use identical physical
parameters, base/max levels, pressure, output cadence, and end time. The
comparison uses:

- `4 * quarter exit flux` versus full exit flux;
- `4 * quarter liquid area/volume/interface measure` versus full values;
- normal-velocity leakage at both reflection planes;
- matched output times and stable termination;
- a reconstruction manifest that checks quadrant transforms and face winding.

Because the adaptive tree grid is cubic, the quarter and full modes do not put
every remote transverse boundary at the same signed distance from the center.
The bounded smoke is deliberately short and uses near-nozzle integral metrics;
Task 03 must retain this caveat and reject the route if remote-boundary effects
become measurable.

Symmetry intentionally suppresses antisymmetric and quadrant-breaking modes.
Consequently, a passing quarter/full smoke authorizes only a bounded Task 03
cost-and-integral comparison. It does not authorize morphology, instability,
detachment, atomization, or breakup claims. Those require full-domain evidence.

## Render-only reconstruction

`scripts/reconstruct_quarter_domain.py` reflects solver-derived quarter facets
using `(y,z)`, `(-y,z)`, `(y,-z)`, and `(-y,-z)`. It reverses facet winding for
odd reflection parity so orientation is consistent. Every output carries the
persistent label:

> RENDER ONLY - ONE SIMULATED QUADRANT MIRRORED; NOT FULL-DOMAIN PHYSICS

The four quadrants are copied visualization geometry, not four simulations and
not additional statistical or physical evidence.

## Task 03 gate

Task 03 is `go_bounded_benchmark` only when the compile, both smoke runs,
matched-parameter audit, flux/mass/area/interface comparisons, symmetry leakage,
reconstruction orientation, artifact-label, Python tests, and schema gates all
pass. Any incompatible perturbation, unstable smoke, unmatched control, or
scientifically material seam error changes the decision to
`no_go_repair_task02` or `needs_human`.

## Verified Task 02 outcome (2026-07-13)

The second bounded iteration compiled and completed both `t = 0.006`,
maxlevel-5 smoke cases. It passed every gate in
`qa/attempt-2/quarter_domain_qa.json` under the local Task 02 output root:

- reflection-plane parity residual: `0` (tolerance `1e-8`);
- four-times-quarter versus full exit-flux relative error: `0.215509`;
- four-times-quarter versus full exit-area relative error: `0.0127449`;
- four-times-quarter versus full liquid-volume relative error: `0.000183534`;
- four-times-quarter versus full interface-measure relative error:
  `1.00126e-12`;
- stable termination and three shared diagnostic times: pass;
- radial periodicity rejection and render-only artifact label: pass.

The first iteration is retained as diagnostic evidence: its only failed gate
came from sampling normal velocity inside the domain instead of evaluating
reflection parity at the plane. The second iteration replaced that invalid
diagnostic with ghost-cell parity residuals and reran both simulations.

**Task 03 decision: `go_bounded_benchmark`.** This authorizes only the Task 03
bounded benchmark defined by its own runbook. It does not authorize a long run,
public media, fit readiness, or any breakup/morphology claim. Task 03 must retain
the remote-boundary and symmetry-suppressed-mode caveats above.
