/**
# Bounded Basilisk atomisation-style VOF jet wrapper

This is a local bounded wrapper around the Basilisk `examples/atomisation.c`
structure. It keeps the same two-phase VOF liquid jet, surface tension, pulsed
inflow, Basilisk View rendering, and `tag()` component diagnostics, but adds an
explicit stop time and CSV/PNG outputs suitable for unattended local smoke runs.

It is an atomisation-route demonstration only: not validation, not production
CFD, not statistically stationary spray data, and not final atomisation
prediction.
*/

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"

double radius = 1./12.;
double initial_length = 0.025;
double Re = 5800.;
double SIGMA = 3e-5;
double u0 = 1., au = 0.05, T0 = 0.1;
double end_time = 0.18;
double output_interval = 0.02;
double uemax = 0.1;
double tag_threshold = 1e-3;
int maxlevel = 6;
int frame_target = 0;
int output_frame = 0;

scalar f0[];
u.n[left]  = dirichlet(f0[]*(u0 + au*sin(2.*pi*t/T0)));
u.t[left]  = dirichlet(0);
#if dimension > 2
u.r[left]  = dirichlet(0);
#endif
p[left]    = neumann(0);
f[left]    = f0[];

u.n[right] = neumann(0);
p[right]   = dirichlet(0);

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
  if (argc > 5)
    frame_target = atoi(argv[5]);

  if (maxlevel < 6)
    maxlevel = 6;
  if (maxlevel > 8)
    maxlevel = 8;
  if (end_time <= 0.)
    end_time = 0.18;
  if (output_interval <= 0.)
    output_interval = 0.02;
  if (frame_target > 1)
    output_interval = end_time/(frame_target - 1);

  init_grid(64);
  origin(0., -1.5, -1.5);
  size(3. [1]);

  rho1 = 1. [0], rho2 = rho1/27.84;
  mu1 = 2.*u0*radius/Re*rho1, mu2 = 2.*u0*radius/Re*rho2;
  f.sigma = SIGMA;
  CFL = 0.35;

  run();
}

event init (t = 0)
{
  if (!restore(file = "restart")) {
    refine(x < 1.2*initial_length && sq(y) + sq(z) < 2.*sq(radius) &&
           level < maxlevel);

    fraction(f0, sq(radius) - sq(y) - sq(z));
    f0.refine = f0.prolongation = fraction_refine;
    restriction({f0});

    foreach() {
      f[] = f0[]*(x < initial_length);
      u.x[] = u0*f[];
      u.y[] = 0.;
#if dimension > 2
      u.z[] = 0.;
#endif
    }
  }
}

event logfile (i++)
{
  if (i == 0)
    fprintf(stderr, "t dt mgp.i mgpf.i mgu.i cells perf.t perf.speed\n");
  fprintf(stderr, "%g %g %d %d %d %ld %g %g\n",
          t, dt, mgp.i, mgpf.i, mgu.i, grid->tn, perf.t, perf.speed);
}

event outputs (t = 0.; t += output_interval; t <= end_time + 1e-12)
{
  char csv_name[96];
  sprintf(csv_name, "interface_cells_%04d.csv", output_frame);
  FILE * cells = fopen(csv_name, "w");
  if (!cells) {
    fprintf(stderr, "ERROR cannot open %s\n", csv_name);
    return 1;
  }
  fprintf(cells, "frame,time,x,y,z,f,u_x,u_y,u_z,level,cell_size\n");
  foreach() {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    if (f[] > 1e-6)
      fprintf(cells,
              "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g\n",
              output_frame, t, x, y, z, f[], u.x[], u.y[], uz, level, Delta);
  }
  fclose(cells);

  scalar m[];
  foreach()
    m[] = f[] > tag_threshold;
  int n = tag(m);

  char comp_name[96];
  sprintf(comp_name, "components_%04d.csv", output_frame);
  FILE * comps = fopen(comp_name, "w");
  if (!comps) {
    fprintf(stderr, "ERROR cannot open %s\n", comp_name);
    return 1;
  }
  fprintf(comps, "frame,time,component_id,volume,centroid_x,centroid_y,centroid_z,cell_count\n");
  if (n > 0) {
    double volume[n];
    coord center[n];
    int cell_count[n];
    for (int j = 0; j < n; j++) {
      volume[j] = 0.;
      center[j].x = center[j].y = center[j].z = 0.;
      cell_count[j] = 0;
    }
    foreach(serial) {
      if (m[] > 0) {
        int j = m[] - 1;
        double w = dv()*f[];
        volume[j] += w;
        center[j].x += w*x;
        center[j].y += w*y;
#if dimension > 2
        center[j].z += w*z;
#endif
        cell_count[j]++;
      }
    }
    for (int j = 0; j < n; j++) {
      if (volume[j] > 0.)
        fprintf(comps, "%d,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%d\n",
                output_frame, t, j, volume[j],
                center[j].x/volume[j], center[j].y/volume[j],
                center[j].z/volume[j], cell_count[j]);
    }
  }
  fclose(comps);

  char png_name[96];
  sprintf(png_name, "native_vof_%04d.png", output_frame);
  view(camera = "iso", fov = 14.5, tx = -0.418, ty = 0.288,
       width = 1280, height = 720);
  clear();
  draw_vof("f");
  box();
  save(png_name);

  fprintf(stderr, "output_frame %d time %g cells %s components %s image %s n_components %d\n",
          output_frame, t, csv_name, comp_name, png_name, n);
  output_frame++;
}

event adapt (i++)
{
  adapt_wavelet({f,u}, {0.01,uemax,uemax,uemax}, maxlevel);
}

event stop (t = end_time)
{
  return 1;
}
