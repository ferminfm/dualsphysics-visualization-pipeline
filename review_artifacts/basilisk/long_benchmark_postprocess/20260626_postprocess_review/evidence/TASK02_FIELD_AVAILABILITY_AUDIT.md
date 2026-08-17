# Field Availability Audit

Status: `partial_success`

No CFD time advancement was performed. The audit used existing manifests, raw CSV summaries, and restore-only reads of saved Basilisk dump checkpoints.

## Saved Data Inventory

| Route | Profile | Checkpoints | Native frames | Facet surfaces | Raw summaries | Nonzero checkpoints |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| official_round_control | round_official_top_hat | 20 | 101 | 101 | 101 | True |
| rectangular_top_hat_comparison | rect_area_top_hat | 20 | 101 | 101 | 101 | True |

Existing raw interface CSVs provide `f`, `ux`, `uy`, and `uz` only for interface cells. They do not provide pressure, vorticity, or meaningful ambient-phase samples by themselves.

For restore-only exports, the physical source time and source iteration are taken from the checkpoint manifests. The sampler also records Basilisk's post-restore event `t/i` values separately in per-export metadata.

## Restored Field Availability

- `f`: available from checkpoints and exported as the phase indicator.
- `u`: available from checkpoints and exported as components plus derived speed.
- `vorticity_magnitude`: derived from restored velocity using finite differences; this is a diagnostic field, not a validated gradient-tensor study.
- `p`: the field symbol is present but restored values have zero range in every selected export, so pressure visualization is blocked.
- `lambda2` / Q-like indicators: not exported in this task because an adaptive-octree gradient-tensor convention needs separate validation.
- Second phase: ambient-phase rows are sampled in center slices and distinguished by `f <= 1e-3`; there is no separate gas tracer beyond the VOF complement.
