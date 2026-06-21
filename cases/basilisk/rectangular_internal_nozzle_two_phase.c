
#include "grid/octree.h"
#include "embed.h"
#include "navier-stokes/centered.h"
#define mu(f) (1./(clamp(f,0.,1.)*(1./mu1 - 1./mu2) + 1./mu2))
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include <string.h>

/*
 * Coupled two-phase rectangular internal-nozzle prototype.
 *
 * Output-root prototype derived from the Task 1 calibrated pressure-driven
 * embedded-wall nozzle. This is not a public atomisation claim or showcase.
 * It preserves pressure-driven injection and never imposes a uniform velocity
 * at the visual nozzle exit.
 *
 * Captured in this repository from:
 * /home/franco/stack-validation/20260620-basilisk-internal-nozzle-two-phase-prototype/case_work/rectangular_internal_nozzle_two_phase.c
 */

scalar un[];

int maxlevel = 6;
int baselevel = 4;
int case_mode = 0; /* 0=P0 smoke, 1=P1 retune, 2=P2 baseline */
int max_steps = 8000;
int last_iter = 0;
int wrote_summary = 0;

double official_r = 1./12.;
double A0, D0, Wrect, Hrect, Dhrect;
double pressure_value = 2524.75;
double target_u = 1.0;
double end_time = 0.04;
double frame_dt = 0.01;
double dt_cap = 2e-4;
double Ldomain = 1.0;
double x_origin_nozzle = 0.0;
double plenum_Dh = 2.0;
double contraction_Dh = 3.0;
double straight_Dh = 10.0;
double external_Dh = 3.0;
double plenum_scale = 3.0;
double uemax = 0.25;
double liquid_threshold = 1e-3;
double credible_volume_threshold = 1e-6;
char case_id[128] = "P0";
char output_dir[512] = ".";

double max_active_front = 0.;
double max_interface_proxy = 0.;
double initial_interface_proxy = 0.;
double max_interface_growth = 0.;
int max_post_tag_count = 0;
int max_detached_proxy_count = 0;
int max_one_cell_debris_count = 0;
double final_mean_exit_velocity = 0.;
double final_liquid_volume = 0.;
double initial_liquid_volume = -1.;
double final_liquid_volume_error = 0.;
int stable_flag = 1;

static double clamp01_local (double a) {
  return a < 0. ? 0. : (a > 1. ? 1. : a);
}

static double smoothstep (double a) {
  a = clamp01_local(a);
  return a*a*(3. - 2.*a);
}

static double exit_x (void) {
  return x_origin_nozzle + (plenum_Dh + contraction_Dh + straight_Dh)*Dhrect;
}

static double width_internal (double xp) {
  double xrel = xp - x_origin_nozzle;
  double Lp = plenum_Dh*Dhrect;
  double Lc = contraction_Dh*Dhrect;
  if (xrel <= Lp)
    return plenum_scale*Wrect;
  if (xrel <= Lp + Lc) {
    double s = smoothstep((xrel - Lp)/Lc);
    return (1. - s)*plenum_scale*Wrect + s*Wrect;
  }
  return Wrect;
}

static double height_internal (double xp) {
  double xrel = xp - x_origin_nozzle;
  double Lp = plenum_Dh*Dhrect;
  double Lc = contraction_Dh*Dhrect;
  if (xrel <= Lp)
    return plenum_scale*Hrect;
  if (xrel <= Lp + Lc) {
    double s = smoothstep((xrel - Lp)/Lc);
    return (1. - s)*plenum_scale*Hrect + s*Hrect;
  }
  return Hrect;
}

static double internal_phi (double xp, double yp, double zp) {
  double w = width_internal(xp);
  double h = height_internal(xp);
  return min(w/2. - fabs(yp), h/2. - fabs(zp));
}

static double geometry_phi (double xp, double yp, double zp) {
  if (xp <= exit_x())
    return internal_phi(xp, yp, zp);
  return 1.; /* downstream external gas domain is open fluid */
}

static double initial_liquid_phi (double xp, double yp, double zp) {
  return min(internal_phi(xp, yp, zp), exit_x() - xp);
}

static void output_path (char *buf, int n, const char *leaf) {
  snprintf(buf, n, "%s/%s", output_dir, leaf);
}

static void print_usage (const char *prog) {
  fprintf(stdout,
          "usage: %s [case_id] [case_mode] [maxlevel] [pressure_value] [end_time] [external_Dh] [output_dir] [frame_dt]\n"
          "\n"
          "Coupled two-phase rectangular internal-nozzle prototype.\n"
          "Default output_dir is current directory. Create it before running.\n"
          "Selected upstream case used: P2_L7_long 2 7 351.48 0.12 3.0 OUTPUT_DIR 0.03.\n"
          "Claim boundary: stable connected-jet prototype only; not breakup or atomisation validation.\n",
          prog);
}

