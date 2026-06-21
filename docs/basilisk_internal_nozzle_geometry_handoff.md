# Basilisk Internal-Nozzle Geometry Handoff

The selected geometry handoff case is `W2_longer_duration` from:

`/home/franco/stack-validation/20260620-basilisk-internal-nozzle-robustness-window`

The upstream geometry task reported:

- extraction mode: `upstream_metric_repackaging`
- raw VOF fields available: `false`
- fit ready: `false`
- selected morphology: `reproducible_internal_nozzle_connected_jet`
- station metrics path: `/home/franco/stack-validation/20260620-basilisk-internal-nozzle-geometry-handoff/geometry_handoff/jet_station_metrics.csv`
- frame summary path: `/home/franco/stack-validation/20260620-basilisk-internal-nozzle-geometry-handoff/geometry_handoff/jet_frame_summary.csv`
- SprayGeo handoff path: `/home/franco/stack-validation/20260620-basilisk-internal-nozzle-geometry-handoff/spraygeo_handoff/basilisk_internal_nozzle_geometry_metrics.csv`
- Ideal Explorer overlay path: `/home/franco/stack-validation/20260620-basilisk-internal-nozzle-geometry-handoff/ideal_explorer_overlay/basilisk_internal_nozzle_Ahat_overlay.csv`

## Normalized Geometry

The handoff uses nondimensional Basilisk prototype units inherited from the
selected case:

- `W = 0.208885689553`
- `H = 0.104442844776`
- `Dh = 0.139257126368`
- `A0 = 0.021816615649911702`
- `r0_equivalent = 0.08333333333330008`

Coordinate conventions:

- `xi = x_from_exit / Dh`
- `zeta = x_from_exit / r0_equivalent`
- `tau = time * final_selected_case_mean_velocity / Dh`

Quality flags include `not_stationary`, `not_for_model_fit`,
`low_occupancy`, `connected_core`, `usable_for_shape_trend`, and
`usable_for_model_overlay`.

## Reusable Script

`scripts/extract_basilisk_internal_nozzle_geometry.py` captures the repackaging
logic for review. It expects existing upstream CSVs and writes a fresh
station/frame/schema package. It does not perform a solver run and does not
reconstruct geometry from raw VOF fields.

Example:

```bash
python3 scripts/extract_basilisk_internal_nozzle_geometry.py \
  --cross-sections /path/to/two_phase_cross_section_metrics.csv \
  --frames /path/to/two_phase_frame_diagnostics.csv \
  --output-dir /tmp/internal_nozzle_geometry_handoff
```

The generated output remains an internal overlay interface artifact unless a
separate raw-field export and convergence plan is completed.
