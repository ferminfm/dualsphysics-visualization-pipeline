# Basilisk Internal-Nozzle Reproduction Map

This map records how to reproduce the source/docs line without committing raw
outputs. Solver runs should write outside Git, for example under
`/home/franco/stack-validation/YYYYMMDD-basilisk-internal-nozzle-rerun`.

The upstream task used:

`/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc`

That path is recorded for provenance. In this repository, `qcc` may not be on
`PATH`; use an explicit Basilisk `qcc` path when rerunning.

## Calibration

Source:

`cases/basilisk/rectangular_internal_nozzle_calibration.c`

Representative upstream compile:

```bash
/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc \
  -O2 -Wall -fopenmp -grid=octree \
  cases/basilisk/rectangular_internal_nozzle_calibration.c \
  -o /tmp/rectangular_internal_nozzle_calibration -lm
```

Representative selected upstream arguments:

```bash
/tmp/rectangular_internal_nozzle_calibration \
  C10_L7_pin2525 10 7 2524.75 0.5 10.0 /tmp/C10_L7_pin2525
```

## Two-Phase Prototype

Source:

`cases/basilisk/rectangular_internal_nozzle_two_phase.c`

Representative upstream arguments:

```bash
/tmp/rectangular_internal_nozzle_two_phase \
  P2_L7_long 2 7 351.48 0.12 3.0 /tmp/P2_L7_long 0.03
```

Expected interpretation: stable connected-jet prototype only; no breakup proxy
candidate.

## Quarter-Symmetry Scout

Source:

`cases/basilisk/rectangular_internal_nozzle_quarter_symmetry.c`

Representative upstream arguments:

```bash
/tmp/rectangular_internal_nozzle_quarter_symmetry \
  Q4_quarter_two_phase 4 7 351.48 0.12 3.0 /tmp/Q4_quarter_two_phase 0.03
```

Quarter symmetry is a scout only. Any morphology-sensitive or breakup-proxy
claim requires full-domain confirmation.

## Profile Analysis

Source:

`scripts/analyze_rectangular_nozzle_profile.py`

Example:

```bash
python3 scripts/analyze_rectangular_nozzle_profile.py \
  /tmp/internal_nozzle_calibration /tmp/internal_nozzle_calibration/runs/C10_L7_pin2525
```

This compares calibration profile samples with a rectangular-duct
Poiseuille-series shape. It is not experimental validation.

## Geometry Repackaging

Source:

`scripts/extract_basilisk_internal_nozzle_geometry.py`

This script needs upstream CSV metrics, not raw VOF fields. Treat its output as
internal model-interface material and keep generated CSVs outside Git unless a
separate review explicitly requests a small fixture.
