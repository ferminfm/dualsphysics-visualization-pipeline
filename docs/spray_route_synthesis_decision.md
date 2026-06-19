# Spray / Atomisation Route Synthesis Decision

## Purpose

This note records the current route-level decision across the DualSPHysics,
OpenFOAM, and Basilisk spray/atomisation work. The full generated synthesis
package is kept outside Git at:

```text
/home/franco/stack-validation/20260618-spray-route-synthesis-decision
```

Generated artifacts include the evidence inventory, decision matrix, synthesis
report, public/private claim boundary, and ranked next-actions plan.

## Current Decision

- DualSPHysics is the public scientific-visualization and geometry-proxy route.
  It demonstrates GPU SPH post-processing, VTK/IsoSurface rendering, and
  scientific communication. It is not an atomisation route.
- OpenFOAM VOF is useful as a scaled Kelvin-Helmholtz/deformation proxy and
  public case-study route after manual review, but the local VOF attempts did
  not produce credible primary-breakup evidence.
- Basilisk is the most physics-aligned route for liquid-gas interface breakup,
  but the current 3D rectangular-slot branches remain negative under the
  conservative credible-component gate.
- The Basilisk 2D shear-sigma scout is positive reduced-model evidence only.
  It does not validate 3D rectangular-slot breakup.

## Stop / Continue Guidance

- Stop using DualSPHysics to imply atomisation, gas-phase physics, internal
  nozzle-flow resolution, physical validation, production CFD, or experimental
  agreement.
- Stop repeating equivalent local OpenFOAM primary-breakup escalation unless a
  materially different solver/mesh/resource plan or HPC path is available.
- Stop repeating equivalent Basilisk `We_g = 80` mild-perturbation 3D
  rectangular-slot transfer attempts.
- Continue Basilisk only with a materially different 3D formulation,
  targeted-interface refinement strategy, gas-shear control, or validation-data
  target.
- Prefer a validation-data or parameter-selection branch before spending more
  local 3D runtime.

## Public Boundary

Acceptable public language:

- scientific visualization workflow
- single-phase geometry proxy
- VOF reduced-model scout
- conservative breakup-proxy gate
- not validation
- not stationary spray data

Do not claim validated atomisation, stationary spray, production CFD, physical
droplet statistics, experimental agreement, or 2D evidence as 3D proof.
