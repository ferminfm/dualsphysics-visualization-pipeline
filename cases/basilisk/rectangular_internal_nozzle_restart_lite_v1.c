#include "grid/octree.h"
#include "embed.h"

static int restart_dt_override_pending, restart_face_state_pending;
static double restart_dt_override_value, restart_dt_scheduler_tnext;
extern double dt;

event stability (i++, last)
{
  if (restart_dt_override_pending) {
    if (fabs (dt - restart_dt_override_value) >
        1e-12*max (fabs (dt), fabs (restart_dt_override_value))) {
      fputs ("restart-lite timestep reconstruction mismatch\n", stderr);
      exit (2);
    }
    tnext = restart_dt_scheduler_tnext;
    dt = dtnext (restart_dt_override_value);
    restart_dt_override_pending = 0;
  }
}

#include "navier-stokes/centered.h"
#define mu(f) (clamp(f,0.,1.)*(mu1 - mu2) + mu2)
#include "two-phase.h"
#include "internal_nozzle_restart_lite_v1.h"
#include "maxruntime.h"
#include <string.h>

face vector muv[];
scalar restart_uf_x[], restart_uf_y[], restart_uf_z[];

static int baselevel = 4, maxlevel = 5, stop_i = 4, checkpoint_i = 2;
static double width = 0.24, height = 0.12, pressure_value = 1.;
static int restored_at_i = -1, checkpoint_written, post_restore_step;
static const char * final_field_path;

event stability (i++, last)
{
  if (restart_dt_override_pending) {
    if (restart_face_state_pending) {
      boundary ({restart_uf_x, restart_uf_y, restart_uf_z});
      foreach_face(x)
        uf.x[] = restart_uf_x[];
      foreach_face(y)
        uf.y[] = restart_uf_y[];
      foreach_face(z)
        uf.z[] = restart_uf_z[];
      boundary ((scalar *){uf});
      restart_face_state_pending = 0;
    }
    restart_dt_scheduler_tnext = tnext;
    for (int replay = 0; replay < iter; replay++)
      timestep (uf, DT);
  }
}

static double nozzle_phi (double xp, double yp, double zp)
{
  (void) xp;
  return min (width/2. - fabs(yp), height/2. - fabs(zp));
}

static void build_geometry (void)
{
  vertex scalar phi[];
  foreach_vertex()
    phi[] = nozzle_phi (x, y, z);
  boundary ({phi});
  fractions (phi, cs, fs);
  fractions_cleanup (cs, fs);
}

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

static void write_field_snapshot (void)
{
  if (!final_field_path)
    return;
  FILE * fp = fopen (final_field_path, "w");
  if (!fp) {
    perror (final_field_path);
    exit (2);
  }
  foreach (serial)
    fprintf (fp, "%a %a %a %a %a %a %a %a %a\n",
             x, y, z, Delta, dv()*cs[], f[], u.x[], u.y[], u.z[]);
  if (fclose (fp)) {
    perror (final_field_path);
    exit (2);
  }
}

u.n[embed] = dirichlet (0.);
u.t[embed] = dirichlet (0.);
u.r[embed] = dirichlet (0.);
p[left] = dirichlet (pressure_value);
pf[left] = dirichlet (pressure_value);
p[right] = dirichlet (0.);
pf[right] = dirichlet (0.);

event properties (i++)
{
  foreach_face()
    muv.x[] = fs.x[]*mu ((f[] + f[-1])/2.);
  boundary ((scalar *){muv});
}

int main (int argc, char ** argv)
{
  maxruntime (&argc, argv);
  if (argc > 1)
    restart_lite_checkpoint = argv[1];
  if (argc > 2)
    checkpoint_i = atoi (argv[2]);
  if (argc > 3)
    stop_i = atoi (argv[3]);
  if (argc > 4 && strcmp (argv[4], "-"))
    final_field_path = argv[4];
  if (argc > 5)
    baselevel = atoi (argv[5]);
  if (argc > 6)
    maxlevel = atoi (argv[6]);
  if (baselevel < 4 || baselevel > 5 ||
      maxlevel < baselevel || maxlevel > 6) {
    fputs ("restart-lite bounded levels must satisfy 4 <= base <= 5 and base <= max <= 6\n",
           stderr);
    return 2;
  }
  size (1.);
  origin (-0.5, -0.5, -0.5);
  init_grid (1 << baselevel);
  rho1 = 1.; rho2 = 0.1;
  mu1 = 1e-2; mu2 = 1e-3;
  mu = muv;
  DT = 2e-4;
  TOLERANCE = 1e-6;
  run();
}

event init (t = 0)
{
  p.nodump = pf.nodump = false;
  if (!restart_lite_restore()) {
    refine (fabs(y) < width && fabs(z) < width && level < maxlevel);
    build_geometry();
    fraction (f, 0.05 - x);
    foreach()
      foreach_dimension()
        u.x[] = 0.;
    boundary ({f, u});
    diagnostics ("fresh_init");
  }
  else {
    restored_at_i = i;
    checkpoint_written = restart_lite_checkpoint_count;
    restart_dt_override_value = restart_lite_next_dt;
    restart_dt_override_pending = 1;
    restart_face_state_pending = 1;
    build_geometry();
    event ("properties");
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
  if (i == checkpoint_i) {
    foreach() {
      restart_uf_x[] = uf.x[];
      restart_uf_y[] = uf.y[];
      restart_uf_z[] = uf.z[];
    }
    boundary ({restart_uf_x, restart_uf_y, restart_uf_z});
    checkpoint_written++;
    restart_lite_checkpoint_count = checkpoint_written;
    restart_lite_dump_fields ({cs, p, u, g, pf, f, rhov,
                               restart_uf_x, restart_uf_y, restart_uf_z});
    diagnostics ("checkpoint_written");
  }
}

event stop (i = stop_i, last)
{
  write_field_snapshot();
  fprintf (stderr, "STOP i=%d restored=%d post_restore_step=%d\n",
           i, restart_lite_restored, post_restore_step);
  return 1;
}
