/**
# Tiny Basilisk 3D VOF jet export case

This is a bounded smoke/export case for adapter and visualization testing.
It is derived from the locally available Basilisk atomisation example structure,
but it is intentionally much coarser and shorter.

It is not a validated atomization simulation, not production CFD, and not an
experimental comparison. The purpose is to generate a small solver-derived 3D
VOF field that can be converted into point-cloud frames, preliminary geometry
metrics, and a headless Blender portfolio animation.
*/

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"

double radius = 0.08;
double jet_length = 0.08;
double Re = 500.;
double SIGMA = 2e-4;
double u0 = 0.8, au = 0.18, T0 = 0.08;
double end_time = 0.14;
double output_interval = 0.035;
double uemax = 0.05;
double export_threshold = 1e-4;
int maxlevel = 5;
int export_frame = 0;

scalar f0[];
u.n[left] = dirichlet(f0[]*(u0 + au*sin(2.*pi*t/T0)));
u.t[left] = dirichlet(0);
#if dimension > 2
u.r[left] = dirichlet(0);
#endif
p[left] = neumann(0);
f[left] = f0[];

u.n[right] = neumann(0);
p[right] = dirichlet(0);

int main (int argc, char * argv[])
{
  if (argc > 1)
    maxlevel = atoi(argv[1]);
  if (argc > 2)
    end_time = atof(argv[2]);
  if (argc > 3)
    output_interval = atof(argv[3]);
  if (argc > 4)
    uemax = atof(argv[4]);

  if (maxlevel < 4)
    maxlevel = 4;
  if (maxlevel > 6)
    maxlevel = 6;
  if (end_time <= 0.)
    end_time = 0.14;
  if (output_interval <= 0.)
    output_interval = 0.035;

  init_grid(1 << maxlevel);
  origin(0., -0.35, -0.35);
  size(0.85);

  rho1 = 1., rho2 = rho1/27.84;
  mu1 = 2.*u0*radius/Re*rho1;
  mu2 = 2.*u0*radius/Re*rho2;
  f.sigma = SIGMA;
  CFL = 0.35;

  run();
}

event init (t = 0)
{
  fraction(f0, sq(radius) - sq(y) - sq(z));
  f0.refine = f0.prolongation = fraction_refine;
  restriction({f0});

  foreach() {
    f[] = f0[]*(x < jet_length);
    u.x[] = u0*f[];
    u.y[] = 0.;
#if dimension > 2
    u.z[] = 0.;
#endif
  }
}

event logfile (i++)
{
  if (i == 0)
    fprintf(stderr, "t dt mgp.i mgpf.i mgu.i cells perf.t perf.speed\n");
  fprintf(stderr, "%g %g %d %d %d %ld %g %g\n",
          t, dt, mgp.i, mgpf.i, mgu.i, grid->tn, perf.t, perf.speed);
}

event export_csv (t = 0.; t += output_interval; t <= end_time + 1e-12)
{
  char name[96];
  sprintf(name, "basilisk3d_jet_frame_%04d.csv", export_frame);
  FILE * fp = fopen(name, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot open %s\n", name);
    return 1;
  }
  fprintf(fp, "frame,time,x,y,z,f,u_x,u_y,u_z,level,cell_size\n");
  foreach() {
    if (f[] > export_threshold) {
      double uz = 0.;
#if dimension > 2
      uz = u.z[];
#endif
      fprintf(fp,
              "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g\n",
              export_frame, t, x, y, z, f[], u.x[], u.y[], uz, level, Delta);
    }
  }
  fclose(fp);
  fprintf(stderr, "export_frame %d time %g file %s\n", export_frame, t, name);
  export_frame++;
}

event stop (t = end_time)
{
  return 1;
}
