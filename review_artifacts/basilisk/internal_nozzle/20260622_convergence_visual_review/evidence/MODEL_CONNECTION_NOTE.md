# Model Connection Note

## Direct Observables

- `A` and `Ahat`: station-slab liquid area and normalized area.
- `width`, `thickness`, `aspect_ratio`: transverse occupancy extents.
- `centroid_y`, `centroid_z`: cross-plane centroid drift.
- `orientation_angle` and `warp_proxy`: second-moment orientation and skew proxy.
- `active_front_Dh`, `interface_proxy`, and `interface_growth`: frame-level transient diagnostics.

## Closures Or Model Quantities

- Ideal/lossy jet-model area overlays may use `xi` or `zeta` as streamwise coordinate and `Ahat` as the area variable.
- Any entrainment, dissipation, contraction-loss, or atomisation parameter remains a closure, not a directly fitted value from this batch.

## Readiness

- Matched-cadence convergence decision: `failed_conservative_matched_cadence_gate`.
- Overlay readiness: `true` for internal diagnostic comparison.
- `exploratory_fit_ready=false`, `fit_ready=false`, and `public_ready=false`.
- Final parameter inference is prohibited.

## Next Model Experiment

Do not run a parameter-fitting experiment from this package. The next model step is a source-level diagnostic alignment check: rerun or restore L7 with the same fixed/front-relative station schedule used by the accepted L8 export, then repeat this exact gate.
