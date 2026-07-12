# Basilisk Internal-Nozzle Visual Output Pipeline

`cases/basilisk/rectangular_internal_nozzle_convergence_visual.c` is the
restartable native-output companion to the W2 raw-field export. It preserves the
pressure-driven W2 internal-nozzle geometry, phase properties, surface tension,
zero-perturbation baseline, and raw station/interface CSV schema. It does not
impose a visual-exit velocity and does not broaden the breakup model.

The source adds:

- Basilisk `dump()` checkpoints with `checkpoint_manifest.json`;
- checkpoint restore from `--restore PATH` or `--auto-restore 1`;
- explicit post-projection phase, velocity, vorticity-magnitude, and runtime
  pressure CSV frames with provenance and gauge context;
- native Basilisk VOF PPM frames using `view()`, `draw_vof()`, and `save()`;
- true solver-derived VOF facet files using `output_facets(f)`;
- full-domain and quarter-domain modes with explicit manifest labels;
- raw frame, station, interface, component, profile, and reduced-section CSVs.

Typical bounded compile pattern:

```sh
WORK=/tmp/qcc_visual_check
rm -rf "$WORK" && mkdir -p "$WORK"
cp cases/basilisk/rectangular_internal_nozzle_convergence_visual.c "$WORK"/
cd "$WORK"
BASILISK=/home/franco/opt/basilisk-survey-20260606/basilisk/src \
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -grid=octree rectangular_internal_nozzle_convergence_visual.c \
  -o /tmp/rectangular_internal_nozzle_convergence_visual \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

The temporary copy is intentional: this local `qcc` reliably compiles Basilisk
cases from a flat work directory and writes generated `*-cpp.c` files there.

Example bounded full-domain smoke:

```sh
OMP_NUM_THREADS=1 timeout 600s /tmp/rectangular_internal_nozzle_convergence_visual \
  --case-id smoke_full \
  --domain full \
  --maxlevel 5 \
  --pressure 351.48 \
  --end-time 0.015 \
  --external-dh 3.0 \
  --output-dir OUTPUT_DIR \
  --diagnostic-dt 0.005 \
  --field-dt 0.005 \
  --visual-dt 0.005 \
  --checkpoint-dt 0.005 \
  --raw-export 1 \
  --field-export 1 \
  --native-frames 1 \
  --facet-export 1 \
  --max-steps 1200
```

Helper scripts:

- `scripts/postprocess_internal_nozzle_checkpoints.py` validates frame,
  checkpoint, and surface manifests and compares matched restart/reference
  diagnostics.
- `scripts/validate_internal_nozzle_instrumentation.py` validates field ranges,
  pressure/event provenance, gravity-off state, field/station joins, facets,
  checkpoints, and bounded restart comparisons.
- `scripts/export_basilisk_vof_surface.py` parses `output_facets(f)` files and
  can write simple OBJ files without topology cleanup.
- `scripts/assemble_internal_nozzle_native_video.py` checks for missing native
  frames and assembles an internal MP4 with `ffmpeg` when available.

Claim boundary: this pipeline is an internal restartable scientific-output
layer only. It is not experimental agreement, production CFD, pressure-atomized
nozzle validation, true atomisation evidence, final predictive modeling, or
public-ready media. Keep `fit_ready=false` and `public_ready=false`.
