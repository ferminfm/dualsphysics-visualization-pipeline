/**
# Planar slot shear-sigma scout

Bounded 2D Basilisk VOF scout for mapping gas-side Weber number, surface
tension scaling, gas shear, and perturbation sensitivity after negative 3D
rectangular-slot morphology results.

This is a reduced 2D/planar instability scout, not a faithful 3D rectangular
slot simulation, not validation, not production CFD, not stationary spray data,
not experimental agreement, and not final atomisation prediction. Connected
waviness must not be called atomization.
*/

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"

/* 2D sheet/slot geometry. Reference length h = Dh = 1. */
double sheet_h = 1.0;
double dh = 1.0;
double duct_length_Dh = 4.0;
double external_length_Dh = 12.0;
double duct_length = 4.0;
double external_length = 12.0;
double domain_length = 16.0;

/* Nondimensional physical/proxy choices. */
double rho_l = 1.0;
double rho_g = 0.05;
double u_l = 1.0;
double target_we_g = 80.0;
double sigma0 = 0.000625;
double re_l = 1200.0;
double mu_l = 0.0008333333333333334;
double mu_g = 0.000033333333333333335;
double rel_u = 1.0;

/* Gas forcing mode: 0 none, 1 coflow-x, 2 counterflow-x, 3 crossflow-y. */
int gas_mode = 0;
double gas_speed = 0.0;

/* Reproducible transverse inlet perturbation. */
double perturb_amp = 0.02;
double perturb_period = 0.20;
double perturb_waves_y = 1.0;

double end_time = 4.0;
double output_interval = 0.25;
double uemax = 0.05;
double tag_threshold = 1e-3;
int maxlevel = 10;
int frame_target = 0;
int output_frame = 0;

scalar slotf[];
bid ductwall;

static inline double half_h(void) { return 0.5*sheet_h; }

static inline double gas_vx(void)
{
  if (gas_mode == 1)
    return gas_speed;
  if (gas_mode == 2)
    return -gas_speed;
  return 0.;
}

static inline double gas_vy(void)
{
  return gas_mode == 3 ? gas_speed : 0.;
}

static inline double perturb_y(double yy, double tt)
{
  return perturb_amp*u_l*
         sin(2.*pi*tt/perturb_period)*
         sin(2.*pi*perturb_waves_y*yy/sheet_h);
}

u.n[left] = dirichlet(gas_vx() + slotf[]*(u_l - gas_vx()));
u.t[left] = dirichlet(gas_vy() + slotf[]*(perturb_y(y,t) - gas_vy()));
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

u.n[ductwall] = dirichlet(0);
u.t[ductwall] = dirichlet(0);
p[ductwall] = neumann(0);
f[ductwall] = dirichlet(0);

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
  if (argc > 6)
    external_length_Dh = atof(argv[6]);
  if (argc > 7)
    perturb_amp = atof(argv[7]);
  if (argc > 8)
    perturb_period = atof(argv[8]);
  if (argc > 9)
    gas_mode = atoi(argv[9]);
  if (argc > 10)
    gas_speed = atof(argv[10]);
  if (argc > 11)
    perturb_waves_y = atof(argv[11]);
  if (argc > 12)
    uemax = atof(argv[12]);

  if (maxlevel < 7)
    maxlevel = 7;
  if (maxlevel > 11)
    maxlevel = 11;
  if (end_time <= 0.)
    end_time = 4.;
  if (output_interval <= 0.)
    output_interval = 0.25;
  if (frame_target > 1)
    output_interval = end_time/(frame_target - 1);
  if (target_we_g <= 0.)
    target_we_g = 80.;
  if (external_length_Dh < 4.)
    external_length_Dh = 4.;
  if (perturb_period <= 0.)
    perturb_period = 0.2;
  if (gas_mode < 0 || gas_mode > 3)
    gas_mode = 0;
  if (gas_speed < 0.)
    gas_speed = fabs(gas_speed);
  if (uemax <= 0.)
    uemax = 0.05;

  duct_length = duct_length_Dh*dh;
  external_length = external_length_Dh*dh;
  domain_length = duct_length + external_length;

  rel_u = sqrt(sq(u_l - gas_vx()) + sq(gas_vy()));
  if (rel_u <= 0.)
    rel_u = u_l;
  sigma0 = rho_g*sq(rel_u)*dh/target_we_g;
  mu_l = rho_l*u_l*dh/re_l;
  mu_g = mu_l/25.;

  init_grid(128);
  origin(-duct_length, -0.5*domain_length);
  size(domain_length);

  rho1 = rho_l, rho2 = rho_g;
  mu1 = mu_l, mu2 = mu_g;
  f.sigma = sigma0;
  CFL = 0.35;

  run();
}

event init(t = 0)
{
  mask(x < 0. && fabs(y) > half_h() ? ductwall : none);

  refine(x < external_length*0.45 &&
         fabs(y) < 3.0*sheet_h &&
         level < maxlevel);

  fraction(slotf, half_h() - fabs(y));
  slotf.refine = slotf.prolongation = fraction_refine;
  restriction({slotf});

  foreach() {
    double in_duct = (x < 0. && fabs(y) <= half_h()) ? 1. : 0.;
    f[] = slotf[]*in_duct;
    double liquid_weight = f[];
    u.x[] = gas_vx() + liquid_weight*(u_l - gas_vx());
    u.y[] = gas_vy() + liquid_weight*(perturb_y(y,t) - gas_vy());
  }
  boundary({f,u});
}

