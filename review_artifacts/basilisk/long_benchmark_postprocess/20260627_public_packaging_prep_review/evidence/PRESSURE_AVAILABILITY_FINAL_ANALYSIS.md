# Pressure Availability Final Analysis

## Finding

Pressure is not available as a reliable restored field in the current long-benchmark outputs. The current pressure field evidence says restored `p` has zero range, so pressure visualization remains blocked.

## Local Basilisk evidence

Local Basilisk source:

- `/home/franco/opt/basilisk-survey-20260606/basilisk/src/navier-stokes/centered.h:141`

The centered Navier-Stokes implementation sets:

```c
p.nodump = pf.nodump = true;
```

This supports the likely explanation: Basilisk pressure fields are not dumped by default for this solver path.

## Canonical benchmark source evidence

Canonical source:

- `cases/basilisk/official_rectangular_pulsed_atomisation.c:10` includes `navier-stokes/centered.h`.
- `cases/basilisk/official_rectangular_pulsed_atomisation.c:653-660` writes checkpoints using `dump(file = path);`.
- Local search found no `p.nodump = false` or `pf.nodump = false` override in the canonical source.
- `cases/basilisk/official_rectangular_pulsed_atomisation.c:703-724` writes `raw_interface_cells.csv` with `f`, `u.x`, `u.y`, `u.z`, `level`, and `Delta`, but no pressure column.

## Interpretation

Existing checkpoints probably cannot recover pressure because `p` and `pf` were marked `nodump` when the checkpoints were written. The zero-range restored pressure exports are therefore not suitable for pressure heatmaps, pressure-gradient diagnostics, Q, or lambda2 visualization.

## Decision

- `pressure_available=false`
- Pressure panels remain removed.
- Pressure visualization should not be recreated from current restored checkpoints.
- Future pressure work requires a dedicated export branch.