static void build_geometry (void) {
  vertex scalar phi[];
  foreach_vertex()
    phi[] = geometry_phi(x, y, z);
  boundary ({phi});
  fractions (phi, cs, fs);
  fractions_cleanup (cs, fs);
}

u.n[embed] = dirichlet(0.);
u.t[embed] = dirichlet(0.);
u.r[embed] = dirichlet(0.);

u.n[left] = neumann(0.);
u.t[left] = neumann(0.);
u.r[left] = neumann(0.);
u.n[right] = neumann(0.);
u.t[right] = neumann(0.);
u.r[right] = neumann(0.);
p[left] = dirichlet(pressure_value);
pf[left] = dirichlet(pressure_value);
p[right] = dirichlet(0.);
pf[right] = dirichlet(0.);
f[left] = dirichlet(1.);
f[right] = neumann(0.);

static void compute_exit_metrics (double *mean_u, double *flow, double *area, double *profile_sanity) {
  double xs = exit_x() - 0.5*Dhrect;
  double sumu = 0., suma = 0., profile_num = 0., profile_den = 0.;
  foreach(reduction(+:sumu) reduction(+:suma) reduction(+:profile_num) reduction(+:profile_den)) {
    if (cs[] > 1e-8 && fabs(x - xs) <= 0.75*Delta) {
      double aw = f[]*cs[]*sq(Delta);
      sumu += u.x[]*aw;
      suma += aw;
      double wx = width_internal(x);
      double hx = height_internal(x);
      double wall_dist = min(wx/2. - fabs(y), hx/2. - fabs(z));
      if (wall_dist > 1.5*Delta) {
        profile_num += fabs(u.y[]) + fabs(u.z[]);
        profile_den += fabs(u.x[]) + 1e-12;
      }
    }
  }
  *mean_u = suma > 0. ? sumu/suma : 0.;
  *flow = sumu;
  *area = suma;
  *profile_sanity = profile_den > 0. ? profile_num/profile_den : 0.;
}

static double liquid_volume_total (void) {
  double vol = 0.;
  foreach(reduction(+:vol))
    if (cs[] > 1e-8)
      vol += f[]*dv();
  return vol;
}

static double interface_proxy_now (void) {
  double proxy = 0.;
  foreach(reduction(+:proxy))
    if (cs[] > 1e-8 && f[] > 1e-3 && f[] < 1. - 1e-3)
      proxy += sq(Delta);
  return proxy;
}

static double active_front_now (void) {
  double af = 0.;
  double xe = exit_x();
  foreach(reduction(max:af))
    if (cs[] > 1e-8 && f[] > liquid_threshold && x > xe)
      af = max(af, x - xe);
  return af;
}

static void write_profile_samples (FILE *fp) {
  double xs = exit_x() - 0.5*Dhrect;
  foreach(serial) {
    if (cs[] > 1e-8 && fabs(x - xs) <= 0.75*Delta) {
      fprintf(fp, "%s,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",
              case_id, t, x, y, z, f[], u.x[], u.y[], u.z[], cs[], cs[]*sq(Delta), Wrect, Hrect);
    }
  }
}

static void write_cross_sections (FILE *fp) {
  const int ns = 10;
  double xe = exit_x();
  for (int s = 0; s < ns; s++) {
    double xp = xe + (s + 1)*external_Dh*Dhrect/(ns + 1);
    double area = 0., cy = 0., cz = 0., ymin = HUGE, ymax = -HUGE, zmin = HUGE, zmax = -HUGE;
    double covyy = 0., covzz = 0., covyz = 0.;
    foreach(serial) {
      if (cs[] > 1e-8 && fabs(x - xp) <= 0.75*Delta && f[] > liquid_threshold) {
        double aw = f[]*sq(Delta);
        area += aw;
        cy += y*aw;
        cz += z*aw;
        ymin = min(ymin, y);
        ymax = max(ymax, y);
        zmin = min(zmin, z);
        zmax = max(zmax, z);
      }
    }
    if (area > 0.) {
      cy /= area; cz /= area;
      foreach(serial) {
        if (cs[] > 1e-8 && fabs(x - xp) <= 0.75*Delta && f[] > liquid_threshold) {
          double aw = f[]*sq(Delta);
          covyy += sq(y - cy)*aw;
          covzz += sq(z - cz)*aw;
          covyz += (y - cy)*(z - cz)*aw;
        }
      }
      covyy /= area; covzz /= area; covyz /= area;
      double width = ymax - ymin;
      double thickness = zmax - zmin;
      double aspect = thickness > 0. ? width/thickness : 0.;
      double warp = sqrt(sq(covyy - covzz) + 4.*sq(covyz))/(covyy + covzz + 1e-30);
      fprintf(fp, "%s,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",
              case_id, t, s, xp - xe, area, width, thickness, aspect, cy, cz, covyz, warp, Dhrect);
    }
    else {
      fprintf(fp, "%s,%.12g,%d,%.12g,0,0,0,0,0,0,0,0,%.12g\n",
              case_id, t, s, xp - xe, Dhrect);
    }
  }
}

