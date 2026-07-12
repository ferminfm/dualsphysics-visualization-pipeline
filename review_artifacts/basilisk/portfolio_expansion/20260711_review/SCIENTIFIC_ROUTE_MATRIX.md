# Scientific route matrix

| Route | Purpose and boundary conditions | Evidence state | Cost / fields / geometry | Symmetry and morphology boundary | Portfolio suitability | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| Official circular control | Existing circular two-phase VOF benchmark visualization; imposed inlet benchmark, not a resolved pressure nozzle | Existing accepted V3.1 internal-review packet; no new Task 06 CFD | Lead surface sequence plus phase, speed, and diagnostic vorticity media; restored pressure remains unavailable in this older route | Full-domain visual evidence, but not experimental validation or a production atomisation prediction | Strongest lead visual after human review, with benchmark and readiness caveats | **KEEP** as lead benchmark visualization |
| 2:1 rectangular top-hat | Existing rectangular top-hat imposed-inlet comparison; not Poiseuille and not internal-nozzle flow | Existing accepted V3.1 secondary comparison | Synchronized round/rectangular visual comparison and no-pressure scalar context | Full-domain imposed-inlet comparison; geometry difference is illustrative, not validation | Useful only as a secondary, explicitly caveated comparison | **KEEP** as secondary comparison; do not extend under a nozzle claim |
| Quarter reconstruction | Reflection-plane quarter computation mirrored into four quadrants for display | Task 03 `verification_failed`; stable matched baseline, reconstruction QA passed, quantitative fidelity failed | Full/quarter wall-time ratio `1.190381`; quarter/full peak RSS `0.837569`; quarter/full output bytes `0.254081`; final exit-flow error `0.447098` versus `0.30` limit; selected near-exit area error `0.452373`, warp error `1.0` | Reflection parity passed, but symmetry suppresses antisymmetric/quadrant-breaking modes. Mirrored facets are one sample copied four times and provide no detachment or breakup evidence | Retain only as a clearly labeled negative diagnostic | **CLOSE** tested quantitative acceleration; archive labeled render-only proxy |
| Pressure-driven internal nozzle | Full-domain W2 L7 bounded reference with runtime post-projection pressure, outlet-zero gauge, gravity disabled | Task 05 `partial` hold; uninterrupted reference valid, scalar restart envelope passed, restored field cadence not comparable at exact time | L7 reference: `t=0.03`, 716.32 s, 516,076 KiB peak RSS; seven valid fields; final pressure range `354.706879`; final exit flow `0.0381218781`; 278,784 station rows and 1,412 interface rows | One credible connected post-exit component, zero credible detached proxies; `connected_waviness_not_atomization`; no breakup | Useful internal scientific evidence and a distinct geometry/pressure route, but not fit/public-ready | **EXTEND** only after reviewed restored-field cadence repair; current state **HOLD** |

## Cross-route claim boundary

- Only the uninterrupted internal-nozzle L7 reference supports runtime pressure
  evidence in this synthesis. It does not establish restored-field agreement.
- Existing V3.1 circular/rectangular scalar media must remain labeled
  no-pressure because their older restored pressure field was unavailable.
- Mirroring is a rendering operation, not new simulated physics.
- Connected waviness is negative evidence for atomisation/breakup claims.
- No route is validated, production-ready, fit-ready, or public-ready.
