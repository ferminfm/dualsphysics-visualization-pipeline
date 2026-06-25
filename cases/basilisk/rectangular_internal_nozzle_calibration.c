
#include "grid/octree.h"
#include "embed.h"
#include "navier-stokes/centered.h"
#include "navier-stokes/perfs.h"
#include <string.h>

/*
 * Pressure-driven rectangular internal-nozzle calibration harness.
 *
 * This source is derived from local Basilisk API patterns in:
 * - src/examples/porous3D.c for 3D embedded no-slip Stokes flow and body forcing
 * - src/examples/naca2414-starting.c for embedded-wall no-slip boundary setup
 * - src/test/poiseuille*.c for pressure-driven/Poiseuille reference patterns
 *
 * Captured in this repository from:
 * /home/franco/stack-validation/20260620-basilisk-internal-nozzle-calibration/case_work/rectangular_internal_nozzle_calibration.c
 *
 * It is not a public atomisation case. It emits profile diagnostics only.
 */

scalar un[];
face vector muv[];

int maxlevel = 7;
int baselevel = 4;
int case_mode = 0; /* 0=D0 straight periodic, 1=D1 straight transient, 5/10/20=C5/C10/C20 */
int max_steps = 5000;
int wrote_outputs = 0;
int last_iter = 0;

double official_r = 1./12.;
double A0, D0, Wrect, Hrect, Prect, Dhrect;
double dyn_visc = 1.;
double forcing_value = 1.; /* body acceleration for D0/D1 or left pressure for C cases */
double target_u = 1.;
double end_time = 1.0;
double steady_tol = 1e-5;
double dt_cap = 2e-3;
double Ldomain = 1.0;
double x_origin_nozzle = -0.5;
double plenum_Dh = 2.0;
double contraction_Dh = 3.0;
double straight_Dh = 8.0;
double plenum_scale = 3.0;
char case_id[128] = "D0";
char output_dir[512] = ".";

static double clamp01 (double a) {
  return a < 0. ? 0. : (a > 1. ? 1. : a);
}

static double smoothstep (double a) {
  a = clamp01(a);
  return a*a*(3. - 2.*a);
}

