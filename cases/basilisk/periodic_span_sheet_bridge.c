/**
# Quasi-2D periodic-span 3D liquid-sheet bridge

Bounded Basilisk VOF case for testing whether the positive reduced 2D
liquid-sheet instability window transfers to a compact 3D bridge with a short
periodic span. This deliberately avoids the finite-width rectangular-slot side
edges used in earlier negative 3D cases.

This is an internal physics-route bridge only: not validation, not production
CFD, not stationary spray data, not experimental agreement, and not final
atomisation prediction. Connected waviness must not be called atomization.
*/

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"

/* Sheet reference length h = Dh = 1. The domain is cubic in Basilisk's tree
   grid, so the periodic span length is L0 = duct_length + external_length. */
double sheet_h = 1.0;
double dh = 1.0;
double domain_length_h = 4.0;
double duct_length_h = 0.75;
double external_length_h = 3.25;
double duct_length = 0.75;
double external_length = 3.25;
double domain_length = 4.0;

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

/* Mild coherent perturbation matching the positive 2D scout spirit. */
double perturb_amp = 0.02;
double perturb_period = 0.20;
double perturb_waves_y = 1.0;
double spanwise_amp = 0.0;
double spanwise_mode = 1.0;

double end_time = 1.20;
double output_interval = 0.10;
double uemax = 0.05;
double tag_threshold = 1e-3;
int maxlevel = 8;
int minlevel = 6;
int frame_target = 0;
int output_frame = 0;

/* Initial refinement controls. */
int pre_refine_level_offset = 1;
double refine_xmin_h = -0.60;
double refine_xmax_h = 2.20;
double refine_y_factor = 1.35;

scalar sheetf[];
bid ductwall;

static inline double half_h(void) { return 0.5*sheet_h; }

static inline double sheet_phi(double yy)
{
  return half_h() - fabs(yy);
}

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

static inline double gas_vz(void)
{
  return 0.;
}

static inline double span_phase(double zz)
{
  double local_z = zz + 0.5*domain_length;
  return cos(2.*pi*spanwise_mode*local_z/domain_length);
}

static inline double perturb_y(double yy, double zz, double tt)
{
  double base = perturb_amp*u_l*
                sin(2.*pi*tt/perturb_period)*
                sin(2.*pi*perturb_waves_y*yy/sheet_h);
  return base*(1. + spanwise_amp*span_phase(zz));
}

static inline double perturb_z(double yy, double zz, double tt)
{
  return spanwise_amp*perturb_amp*u_l*
         cos(2.*pi*tt/perturb_period)*
         sin(2.*pi*spanwise_mode*(zz + 0.5*domain_length)/domain_length)*
         cos(pi*yy/sheet_h);
}

u.n[left] = dirichlet(gas_vx() + sheetf[]*(u_l - gas_vx()));
u.t[left] = dirichlet(gas_vy() + sheetf[]*(perturb_y(y,z,t) - gas_vy()));
#if dimension > 2
u.r[left] = dirichlet(gas_vz() + sheetf[]*(perturb_z(y,z,t) - gas_vz()));
#endif
p[left] = neumann(0);
f[left] = sheetf[];

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
#if dimension > 2
u.r[ductwall] = dirichlet(0);
#endif
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
    domain_length_h = atof(argv[6]);
  if (argc > 7)
    duct_length_h = atof(argv[7]);
  if (argc > 8)
    perturb_amp = atof(argv[8]);
  if (argc > 9)
    perturb_period = atof(argv[9]);
  if (argc > 10)
    spanwise_amp = atof(argv[10]);
  if (argc > 11)
    spanwise_mode = atof(argv[11]);
  if (argc > 12)
    gas_mode = atoi(argv[12]);
  if (argc > 13)
    gas_speed = atof(argv[13]);
  if (argc > 14)
    uemax = atof(argv[14]);
  if (argc > 15)
    minlevel = atoi(argv[15]);
  if (argc > 16)
    pre_refine_level_offset = atoi(argv[16]);
  if (argc > 17)
    refine_xmin_h = atof(argv[17]);
  if (argc > 18)
    refine_xmax_h = atof(argv[18]);
  if (argc > 19)
    refine_y_factor = atof(argv[19]);
  if (argc > 20)
    tag_threshold = atof(argv[20]);

  if (maxlevel < 6)
    maxlevel = 6;
  if (maxlevel > 10)
    maxlevel = 10;
  if (minlevel < 5)
    minlevel = 5;
  if (minlevel > maxlevel)
    minlevel = maxlevel;
  if (end_time <= 0.)
    end_time = 1.2;
  if (output_interval <= 0.)
    output_interval = 0.1;
  if (frame_target > 1)
    output_interval = end_time/(frame_target - 1);
  if (target_we_g <= 0.)
    target_we_g = 80.;
  if (domain_length_h < 2.0)
    domain_length_h = 2.0;
  if (duct_length_h < 0.25)
    duct_length_h = 0.25;
  if (duct_length_h > domain_length_h - 0.75)
    duct_length_h = domain_length_h - 0.75;
  if (perturb_period <= 0.)
    perturb_period = 0.2;
  if (spanwise_amp < 0.)
    spanwise_amp = fabs(spanwise_amp);
  if (spanwise_mode < 0.)
    spanwise_mode = fabs(spanwise_mode);
  if (spanwise_mode < 0.5)
    spanwise_mode = 0.;
  if (gas_mode < 0 || gas_mode > 3)
    gas_mode = 0;
  if (gas_speed < 0.)
    gas_speed = fabs(gas_speed);
  if (uemax <= 0.)
    uemax = 0.05;
  if (pre_refine_level_offset < 0)
    pre_refine_level_offset = 0;
  if (pre_refine_level_offset > 4)
    pre_refine_level_offset = 4;
  if (refine_y_factor < 0.75)
    refine_y_factor = 0.75;
  if (tag_threshold <= 0.)
    tag_threshold = 1e-3;

  domain_length = domain_length_h*sheet_h;
  duct_length = duct_length_h*sheet_h;
  external_length = domain_length - duct_length;
  external_length_h = external_length/sheet_h;

  rel_u = sqrt(sq(u_l - gas_vx()) + sq(gas_vy()) + sq(gas_vz()));
  if (rel_u <= 0.)
    rel_u = u_l;
  sigma0 = rho_g*sq(rel_u)*dh/target_we_g;
  mu_l = rho_l*u_l*dh/re_l;
  mu_g = mu_l/25.;

  origin(-duct_length, -0.5*domain_length, -0.5*domain_length);
  size(domain_length);
