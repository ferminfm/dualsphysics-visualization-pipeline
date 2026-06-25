# Scientific Asset Gate

Status: PASS for internal scientific review only.

Hard gates remain closed:

- `convergence_passed=false`
- `exploratory_fit_ready=false`
- `fit_ready=false`
- `public_ready=false`
- `breakup_claim_allowed=false`

Assets are connected-jet/VOF prototype evidence. They are not atomisation validation, not breakup evidence, and not a calibrated fit surface.

Fidelity checks:

- Full-domain L7 sequence uses all 61 physical Task 03 frames.
- L7/L8 comparison uses 25 matched physical-time frames through t=0.12.
- Flythrough is camera motion over the final Task 03 L7 physical frame; the surface itself is not animated or interpolated.
- Quarter diagnostic uses Task 05 mirrored quarter-domain surfaces and carries the persistent diagnostic label.
- Presentation interpolation was not used in any render manifest.
