# Internal-Nozzle Bounded Run Recipe

This is the Task 05 activation recipe. Task 04 did not execute these longer
stages. Gravity remains off and the source exposes no gravity run option.

## Preconditions

- Branch: `review/basilisk-internal-nozzle-reactivation-20260711`.
- Source: `cases/basilisk/rectangular_internal_nozzle_convergence_visual.c`.
- Pressure: `351.48`; perturbation amplitude: `0`.
- Use an absolute output directory outside Git with at least 20 GiB free.
- Use `OMP_NUM_THREADS=1` for restart-sensitive evidence. Four-thread runs are
  exploratory until a separate determinism benchmark passes.
- Stop on nonzero solver exit, NaN, zero-range pressure, missing/empty dump,
  nonpositive facet count, naming mismatch, or restart deviation above 1%.

## Build

Compile from a flat task-owned build directory because this local `qcc` writes
generated preprocessed files beside the input.

```sh
TASK04=/home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-04-internal-nozzle-instrumentation
REPO=/home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/worktrees/task04-internal-nozzle
QCC=/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc
mkdir -p "$TASK04/task05-build"
cp "$REPO/cases/basilisk/rectangular_internal_nozzle_convergence_visual.c" "$TASK04/task05-build/"
BASILISK=/home/franco/opt/basilisk-survey-20260606/basilisk/src \
  "$QCC" -O2 -Wall -grid=octree \
  "$TASK04/task05-build/rectangular_internal_nozzle_convergence_visual.c" \
  -o "$TASK04/task05-build/internal_nozzle" \
  -L/home/franco/opt/basilisk-survey-20260606/basilisk/src/gl \
  -lglutils -lfb_tiny -lm
```

## Stage A: required bounded smoke

```sh
OUT=/home/franco/stack-validation/YYYYMMDD-task05-internal-nozzle/smoke
mkdir -p "$OUT"
OMP_NUM_THREADS=1 timeout 600s "$TASK04/task05-build/internal_nozzle" \
  --case-id task05_smoke --domain full --maxlevel 5 --pressure 351.48 \
  --end-time 0.01 --external-dh 3 --output-dir "$OUT" \
  --diagnostic-dt 0.005 --field-dt 0.005 --visual-dt 0.005 \
  --checkpoint-dt 0.005 --raw-export 1 --field-export 1 \
  --native-frames 1 --facet-export 1 --perturb-amp 0 --max-steps 1200
```

Validate with `scripts/validate_internal_nozzle_instrumentation.py` and
`scripts/postprocess_internal_nozzle_checkpoints.py`. Preserve the uninterrupted
and restored directories for the comparison.

## Stage B: bounded W2 evidence window

Run only after Stage A passes. Start at maxlevel 7 and stop at `t=0.03`; this is
not the prior long `t=0.18` case.

```sh
OUT=/home/franco/stack-validation/YYYYMMDD-task05-internal-nozzle/w2_l7_t003
mkdir -p "$OUT"
OMP_NUM_THREADS=1 timeout 3600s "$TASK04/task05-build/internal_nozzle" \
  --case-id W2_task05_l7_t003 --domain full --maxlevel 7 --pressure 351.48 \
  --end-time 0.03 --external-dh 3 --output-dir "$OUT" \
  --diagnostic-dt 0.005 --field-dt 0.005 --visual-dt 0.005 \
  --checkpoint-dt 0.005 --raw-export 1 --field-export 1 \
  --native-frames 1 --facet-export 1 --perturb-amp 0 --max-steps 8000
```

Do not continue to `t=0.18`, add gravity, raise resolution, or start a matrix
inside the same unattended stage. Review wall time, output size, pressure
ranges, restart envelope, and morphology boundary first.
