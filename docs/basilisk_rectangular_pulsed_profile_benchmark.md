# Basilisk Rectangular Pulsed-Profile Benchmark

`cases/basilisk/official_rectangular_pulsed_atomisation.c` is the canonical
bounded source for the official circular pulsed-jet control and the area-matched
2:1 rectangular inlet-boundary variants.

The rectangular route imposes a profile at the inlet plane. It is not an
internal-nozzle-flow simulation and should not be described as validation,
production CFD, stationary spray data, or public-ready atomisation media.

## Modes

- `round_official_top_hat`: circular top-hat control matching the local
  Basilisk `examples/atomisation.c` defaults when run with the default settings.
- `rect_area_top_hat`: 2:1 rectangular top-hat with area equal to the official
  circular aperture.
- `rect_area_separable_parabolic`: analytically normalized separable parabolic
  rectangle profile.
- `rect_area_poisseuille_series`: numerically normalized truncated rectangular
  duct Poiseuille-series profile. The source also accepts the corrected spelling
  alias `rect_area_poiseuille_series`.

## Compile Pattern

Use the local Basilisk tree and compile from a flat temporary work directory:

```sh
WORK=/tmp/qcc_rectangular_pulsed_profile
rm -rf "$WORK" && mkdir -p "$WORK"
cp cases/basilisk/official_rectangular_pulsed_atomisation.c "$WORK"/
cd "$WORK"
BASILISK=/home/franco/opt/basilisk-survey-20260606/basilisk/src \
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -grid=octree official_rectangular_pulsed_atomisation.c \
  -o official_rectangular_pulsed_atomisation \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

## Bounded Smoke Example

```sh
OMP_NUM_THREADS=4 timeout 900s /tmp/qcc_rectangular_pulsed_profile/official_rectangular_pulsed_atomisation \
  --case-id rect_poisseuille_smoke \
  --profile-mode rect_area_poisseuille_series \
  --maxlevel 7 \
  --end-time 0.12 \
  --output-dt 0.04 \
  --facet-dt 0.04 \
  --raw-dt 0.04 \
  --checkpoint-dt 0.06 \
  --uemax 0.1 \
  --output-dir /home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/01_canonical_source_profile_pipeline/runs/rect_poisseuille_smoke \
  --max-steps 8000
```

Expected output families:

- `native_frames/native_vof_*.ppm` from `draw_vof("f")`;
- `vof_surfaces/vof_facets_*.facets` from `output_facets(f)`;
- `raw_frame_summary.csv`, `raw_component_summary.csv`, and optional
  `raw_interface_cells.csv`;
- `visual_frame_manifest.json`, `surface_manifest.json`, and
  `checkpoint_manifest.json`;
- checkpoint dumps under `checkpoints/`.

Profile-only validation:

```sh
python3 scripts/validate_rectangular_inlet_profile.py \
  --output-dir /home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/01_canonical_source_profile_pipeline
```

The profile validator checks wall zeros, unit area mean, mass-flow consistency
with `A0*Umean`, peak/mean ratio, nonnegative pulsed inlet velocity, and the
2:1 area-matched geometry.

## Credibility Audit Helper

For the long round/rectangular benchmark batch, the conservative Task 05
topology and route-selection artifacts can be regenerated after the bounded L9
confirmation has completed:

```sh
python3 scripts/analyze_basilisk_atomisation_benchmark.py \
  --batch-root /home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch \
  --output-root /home/franco/stack-validation/20260625-basilisk-rectangular-poiseuille-atomisation-showcase-batch/05_breakup_credibility_resolution_audit
```

The helper writes compact CSV/JSON/Markdown review artifacts only. It does not
run the solver, render media, publish, or treat component counts as validated
droplet statistics.
