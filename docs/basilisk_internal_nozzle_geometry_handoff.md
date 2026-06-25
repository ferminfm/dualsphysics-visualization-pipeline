# Basilisk Internal-Nozzle Geometry Handoff

The selected geometry handoff case is `W2_longer_duration`.

Two handoff levels exist:

1. The older reduced-metric package from:

`/home/franco/stack-validation/20260620-basilisk-internal-nozzle-robustness-window`

2. The raw-field package from:

`/home/franco/stack-validation/20260621-basilisk-internal-nozzle-raw-field-export-rerun`

The raw-field package is preferred for current SprayGeo/Ideal Explorer overlay
work because it computes station geometry from exported VOF station-slab cells
rather than only repackaging reduced cross-section diagnostics.

The older upstream geometry task reported:

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

## Raw-Derived Model Handoff

The raw-export path writes selective VOF station cells, interface cells,
component summaries, and exit-profile samples. The reusable scripts are:

- `scripts/extract_internal_nozzle_raw_geometry.py`
- `scripts/build_internal_nozzle_geometry_model_handoff.py`

The second script consumes the raw-derived station metrics and writes:

- `geometry_handoff/jet_station_metrics.csv`
- `geometry_handoff/jet_frame_summary.csv`
- `geometry_handoff/jet_component_summary.csv`
- `spraygeo_handoff/basilisk_internal_nozzle_geometry_metrics.csv`
- `ideal_explorer_overlay/basilisk_internal_nozzle_Ahat_overlay.csv`
- schemas, README files, and internal diagnostic SVGs.

The generated output is overlay-ready for internal model comparison but not
exploratory-fit-ready. The matched-cadence L7/L8 station-shape convergence gate
has not passed, and the morphology is still a connected internal-nozzle jet.

Example:

```bash
python3 scripts/build_internal_nozzle_geometry_model_handoff.py \
  --raw-root /home/franco/stack-validation/20260621-basilisk-internal-nozzle-raw-field-export-rerun \
  --output-root /home/franco/stack-validation/20260621-basilisk-internal-nozzle-geometry-model-handoff-from-raw
```

Do not treat the resulting overlay as validation, a stationary spray, a breakup
claim, or public-ready material.
