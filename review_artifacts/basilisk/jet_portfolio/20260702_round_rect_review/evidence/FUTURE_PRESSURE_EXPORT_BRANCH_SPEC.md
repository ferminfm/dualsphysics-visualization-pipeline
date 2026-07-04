# Future Pressure Export Branch Spec

Do not run this branch as part of the current packaging-prep task.

## Objective

Add a minimal, bounded pressure-export path for the long Basilisk benchmark so pressure diagnostics can be audited from real nonzero pressure data.

## Source patch requirements

1. Explicitly enable pressure dumping or runtime pressure export:
   - set `p.nodump = false` and `pf.nodump = false` only if compatible with the solver path; or
   - write selected pressure samples during runtime after projection.
2. Export pressure after the projection step at selected frames.
3. Include raw columns:
   - time, frame, x, y, z, f, u.x, u.y, u.z, p, level, Delta, region flag.
4. Record pressure min/max/range at runtime before dump and after restore.
5. Compare restored pressure range against runtime pressure range.
6. Only add pressure-gradient, Q, or lambda2 after a validated adaptive-grid gradient convention exists.

## Bounded test ladder

- P0: one short compile/export smoke with pressure range check.
- P1: one selected official circular frame window, not a broad sweep.
- P2: optional matched rectangular frame only if P1 proves nonzero pressure recovery.

## Stop criteria

Stop if pressure remains zero-range after runtime export, if restored pressure does not match runtime pressure, or if gradient metrics depend on an unvalidated stencil.
