#include "grid/octree.h"
#include "embed.h"
#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "../../cases/basilisk/internal_nozzle_restart_lite_v1.h"
#include <string.h>

scalar marker[];

static int stop_i = 3;
static int checkpoint_i = 2;
static int restored_at_i = -1;
static int checkpoint_written;
static int post_restore_step;

static void diagnostics (const char * phase)
{
  long cells = 0, interface_cells = 0;
  double volume = 0., mx = 0., my = 0., mz = 0., kinetic = 0.;
  double fmin = HUGE, fmax = -HUGE, umin = HUGE, umax = -HUGE;
  foreach (reduction(+:cells) reduction(+:interface_cells)
           reduction(+:volume) reduction(+:mx) reduction(+:my) reduction(+:mz)
           reduction(+:kinetic) reduction(min:fmin) reduction(max:fmax)
           reduction(min:umin) reduction(max:umax)) {
    double dvf = dv()*cs[];
    cells++;
    volume += f[]*dvf;
    mx += u.x[]*dvf;
    my += u.y[]*dvf;
    mz += u.z[]*dvf;
    kinetic += 0.5*(sq(u.x[]) + sq(u.y[]) + sq(u.z[]))*dvf;
    if (f[] > 1e-12 && f[] < 1. - 1e-12)
      interface_cells++;
    fmin = min(fmin, f[]); fmax = max(fmax, f[]);
    umin = min(umin, min(u.x[], min(u.y[], u.z[])));
    umax = max(umax, max(u.x[], max(u.y[], u.z[])));
  }
  fprintf (stderr,
           "OBS phase=%s t=%.17g i=%d cells=%ld volume=%.17g "
           "mx=%.17g my=%.17g mz=%.17g ke=%.17g interfaces=%ld "
           "fmin=%.17g fmax=%.17g umin=%.17g umax=%.17g "
           "checkpoint_counter=%d output_counter=%d restored=%d\n",
           phase, t, iter, cells, volume, mx, my, mz,
           kinetic, interface_cells, fmin, fmax, umin, umax,
           checkpoint_written, iter, restart_lite_restored);
  fflush (stderr);
}

int main (int argc, char ** argv)
{
  if (argc > 1)
    restart_lite_checkpoint = argv[1];
  if (argc > 2)
    checkpoint_i = atoi (argv[2]);
  if (argc > 3)
    stop_i = atoi (argv[3]);
  size (1.);
  origin (-0.5, -0.5, -0.5);
  init_grid (1 << 4);
  DT = 2e-3;
  TOLERANCE = 1e-7;
  run();
}

event init (t = 0)
{
  if (!restart_lite_restore()) {
    refine (sq(x) + sq(y) + sq(z) < sq(0.24) && level < 5);
    fraction (f, 0.12 - x);
    foreach() {
      u.x[] = 0.05*(1. - sq(2.*y))*(1. - sq(2.*z));
      u.y[] = u.z[] = 0.;
      marker[] = x + 2.*y + 3.*z;
    }
    boundary ({f, marker, u});
    diagnostics ("fresh_init");
  }
  else {
    restored_at_i = i;
    checkpoint_written = iter >= checkpoint_i;
    diagnostics ("restored_immediate");
  }
}

event observation (i++, last)
{
  diagnostics ("end_step");
  if (restart_lite_restored && i > restored_at_i)
    post_restore_step = 1;
}

event checkpoint (i++, last)
{
  if (!restart_lite_restored && i == checkpoint_i) {
    restart_lite_dump();
    checkpoint_written++;
    diagnostics ("checkpoint_written");
  }
}

event stop (i = stop_i, last)
{
  fprintf (stderr, "STOP i=%d restored=%d post_restore_step=%d\n",
           i, restart_lite_restored, post_restore_step);
  return 1;
}
