# Matched-Cadence Convergence Decision

Decision: `failed_conservative_matched_cadence_gate`.

Exact common physical times used: `0.03, 0.06, 0.09, 0.12`.
The accepted L8 final time for this gate is `0.12`; later L8 frames are recorded as context only.

## Threshold Results

- `mean_exit_velocity_rel_diff_le_2pct`: `False`
- `active_front_abs_diff_le_0p10_Dh`: `False`
- `median_Ahat_rel_diff_le_10pct`: `False`
- `p90_Ahat_rel_diff_le_20pct`: `False`
- `median_width_rel_diff_le_10pct`: `True`
- `p90_width_rel_diff_le_20pct`: `True`
- `median_thickness_rel_diff_le_10pct`: `False`
- `p90_thickness_rel_diff_le_20pct`: `True`
- `median_aspect_rel_diff_le_12pct`: `False`
- `p90_aspect_rel_diff_le_20pct`: `True`
- `centroid_separation_le_0p05_Dh`: `True`
- `warp_abs_diff_le_0p10`: `False`
- `interface_proxy_rel_diff_le_20pct`: `True`
- `no_morphology_classification_change`: `True`
- `no_new_credible_detached_claim`: `True`

## Aggregate Metrics

- valid station/time pairs: `6`
- threshold pass fraction: `0.3333333333333333`
- max mean-exit-velocity relative difference: `0.3382031566547835`
- max active-front difference: `0.24609375000053857 Dh`

The mean exit velocity and active-front thresholds fail by a wide margin. Station coverage is also limited because Task 03 L7 was generated with the older station schedule while accepted Task 04 L8 used the runbook-required station schedule.
