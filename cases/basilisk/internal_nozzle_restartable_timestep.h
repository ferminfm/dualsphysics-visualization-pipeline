/*
 * Restartable equivalent of Basilisk v2406 src/timestep.h.
 *
 * The upstream routine stores its timestep-ramp history in a function-local
 * static variable.  Generic dumps cannot serialize that value, so a resumed
 * process repeats the startup ramp and diverges from an uninterrupted run.
 * This case-owned copy preserves the upstream formula while exposing the one
 * scalar of history for checkpoint metadata.
 *
 * The preparation script verifies the upstream timestep.h SHA-256 before it
 * permits compilation.  Do not use this header with an unverified upstream
 * implementation.
 */

double internal_nozzle_timestep_previous = 0.;
int internal_nozzle_timestep_restore_probe = 0;

// note: u is weighted by fm
double timestep (const face vector u, double dtmax)
{
  if (t == 0.) internal_nozzle_timestep_previous = 0.;
  dtmax /= CFL;
  foreach_face(reduction(min:dtmax))
    if (u.x[] != 0.) {
      double dt = Delta/fabs(u.x[]);
      assert (fm.x[]);
      dt *= fm.x[];
      if (dt < dtmax) dtmax = dt;
    }
  dtmax *= CFL;
  if (dtmax > internal_nozzle_timestep_previous)
    dtmax = (internal_nozzle_timestep_previous + 0.1*dtmax)/1.1;
  if (internal_nozzle_timestep_restore_probe)
    internal_nozzle_timestep_restore_probe = 0;
  else
    internal_nozzle_timestep_previous = dtmax;
  return dtmax;
}
