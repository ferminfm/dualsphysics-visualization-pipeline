# Basilisk Internal-Nozzle Raw-Field Export

This note documents the dedicated raw-field export path for the pressure-driven
rectangular internal-nozzle line. It is an internal fit-readiness diagnostic, not
a public media route and not validation evidence.

## Selected Case

The export case targets the robustness-study selection `W2_longer_duration`.
It preserves the same pressure-driven plenum/contraction/2:1 rectangular nozzle
interpretation used by the captured internal-nozzle prototype:

- pressure is imposed upstream and referenced downstream;
- embedded internal nozzle walls are no-slip;
- the visual nozzle exit does not receive a prescribed uniform velocity;
- the downstream liquid-gas VOF field is classified conservatively.

The reusable source is:

`cases/basilisk/rectangular_internal_nozzle_raw_export.c`

The extractor is:

`scripts/extract_internal_nozzle_raw_geometry.py`

## Export Modes

The solver writes selective CSV exports under the chosen run directory.

- `raw_station_cells.csv`: all exported cells inside downstream station slabs.
- `raw_interface_cells.csv`: cells with `0 < f < 1` within the near-exit
  external domain.
- `raw_component_summary.csv`: tagged post-exit component summaries.
- `raw_profile_exit_cells.csv`: exit-plane profile sanity samples.
- `raw_frame_summary.csv`: frame-level mean velocity, active front, interface,
  and component diagnostics.
- `raw_case_summary.csv`: single-row case/run summary.
- `raw_export_manifest.json`: file manifest and claim boundary.

The station coordinate is nondimensionalized as:

`xi = (x - x_exit)/Dh`

The baseline fixed station list covers approximately:

`xi = 0.25, 0.5, 0.75, 1.0, 1.5`

Two active-front-relative stations are also exported when the front has advanced
far enough to make them meaningful.

## Geometry Extraction

The extractor reads the raw station-cell rows and computes:

- station liquid area proxy `A`;
- normalized area `Ahat = A/A0`;
- equivalent diameter;
- width and thickness;
- width/thickness aspect ratio;
- centroid in `y,z`;
- second moments and orientation angle;
- warp proxy;
- active-front and interface-growth context;
- component and detached-proxy counts from frame diagnostics;
- quality flags.

The area proxy divides each liquid cell volume contribution by the local station
slab width used during export. This is a fit-readiness and overlay diagnostic,
not a final stationary spray or experimental-comparison metric.

## Claim Boundary

Allowed internal wording:

- pressure-driven internal-nozzle prototype;
- raw-field extraction path;
- station-wise geometry metrics;
- connected-jet or breakup-proxy classification with conservative gates.

Prohibited wording:

- validation;
- production CFD;
- stationary spray;
- experimental agreement;
- true atomisation;
- pressure-atomized-nozzle validation;
- final predictive modeling.

Connected waviness is not atomisation. One-cell debris, pre-exit components,
mirrored quadrants, and projection artifacts are not detached-liquid evidence.

## Typical Commands

Compile:

```sh
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc -fopenmp -O2 \
  cases/basilisk/rectangular_internal_nozzle_raw_export.c \
  -o /tmp/rectangular_internal_nozzle_raw_export -lm
```

Run a short smoke export:

```sh
OMP_NUM_THREADS=4 timeout 600s /tmp/rectangular_internal_nozzle_raw_export \
  E0_raw_export_smoke 2 5 351.48 0.01 1.5 OUTPUT_DIR 0.01 0 0.03 1 0.15 0.75
```

Run the bounded W2 baseline export:

```sh
OMP_NUM_THREADS=4 timeout 5400s /tmp/rectangular_internal_nozzle_raw_export \
  E1_W2_raw_export 2 7 351.48 0.18 3.0 OUTPUT_DIR 0.03 0 0.03 1 0.15 0.75
```

Extract geometry:

```sh
scripts/extract_internal_nozzle_raw_geometry.py \
  --raw-dir OUTPUT_DIR \
  --output-root OUTPUT_ROOT \
  --source-case W2_longer_duration
```

Build the model-handoff package from existing raw-derived metrics:

```sh
scripts/build_internal_nozzle_geometry_model_handoff.py \
  --raw-root /home/franco/stack-validation/20260621-basilisk-internal-nozzle-raw-field-export-rerun \
  --output-root /home/franco/stack-validation/20260621-basilisk-internal-nozzle-geometry-model-handoff-from-raw
```

This second step does not run a solver. It writes SprayGeo and Ideal Momentum Jet
Explorer overlay files under the output root and keeps `fit_ready=false` until a
matched-cadence L7/L8 station convergence gate passes.