static double width_at_x (double xp) {
  if (case_mode == 0 || case_mode == 1)
    return Wrect;
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

static double height_at_x (double xp) {
  if (case_mode == 0 || case_mode == 1)
    return Hrect;
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

static double phi_nozzle (double xp, double yp, double zp) {
  double w = width_at_x(xp);
  double h = height_at_x(xp);
  return min(w/2. - fabs(yp), h/2. - fabs(zp));
}

static double sample_x_location (void) {
  if (case_mode == 0 || case_mode == 1)
    return x_origin_nozzle + 0.5*Ldomain;
  double xrel = plenum_Dh*Dhrect + contraction_Dh*Dhrect + straight_Dh*Dhrect - 0.5*Dhrect;
  return x_origin_nozzle + xrel;
}

static void output_path (char *buf, int n, const char *leaf) {
  snprintf(buf, n, "%s/%s", output_dir, leaf);
}

static void print_usage (const char *prog) {
  fprintf(stdout,
          "usage: %s [case_id] [case_mode] [maxlevel] [forcing_value] [end_time] [straight_Dh] [output_dir]\n"
          "\n"
          "Pressure-driven rectangular internal-nozzle calibration harness.\n"
          "Default output_dir is current directory. Create it before running.\n"
          "Selected upstream case used: C10_L7_pin2525 10 7 2524.75 0.5 10.0 OUTPUT_DIR.\n"
          "Claim boundary: profile/calibration diagnostics only; not atomisation validation.\n",
          prog);
}

static void build_geometry (void) {
  vertex scalar phi[];
  foreach_vertex()
    phi[] = phi_nozzle(x, y, z);
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

p[left] = dirichlet(case_mode >= 5 ? forcing_value : 0.);
pf[left] = dirichlet(case_mode >= 5 ? forcing_value : 0.);
p[right] = dirichlet(0.);
pf[right] = dirichlet(0.);

event properties (i++) {
  foreach_face()
    muv.x[] = dyn_visc*fm.x[];
  boundary ((scalar *){muv});
}

static void compute_plane_metrics (double *mean_u, double *flow, double *area,
                                   double *center_u, double *wall_u,
                                   double *inlet_flow, double *outlet_flow) {
  double xs = sample_x_location();
  double sumu = 0., suma = 0., wu = 0.;
  double fin = 0., fout = 0.;
  double xin = (case_mode >= 5 ? x_origin_nozzle + 0.5*Dhrect : xs);
  double xout = (case_mode >= 5 ? x_origin_nozzle + plenum_Dh*Dhrect + contraction_Dh*Dhrect + straight_Dh*Dhrect - 0.5*Dhrect : xs);
  foreach(reduction(+:sumu) reduction(+:suma)
          reduction(max:wu) reduction(+:fin) reduction(+:fout)) {
    if (cs[] > 1e-8) {
      double wx = width_at_x(x);
      double hx = height_at_x(x);
      double wall_dist = min(wx/2. - fabs(y), hx/2. - fabs(z));
      if (wall_dist < 1.5*Delta)
        wu = max(wu, fabs(u.x[]));
      double dxs = fabs(x - xs);
      if (dxs <= 0.75*Delta) {
        double aw = cs[]*sq(Delta);
        sumu += u.x[]*aw;
        suma += aw;
      }
      if (fabs(x - xin) <= 0.75*Delta)
        fin += u.x[]*cs[]*sq(Delta);
      if (fabs(x - xout) <= 0.75*Delta)
        fout += u.x[]*cs[]*sq(Delta);
    }
  }
  *mean_u = suma > 0. ? sumu/suma : 0.;
  *flow = sumu;
  *area = suma;
  double cdist = HUGE, cu = 0.;
  foreach(serial) {
    if (cs[] > 1e-8 && fabs(x - xs) <= 0.75*Delta) {
      double d2 = sq(y) + sq(z) + sq(x - xs);
      if (d2 < cdist) {
        cdist = d2;
        cu = u.x[];
      }
    }
  }
  *center_u = cu;
  *wall_u = wu;
  *inlet_flow = fin;
  *outlet_flow = fout;
}

static void write_outputs_now (const char *stop_reason) {
  if (wrote_outputs)
    return;
  wrote_outputs = 1;

  char path[1024];
  double mean_u = 0., flow = 0., area = 0., center_u = 0., wall_u = 0., fin = 0., fout = 0.;
  compute_plane_metrics(&mean_u, &flow, &area, &center_u, &wall_u, &fin, &fout);
  double imbalance = 0.;
  if (case_mode >= 5 && fabs(fout) > 1e-14)
    imbalance = fabs(fin - fout)/fabs(fout);

  output_path(path, sizeof(path), "nozzle_case_summary.csv");
  FILE *fp = fopen(path, "w");
  fprintf(fp, "case_id,case_mode,t,i,maxlevel,baselevel,forcing_value,target_u,mean_exit_velocity,flow_rate,sampled_area,geometric_area,centerline_velocity,max_wall_speed,inlet_flow,outlet_flow,mass_imbalance,width,height,hydraulic_diameter,straight_length_Dh,stop_reason\n");
  fprintf(fp, "%s,%d,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%s\n",
          case_id, case_mode, t, last_iter, maxlevel, baselevel, forcing_value, target_u, mean_u, flow, area, A0,
          center_u, wall_u, fin, fout, imbalance, Wrect, Hrect, Dhrect, straight_Dh, stop_reason);
  fclose(fp);

  output_path(path, sizeof(path), "profile_samples.csv");
  fp = fopen(path, "w");
  fprintf(fp, "case_id,t,x,y,z,ux,uy,uz,cs,area_weight,Delta,width,height,hydraulic_diameter\n");
  double xs = sample_x_location();
  foreach() {
    if (cs[] > 1e-8 && fabs(x - xs) <= 0.75*Delta) {
      fprintf(fp, "%s,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",
              case_id, t, x, y, z, u.x[], u.y[], u.z[], cs[], cs[]*sq(Delta), Delta, Wrect, Hrect, Dhrect);
    }
  }
  fclose(fp);

  output_path(path, sizeof(path), "transient_history.csv");
  fp = fopen(path, "a");
  fprintf(fp, "# stop_reason=%s final_t=%.12g final_i=%d final_mean_u=%.12g\n", stop_reason, t, last_iter, mean_u);
  fclose(fp);
}

int main (int argc, char ** argv) {
  if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
    print_usage(argv[0]);
    return 0;
  }

  A0 = pi*sq(official_r);
  D0 = 2.*official_r;
  Wrect = sqrt(2.*A0);
  Hrect = Wrect/2.;
  Prect = 2.*(Wrect + Hrect);
  Dhrect = 2.*Wrect*Hrect/(Wrect + Hrect);

  if (argc > 1) snprintf(case_id, sizeof(case_id), "%s", argv[1]);
  if (argc > 2) case_mode = atoi(argv[2]);
  if (argc > 3) maxlevel = atoi(argv[3]);
  if (argc > 4) forcing_value = atof(argv[4]);
  if (argc > 5) end_time = atof(argv[5]);
  if (argc > 6) straight_Dh = atof(argv[6]);
  if (argc > 7) snprintf(output_dir, sizeof(output_dir), "%s", argv[7]);

  if (case_mode == 0 || case_mode == 1) {
    Ldomain = 8.*Dhrect;
    x_origin_nozzle = -0.5*Ldomain;
  }
  else {
    Ldomain = (plenum_Dh + contraction_Dh + straight_Dh + 1.0)*Dhrect;
    x_origin_nozzle = 0.;
  }

  size(Ldomain);
  origin(x_origin_nozzle, -0.5*Ldomain, -0.5*Ldomain);
  if (case_mode == 0 || case_mode == 1)
    periodic(right);

  init_grid(1 << baselevel);
  mu = muv;
  stokes = true;
  DT = dt_cap;
  TOLERANCE = 1e-5;
  run();
}

event init (t = 0) {
  for (scalar s in {u, p, pf})
    s.third = true;

  double refine_band = (case_mode >= 5 ? plenum_scale*Wrect : Wrect);
  refine (fabs(y) < 0.65*refine_band && fabs(z) < 0.65*refine_band && level < maxlevel);
  build_geometry();

  foreach() {
    foreach_dimension()
      u.x[] = 0.;
    un[] = u.x[];
  }
  boundary ((scalar *){u, un});

  if (case_mode == 0 || case_mode == 1) {
    const face vector av[] = {forcing_value, 0., 0.};
    a = av;
  }

  char path[1024];
  output_path(path, sizeof(path), "transient_history.csv");
  FILE *fp = fopen(path, "w");
  fprintf(fp, "case_id,t,i,mean_exit_velocity,flow_rate,sampled_area,centerline_velocity,max_wall_speed,inlet_flow,outlet_flow,mass_imbalance,du\n");
  fclose(fp);
}

event logfile (i++) {
  last_iter = i;
  double mean_u = 0., flow = 0., area = 0., center_u = 0., wall_u = 0., fin = 0., fout = 0.;
  compute_plane_metrics(&mean_u, &flow, &area, &center_u, &wall_u, &fin, &fout);
  double imbalance = 0.;
  if (case_mode >= 5 && fabs(fout) > 1e-14)
    imbalance = fabs(fin - fout)/fabs(fout);
  double du = change (u.x, un);
  char path[1024];
  output_path(path, sizeof(path), "transient_history.csv");
  FILE *fp = fopen(path, "a");
  fprintf(fp, "%s,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g\n",
          case_id, t, i, mean_u, flow, area, center_u, wall_u, fin, fout, imbalance, du);
  fclose(fp);

  if (i > 20 && du < steady_tol && t > 0.05) {
    write_outputs_now("steady_change_below_tolerance");
    return 1;
  }
  if (i >= max_steps) {
    write_outputs_now("max_steps_reached");
    return 1;
  }
}

event end (t = end_time) {
  write_outputs_now("end_time_reached");
}