#if dimension > 2
  periodic(front);
#endif
  init_grid(1 << minlevel);

  rho1 = rho_l, rho2 = rho_g;
  mu1 = mu_l, mu2 = mu_g;
  f.sigma = sigma0;
  CFL = 0.35;

  run();
}

event init(t = 0)
{
  mask(x < 0. && fabs(y) > half_h() ? ductwall : none);

  int pre_level = maxlevel - pre_refine_level_offset;
  if (pre_level < minlevel)
    pre_level = minlevel;

  refine(x > refine_xmin_h*sheet_h &&
         x < refine_xmax_h*sheet_h &&
         fabs(y) < refine_y_factor*sheet_h &&
         level < pre_level);

  fraction(sheetf, sheet_phi(y));
  sheetf.refine = sheetf.prolongation = fraction_refine;
  restriction({sheetf});

  foreach() {
    double in_duct = (x < 0. && sheet_phi(y) > 0.) ? 1. : 0.;
    f[] = sheetf[]*in_duct;
    double liquid_weight = f[];
    u.x[] = gas_vx() + liquid_weight*(u_l - gas_vx());
    u.y[] = gas_vy() + liquid_weight*(perturb_y(y,z,t) - gas_vy());
#if dimension > 2
    u.z[] = gas_vz() + liquid_weight*(perturb_z(y,z,t) - gas_vz());
#endif
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
            "design model quasi_2d_periodic_span_3d_sheet h %g Dh %g duct_h %g external_h %g domain_h %g span_h %g We_g %g We_l %g rho_ratio_l_g %g mu_ratio_l_g %g Re_l %g Re_g %g Oh_l %g maxlevel %d minlevel %d cells_across_sheet %g cells_across_span %g perturb_amp %g perturb_period %g waves_y %g spanwise_amp %g spanwise_mode %g gas_mode %d gas_speed %g rel_u %g sigma %g pre_refine_offset %d refine_xmin_h %g refine_xmax_h %g refine_y_factor %g tag_threshold %g periodic_z 1\n",
            sheet_h, dh, duct_length/sheet_h, external_length/sheet_h,
            domain_length/sheet_h, domain_length/sheet_h, we_g, we_l,
            rho_l/rho_g, mu_l/mu_g, re_l, re_g, oh_l, maxlevel, minlevel,
            sheet_h/delta, domain_length/delta, perturb_amp, perturb_period,
            perturb_waves_y, spanwise_amp, spanwise_mode, gas_mode, gas_speed,
            rel_u, sigma0, pre_refine_level_offset, refine_xmin_h,
            refine_xmax_h, refine_y_factor, tag_threshold);
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
  fprintf(comps, "frame,time,component_id,volume,centroid_x,centroid_y,centroid_z,cell_count,detached_proxy,post_exit_only\n");
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
      if (labels[] > 0) {
        int j = labels[] - 1;
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
        int detached = post_exit_only ? (n > 1 && volume[j] < 0.8*vmax)
                                      : (cx > 0.5*sheet_h && volume[j] < 0.8*vmax);
        fprintf(comps, "%d,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%d,%d,%d\n",
                output_frame, tt, j, volume[j], cx, cy, cz,
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
  fprintf(cells, "frame,time,x,y,z,f,u_x,u_y,u_z,level,cell_size,post_exit,interface_cell\n");
  foreach() {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    if (f[] > 1e-6)
      fprintf(cells,
              "%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%d,%d\n",
              output_frame, t, x, y, z, f[], u.x[], u.y[], uz,
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
  view(camera = "iso", fov = 20.0, tx = -0.20, ty = 0.15,
       width = 1280, height = 720);
  clear();
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
  foreach() {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    speed[] = sqrt(sq(u.x[]) + sq(u.y[]) + sq(uz));
  }
  boundary({speed});
  adapt_wavelet({f,u,speed}, {0.003,uemax,uemax,uemax,0.03}, maxlevel);
}

event stop(t = end_time)
{
  return 1;
}
