/**
# Rectangular-slot gas-Weber VOF breakup-proxy case

This is a bounded Basilisk VOF experiment for a rectangular liquid slot issuing
through a short duct into a gas region. It uses the official atomisation wrapper
as a template, but the geometry, nondimensional design table, perturbation, and
diagnostics are specific to a rectangular-slot breakup-proxy study.

This is not validation, not production CFD, not stationary spray data, and not
final atomisation prediction. Connected waviness must not be called
atomization; detached or ligament-like structures are only breakup-proxy
candidates.
*/

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"

/* Geometry. W/H = 1.5, Dh = 2WH/(W + H) = 0.96. */
double slot_w = 1.2;
double slot_h = 0.8;
double dh = 0.96;
double duct_length = 9.6;     /* 10 Dh. */
double external_length = 19.2; /* 20 Dh. */
double domain_length = 28.8;  /* 30 Dh, cubic Basilisk domain. */

/* Dimensionless physical/proxy choices. */
double rho_l = 1.0;
double rho_g = 0.05;
double u_l = 1.0;
double u_g = 0.0;
double rel_u = 1.0;
double target_we_g = 50.0;
double sigma0 = 0.00096;
double re_l = 1200.0;
double mu_l = 0.0008;
double mu_g = 0.000032;

/* Perturbation: proxy trigger applied to inlet transverse velocity. */
double perturb_amp = 0.08;
double perturb_period = 0.18;
double perturb_waves_y = 2.0;
double perturb_waves_z = 1.0;

double end_time = 0.18;
double output_interval = 0.02;
double uemax = 0.08;
double tag_threshold = 1e-3;
int maxlevel = 8;
int frame_target = 0;
int output_frame = 0;

scalar slotf[];
bid ductwall;

u.n[left] = dirichlet(u_g + slotf[]*(u_l - u_g));
u.t[left] = dirichlet(slotf[]*perturb_amp*u_l*
                      sin(2.*pi*t/perturb_period)*
                      sin(2.*pi*perturb_waves_z*z/slot_h));
#if dimension > 2
u.r[left] = dirichlet(slotf[]*perturb_amp*u_l*
                      cos(2.*pi*t/perturb_period)*
                      sin(2.*pi*perturb_waves_y*y/slot_w));
#endif
p[left] = neumann(0);
f[left] = slotf[];

u.n[right] = neumann(0);
p[right] = dirichlet(0);
f[right] = neumann(0);

u.n[top] = neumann(0);
p[top] = dirichlet(0);
f[top] = neumann(0);
u.n[bottom] = neumann(0);
p[bottom] = dirichlet(0);
f[bottom] = neumann(0);

#if dimension > 2
u.n[front] = neumann(0);
p[front] = dirichlet(0);
f[front] = neumann(0);
u.n[back] = neumann(0);
p[back] = dirichlet(0);
f[back] = neumann(0);
#endif

u.n[ductwall] = dirichlet(0);
u.t[ductwall] = dirichlet(0);
#if dimension > 2
u.r[ductwall] = dirichlet(0);
#endif
p[ductwall] = neumann(0);
f[ductwall] = dirichlet(0);

static inline double half_w(void) { return 0.5*slot_w; }
static inline double half_h(void) { return 0.5*slot_h; }

static inline double rectangular_slot_phi(double yy, double zz)
{
  return min(half_w() - fabs(yy), half_h() - fabs(zz));
}

int main(int argc, char * argv[])
{
  if (argc > 1)
    maxlevel = atoi(argv[1]);
  if (argc > 2)
    end_time = atof(argv[2]);
  if (argc > 3)
    output_interval = atof(argv[3]);
  if (argc > 4)
    target_we_g = atof(argv[4]);
  if (argc > 5)
    frame_target = atoi(argv[5]);

  if (maxlevel < 7)
    maxlevel = 7;
  if (maxlevel > 10)
    maxlevel = 10;
  if (end_time <= 0.)
    end_time = 0.18;
  if (output_interval <= 0.)
    output_interval = 0.02;
  if (frame_target > 1)
    output_interval = end_time/(frame_target - 1);
  if (target_we_g <= 0.)
    target_we_g = 50.;

  rel_u = fabs(u_l - u_g);
  sigma0 = rho_g*sq(rel_u)*dh/target_we_g;
  mu_l = rho_l*u_l*dh/re_l;
  mu_g = mu_l/25.;

  init_grid(64);
  origin(-duct_length, -0.5*domain_length, -0.5*domain_length);
  size(domain_length);

  rho1 = rho_l, rho2 = rho_g;
  mu1 = mu_l, mu2 = mu_g;
  f.sigma = sigma0;
  CFL = 0.35;

  run();
}