static void write_component_diagnostics (FILE *fp, int *tag_count, int *detached_proxy, int *one_cell_debris) {
  scalar m[];
  double xe = exit_x();
  foreach()
    m[] = (cs[] > 1e-8 && x > xe + 0.05*Dhrect && f[] > liquid_threshold);
  int n = tag(m);
  *tag_count = n;
  *detached_proxy = 0;
  *one_cell_debris = 0;
  if (n <= 0)
    return;
  double vol[n], bx[n], by[n], bz[n];
  int cells[n];
  for (int j = 0; j < n; j++)
    vol[j] = bx[j] = by[j] = bz[j] = 0., cells[j] = 0;
  foreach(serial) {
    if (m[] > 0) {
      int j = m[] - 1;
      double vv = f[]*dv();
      vol[j] += vv;
      bx[j] += x*vv;
      by[j] += y*vv;
      bz[j] += z*vv;
      cells[j]++;
    }
  }
  for (int j = 0; j < n; j++) {
    double cx = vol[j] > 0. ? bx[j]/vol[j] : 0.;
    double cy = vol[j] > 0. ? by[j]/vol[j] : 0.;
    double cz = vol[j] > 0. ? bz[j]/vol[j] : 0.;
    int credible = (vol[j] > credible_volume_threshold && cells[j] > 1);
    if (!credible)
      (*one_cell_debris)++;
    if (credible && cx > xe + 0.15*Dhrect)
      (*detached_proxy)++;
    fprintf(fp, "%s,%.12g,%d,%d,%.12g,%d,%.12g,%.12g,%.12g,%d\n",
            case_id, t, j, n, vol[j], cells[j], cx - xe, cy, cz, credible);
  }
}

int main (int argc, char **argv) {
  if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
    print_usage(argv[0]);
    return 0;
  }

  A0 = pi*sq(official_r);
  D0 = 2.*official_r;
  Wrect = sqrt(2.*A0);
  Hrect = Wrect/2.;
  Dhrect = 2.*Wrect*Hrect/(Wrect + Hrect);

  if (argc > 1) snprintf(case_id, sizeof(case_id), "%s", argv[1]);
  if (argc > 2) case_mode = atoi(argv[2]);
  if (argc > 3) maxlevel = atoi(argv[3]);
  if (argc > 4) pressure_value = atof(argv[4]);
  if (argc > 5) end_time = atof(argv[5]);
  if (argc > 6) external_Dh = atof(argv[6]);
  if (argc > 7) snprintf(output_dir, sizeof(output_dir), "%s", argv[7]);
  if (argc > 8) frame_dt = atof(argv[8]);

  Ldomain = (plenum_Dh + contraction_Dh + straight_Dh + external_Dh)*Dhrect;
  x_origin_nozzle = 0.;
  size(Ldomain);
  origin(x_origin_nozzle, -0.5*Ldomain, -0.5*Ldomain);
  init_grid(1 << baselevel);

  rho1 = 1.;
  rho2 = rho1/27.84;
  mu1 = 1.;
  mu2 = mu1/27.84;
  f.sigma = 3e-5;

  DT = dt_cap;
  TOLERANCE = 1e-5;
  NITERMIN = 2;
  run();
}

