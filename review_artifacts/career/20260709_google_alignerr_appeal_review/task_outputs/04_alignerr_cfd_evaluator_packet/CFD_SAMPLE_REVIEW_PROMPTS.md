# CFD Sample Review Prompts

These are self-authored practice prompts, not live assessment material.

## 1. VOF breakup claim review

Prompt: Review an AI answer claiming a VOF liquid jet has atomized because a rendered frame shows a wavy connected interface. Evaluate whether the evidence supports breakup.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 2. Pressure-field availability

Prompt: Review an AI answer that includes pressure heatmaps from a Basilisk dump where restored pressure has zero range. Decide whether pressure visualization is valid.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 3. Boundary-condition mismatch

Prompt: Review an answer that compares a pressure-driven internal-nozzle case to an imposed-inlet rectangular aperture case as if they were equivalent.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 4. Resolution convergence

Prompt: Review a claim that L7/L8 station-wise jet metrics converge when time frames and station definitions are not aligned.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 5. OpenFOAM KH proxy

Prompt: Review an answer that describes a scaled Kelvin-Helmholtz proxy as validated atomization.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 6. DualSPHysics 2D impinging jet

Prompt: Review a response that treats a 2D single-phase official example visualization as a 3D liquid-gas spray validation.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 7. Nondimensional comparison

Prompt: Review a response comparing two rectangular jets without accounting for area, hydraulic diameter, and flux differences.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 8. Reduced-model overlay

Prompt: Review a response claiming ideal/lossy jet model fit readiness from exploratory geometry metrics with quality flags still failing.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 9. Mesh and CFL sanity

Prompt: Review an answer that ignores timestep/CFL and mesh resolution in a transient CFD result.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

## 10. Visualization artifact diagnosis

Prompt: Review a response that mistakes one-cell debris or clipping at a domain boundary for detached liquid structures.

Expected evaluator behavior: identify the claim, check physical/numerical evidence, state pass/warn/fail, list missing checks, and provide safe corrected wording.