event logfile(i++)
{
  if (i == 0) {
    double we_g = rho_g*sq(rel_u)*dh/sigma0;
    double we_l = rho_l*sq(rel_u)*dh/sigma0;
    double re_g = rho_g*rel_u*dh/mu_g;
    double oh_l = mu_l/sqrt(rho_l*sigma0*dh);
    double delta = domain_length/pow(2., maxlevel);
    fprintf(stderr,
            "design model 2D_planar_slot Dh %g duct_Dh %g external_Dh %g domain_Dh %g We_g %g We_l %g rho_ratio_l_g %g mu_ratio_l_g %g Re_l %g Re_g %g Oh_l %g maxlevel %d cells_across_sheet %g perturb_amp %g perturb_period %g waves_y %g gas_mode %d gas_speed %g rel_u %g sigma %g\n",
            dh, duct_length/dh, external_length/dh, domain_length/dh,
            we_g, we_l, rho_l/rho_g, mu_l/mu_g, re_l, re_g, oh_l,
            maxlevel, sheet_h/delta, perturb_amp, perturb_period,
            perturb_waves_y, gas_mode, gas_speed, rel_u, sigma0);
    fprintf(stderr, "t dt mgp.i mgpf.i mgu.i cells perf.t perf.speed\n");
  }
  fprintf(stderr, "%g %g %d %d %d %ld %g %g\n",
          t, dt, mgp.i, mgpf.i, mgu.i, grid->tn, perf.t, perf.speed);
}

static void write_components(char * name, scalar labels, int n, double tt,
                             int post_exit_only)
{
  FILE * comps = fopen(name, "w");
  if (!comps) {
    fprintf(stderr, "ERROR cannot open %s\n", name);
    return;
  }
  fprintf(comps, "frame,time,component_id,area,centroid_x,centroid_y,cell_count,detached_proxy,post_exit_only\n");
  if (n > 0) {
    double area[n];
    double cx[n], cy[n];
    int cell_count[n];
    for (int j = 0; j < n; j++) {
      area[j] = 0.;
      cx[j] = cy[j] = 0.;
      cell_count[j] = 0;
    }
    foreach(serial) {
      if (labels[] > 0) {
        int j = labels[] - 1;
        double w = sq(Delta)*f[];
        area[j] += w;
        cx[j] += w*x;
        cy[j] += w*y;
        cell_count[j]++;
      }
    }
    double amax = 0.;
    for (int j = 0; j < n; j++)
      if (area[j] > amax)
        amax = area[j];
    for (int j = 0; j < n; j++) {
      if (area[j] > 0.) {
        int detached = post_exit_only ? (n > 1 && area[j] < 0.8*amax)
                                      : ((cx[j]/area[j]) > 0.5*dh &&
                                         area[j] < 0.8*amax);
        fprintf(comps, "%d,%.12g,%d,%.12g,%.12g,%.12g,%d,%d,%d\n",
                output_frame, tt, j, area[j], cx[j]/area[j], cy[j]/area[j],
                cell_count[j], detached, post_exit_only);
      }
    }
  }
  fclose(comps);
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
  fprintf(cells, "frame,time,x,y,f,u_x,u_y,level,cell_size,post_exit,interface_cell\n");
  foreach() {
    if (f[] > 1e-6)
      fprintf(cells,
              "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%d,%d\n",
              output_frame, t, x, y, f[], u.x[], u.y[],
              level, Delta, x >= 0., f[] > 1e-6 && f[] < 1. - 1e-6);
  }
  fclose(cells);

  scalar m[];
  foreach()
    m[] = f[] > tag_threshold;
  int n = tag(m);
  char comp_name[96];
  sprintf(comp_name, "components_%04d.csv", output_frame);
  write_components(comp_name, m, n, t, 0);

  scalar mp[];
  foreach()
    mp[] = (x >= 0. && f[] > tag_threshold);
  int np = tag(mp);
  char post_comp_name[96];
  sprintf(post_comp_name, "post_components_%04d.csv", output_frame);
  write_components(post_comp_name, mp, np, t, 1);

  char png_name[96];
  sprintf(png_name, "native_vof_%04d.png", output_frame);
  view(width = 1280, height = 720, fov = 16.0, tx = -0.22, ty = 0.0);
  clear();
  squares("f", min = 0., max = 1.);
  draw_vof("f");
  box();
  save(png_name);

  fprintf(stderr,
          "output_frame %d time %g cells %s components %s post_components %s image %s n_components %d n_post_components %d\n",
          output_frame, t, csv_name, comp_name, post_comp_name, png_name,
          n, np);
  output_frame++;
}

event adapt(i++)
{
  scalar speed[];
  foreach()
    speed[] = sqrt(sq(u.x[]) + sq(u.y[]));
  boundary({speed});
  adapt_wavelet({f,u,speed}, {0.003,uemax,uemax,0.03}, maxlevel);
}

event stop(t = end_time)
{
  return 1;
}