event init (t = 0) {
  for (scalar s in {u, p, pf})
    s.third = true;

  double refine_band = plenum_scale*Wrect;
  refine (x <= exit_x() + external_Dh*Dhrect &&
          fabs(y) < 0.75*refine_band &&
          fabs(z) < 0.75*refine_band &&
          level < maxlevel);
  build_geometry();

  fraction (f, initial_liquid_phi(x,y,z));
  f.refine = f.prolongation = fraction_refine;
  restriction ({f});

  foreach() {
    foreach_dimension()
      u.x[] = 0.;
    un[] = u.x[];
  }
  boundary ({f, u, un});

  char path[1024];
  output_path(path, sizeof(path), "two_phase_frame_diagnostics.csv");
  FILE *fp = fopen(path, "w");
  fprintf(fp, "case_id,t,i,mean_exit_velocity,exit_flow,exit_liquid_area,profile_sanity,liquid_volume,liquid_volume_error,active_front,interface_proxy,interface_growth,post_tag_count,detached_proxy_count,one_cell_debris_count\n");
  fclose(fp);
  output_path(path, sizeof(path), "two_phase_component_diagnostics.csv");
  fp = fopen(path, "w");
  fprintf(fp, "case_id,t,component_id,tag_count,volume,cells,centroid_x_from_exit,centroid_y,centroid_z,credible\n");
  fclose(fp);
  output_path(path, sizeof(path), "two_phase_cross_section_metrics.csv");
  fp = fopen(path, "w");
  fprintf(fp, "case_id,t,station_id,x_from_exit,area_proxy,width,thickness,aspect_ratio,centroid_y,centroid_z,cov_yz,warp_proxy,Dh\n");
  fclose(fp);
  output_path(path, sizeof(path), "two_phase_profile_samples.csv");
  fp = fopen(path, "w");
  fprintf(fp, "case_id,t,x,y,z,f,ux,uy,uz,cs,area_weight,width,height\n");
  fclose(fp);
}

event diagnostics (t = 0.; t += frame_dt; t <= end_time) {
  last_iter = i;
  double mean_u = 0., flow = 0., area = 0., ps = 0.;
  compute_exit_metrics(&mean_u, &flow, &area, &ps);
  final_mean_exit_velocity = mean_u;
  double lv = liquid_volume_total();
  if (initial_liquid_volume < 0.)
    initial_liquid_volume = lv;
  final_liquid_volume = lv;
  final_liquid_volume_error = initial_liquid_volume > 0. ? fabs(lv - initial_liquid_volume)/initial_liquid_volume : 0.;
  double af = active_front_now();
  double ip = interface_proxy_now();
  if (initial_interface_proxy <= 0. && ip > 0.)
    initial_interface_proxy = ip;
  double growth = initial_interface_proxy > 0. ? ip/initial_interface_proxy : 1.;
  max_active_front = max(max_active_front, af);
  max_interface_proxy = max(max_interface_proxy, ip);
  max_interface_growth = max(max_interface_growth, growth);

  char path[1024];
  output_path(path, sizeof(path), "two_phase_component_diagnostics.csv");
  FILE *comp = fopen(path, "a");
  int nt = 0, nd = 0, debris = 0;
  write_component_diagnostics(comp, &nt, &nd, &debris);
  fclose(comp);
  max_post_tag_count = max(max_post_tag_count, nt);
  max_detached_proxy_count = max(max_detached_proxy_count, nd);
  max_one_cell_debris_count = max(max_one_cell_debris_count, debris);

  output_path(path, sizeof(path), "two_phase_cross_section_metrics.csv");
  FILE *xs = fopen(path, "a");
  write_cross_sections(xs);
  fclose(xs);

  output_path(path, sizeof(path), "two_phase_profile_samples.csv");
  FILE *prof = fopen(path, "a");
  write_profile_samples(prof);
  fclose(prof);

  output_path(path, sizeof(path), "two_phase_frame_diagnostics.csv");
  FILE *fp = fopen(path, "a");
  fprintf(fp, "%s,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d\n",
          case_id, t, i, mean_u, flow, area, ps, lv, final_liquid_volume_error, af, ip, growth, nt, nd, debris);
  fclose(fp);

  if (final_liquid_volume_error > 0.5)
    stable_flag = 0;
}

event logfile (i++) {
  last_iter = i;
  double du = change(u.x, un);
  if (i >= max_steps) {
    stable_flag = 0;
    return 1;
  }
  if (du != du) {
    stable_flag = 0;
    return 1;
  }
}

event end (t = end_time) {
  if (wrote_summary)
    return 0;
  wrote_summary = 1;
  char path[1024];
  output_path(path, sizeof(path), "two_phase_case_summary.csv");
  FILE *fp = fopen(path, "w");
  fprintf(fp, "case_id,case_mode,t,i,maxlevel,baselevel,pressure_value,target_u,mean_exit_velocity,pressure_retuned,liquid_volume,liquid_volume_error,max_active_front,max_interface_proxy,max_interface_growth,max_post_tag_count,max_detached_proxy_count,max_one_cell_debris_count,width,height,Dh,external_Dh,stable_flag\n");
  fprintf(fp, "%s,%d,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%d\n",
          case_id, case_mode, t, last_iter, maxlevel, baselevel, pressure_value, target_u, final_mean_exit_velocity,
          fabs(pressure_value - 2524.75) > 1e-6, final_liquid_volume, final_liquid_volume_error,
          max_active_front, max_interface_proxy, max_interface_growth, max_post_tag_count,
          max_detached_proxy_count, max_one_cell_debris_count, Wrect, Hrect, Dhrect, external_Dh, stable_flag);
  fclose(fp);
}