event init(t = 0)
{
  mask(x < 0. && (fabs(y) > half_w() || fabs(z) > half_h()) ? ductwall : none);

  refine(x < external_length*0.20 &&
         fabs(y) < 1.4*slot_w &&
         fabs(z) < 1.6*slot_h &&
         level < maxlevel);

  fraction(slotf, rectangular_slot_phi(y,z));
  slotf.refine = slotf.prolongation = fraction_refine;
  restriction({slotf});

  foreach() {
    double in_duct = (x < 0. && rectangular_slot_phi(y,z) > 0.) ? 1. : 0.;
    f[] = slotf[]*in_duct;
    double liquid_weight = f[];
    u.x[] = u_g + liquid_weight*(u_l - u_g);
    u.y[] = liquid_weight*perturb_amp*u_l*
            sin(2.*pi*perturb_waves_z*z/slot_h);
#if dimension > 2
    u.z[] = liquid_weight*perturb_amp*u_l*
            sin(2.*pi*perturb_waves_y*y/slot_w);
#endif
  }
  boundary({f,u});
}

event logfile(i++)
{
  if (i == 0) {
    double we_g = rho_g*sq(rel_u)*dh/sigma0;
    double we_l = rho_l*sq(rel_u)*dh/sigma0;
    double oh_l = mu_l/sqrt(rho_l*sigma0*dh);
    fprintf(stderr, "design Dh %g duct_Dh %g external_Dh %g We_g %g We_l %g rho_ratio_l_g %g mu_ratio_l_g %g Re_l %g Oh_l %g perturb_amp %g perturb_period %g\n",
            dh, duct_length/dh, external_length/dh, we_g, we_l,
            rho_l/rho_g, mu_l/mu_g, re_l, oh_l, perturb_amp, perturb_period);
    fprintf(stderr, "t dt mgp.i mgpf.i mgu.i cells perf.t perf.speed\n");
  }
  fprintf(stderr, "%g %g %d %d %d %ld %g %g\n",
          t, dt, mgp.i, mgpf.i, mgu.i, grid->tn, perf.t, perf.speed);
}

event outputs(t = 0.; t += output_interval; t <= end_time + 1e-12)
{
  char csv_name[96];
  sprintf(csv_name, "interface_cells_%04d.csv", output_frame);
  FILE * cells = fopen(csv_name, "w");
  if (!cells) {
    fprintf(stderr, "ERROR cannot open %s\n", csv_name);
    return 1;
  }
  fprintf(cells, "frame,time,x,y,z,f,u_x,u_y,u_z,level,cell_size,post_exit\n");
  foreach() {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    if (f[] > 1e-6)
      fprintf(cells,
              "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%d\n",
              output_frame, t, x, y, z, f[], u.x[], u.y[], uz,
              level, Delta, x >= 0.);
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
  fprintf(comps, "frame,time,component_id,volume,centroid_x,centroid_y,centroid_z,cell_count,detached_proxy\n");
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
    double vmax = 0.;
    for (int j = 0; j < n; j++)
      if (volume[j] > vmax)
        vmax = volume[j];
    for (int j = 0; j < n; j++) {
      if (volume[j] > 0.) {
        double cx = center[j].x/volume[j];
        double cy = center[j].y/volume[j];
        double cz = center[j].z/volume[j];
        int detached = cx > 0.5*dh && volume[j] < 0.8*vmax;
        fprintf(comps, "%d,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%d,%d\n",
                output_frame, t, j, volume[j], cx, cy, cz,
                cell_count[j], detached);
      }
    }
  }
  fclose(comps);

  char png_name[96];
  sprintf(png_name, "native_vof_%04d.png", output_frame);
  view(camera = "iso", fov = 10.5, tx = -0.48, ty = 0.30,
       width = 1280, height = 720);
  clear();
  draw_vof("f");
  box();
  save(png_name);

  fprintf(stderr, "output_frame %d time %g cells %s components %s image %s n_components %d\n",
          output_frame, t, csv_name, comp_name, png_name, n);
  output_frame++;
}

event adapt(i++)
{
  scalar speed[];
  foreach() {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    speed[] = sqrt(sq(u.x[]) + sq(u.y[]) + sq(uz));
  }
  boundary({speed});
  adapt_wavelet({f,u,speed}, {0.005,uemax,uemax,uemax,0.06}, maxlevel);
}

event stop(t = end_time)
{
  return 1;
}
