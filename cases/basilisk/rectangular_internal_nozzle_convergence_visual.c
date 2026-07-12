#include "grid/octree.h"
#include "embed.h"
#include "navier-stokes/centered.h"
#define mu(f) (1./(clamp(f,0.,1.)*(1./mu1 - 1./mu2) + 1./mu2))
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"
#include <ctype.h>
#include <errno.h>
#include <sys/stat.h>
#include <string.h>

/*
 * Restartable native-VOF visual/checkpoint pipeline for the pressure-driven
 * W2 rectangular internal-nozzle case.
 *
 * This source preserves the calibrated pressure-driven injection geometry,
 * embedded-wall treatment, phase properties, zero perturbation baseline, and
 * raw station/interface export schema from rectangular_internal_nozzle_raw_export.c.
 * It adds checkpoint dumps, native Basilisk VOF frames, true output_facets()
 * surface files, and deterministic manifests for bounded smoke/restart review.
 *
 * In quarter mode, bottom (y = 0) and back (z = 0) are reflection planes:
 * normal velocity is zero and tangential velocity, pressure, and volume
 * fraction have zero normal derivative.  These are not periodic boundaries.
 * Quarter-domain facets may be mirrored only for render/diagnostic use; the
 * four copies are not independent full-domain physics.
 */

scalar un[];

int maxlevel = 6;
int baselevel = 4;
int case_mode = 2;
int max_steps = 8000;
int last_iter = 0;
int wrote_summary = 0;
int stable_flag = 1;
int domain_quarter = 0;
int enable_raw_export = 1;
int enable_native_frames = 1;
int enable_facet_export = 1;
int auto_restore = 0;
int restore_requested = 0;
int restored_ok = 0;
int visual_frame_index = 0;
int raw_frame_index = 0;
int checkpoint_index = 0;
int surface_frame_index = 0;

double official_r = 1./12.;
double A0, D0, Wrect, Hrect, Dhrect;
double pressure_value = 351.48;
double base_pressure_value = 351.48;
double perturb_amp = 0.;
double perturb_period = 0.03;
double target_u = 1.0;
double end_time = 0.18;
double diagnostic_dt = 0.03;
double visual_dt = 0.005;
double checkpoint_dt = 0.03;
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
double interface_threshold = 1e-6;
double credible_volume_threshold = 1e-6;
double station_half_dh = 0.15;
double transverse_scale = 0.75;
double restore_time = -1.;

char case_id[128] = "W2_visual_pipeline";
char output_dir[512] = ".";
char restore_path[512] = "";
char restored_from[512] = "";
char camera_preset[64] = "science_iso";
char frames_dir[640] = "";
char surfaces_dir[640] = "";
char checkpoints_dir[640] = "";
char sanitized_case_id[128] = "W2_visual_pipeline";

double max_active_front = 0.;
double max_interface_proxy = 0.;
double initial_interface_proxy = 0.;
double max_interface_growth = 0.;
int max_post_tag_count = 0;
int max_detached_proxy_count = 0;
int max_one_cell_debris_count = 0;
double final_mean_exit_velocity = 0.;
double final_exit_flow = 0.;
double final_exit_area = 0.;
double final_liquid_volume = 0.;
double initial_liquid_volume = -1.;
double final_liquid_volume_error = 0.;
double max_symmetry_leakage = 0.;

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
  if (domain_quarter)
    return min(w/2. - yp, h/2. - zp);
  return min(w/2. - fabs(yp), h/2. - fabs(zp));
}

static double geometry_phi (double xp, double yp, double zp) {
  if (xp <= exit_x())
    return internal_phi(xp, yp, zp);
  return 1.;
}

static double initial_liquid_phi (double xp, double yp, double zp) {
  return min(internal_phi(xp, yp, zp), exit_x() - xp);
}

static const char * domain_label (void) {
  return domain_quarter ? "quarter" : "full";
}

static void copy_string (char *dst, size_t n, const char *src) {
  if (n == 0)
    return;
  snprintf(dst, n, "%s", src ? src : "");
}

static void sanitize_case_id (void) {
  size_t j = 0;
  for (size_t k = 0; case_id[k] != '\0' && j + 1 < sizeof(sanitized_case_id); k++) {
    unsigned char ch = (unsigned char) case_id[k];
    sanitized_case_id[j++] = (isalnum(ch) || ch == '_' || ch == '-') ? ch : '_';
  }
  sanitized_case_id[j] = '\0';
  if (!sanitized_case_id[0])
    copy_string(sanitized_case_id, sizeof(sanitized_case_id), "case");
}

static void output_path (char *buf, int n, const char *leaf) {
  snprintf(buf, n, "%s/%s", output_dir, leaf);
}

static void subdir_path (char *buf, int n, const char *dir, const char *leaf) {
  snprintf(buf, n, "%s/%s", dir, leaf);
}

static int file_exists_nonzero (const char *path) {
  struct stat st;
  return stat(path, &st) == 0 && st.st_size > 0;
}

static void ensure_dir (const char *path) {
  if (mkdir(path, 0775) != 0 && errno != EEXIST) {
    fprintf(stderr, "ERROR cannot create directory %s: %s\n", path, strerror(errno));
    exit(2);
  }
}

static void ensure_output_dirs (void) {
  sanitize_case_id();
  snprintf(frames_dir, sizeof(frames_dir), "%s/native_frames", output_dir);
  snprintf(surfaces_dir, sizeof(surfaces_dir), "%s/vof_surfaces", output_dir);
  snprintf(checkpoints_dir, sizeof(checkpoints_dir), "%s/checkpoints", output_dir);
  ensure_dir(output_dir);
  ensure_dir(frames_dir);
  ensure_dir(surfaces_dir);
  ensure_dir(checkpoints_dir);
}

static void write_header_if_missing (const char *path, const char *header) {
  if (file_exists_nonzero(path))
    return;
  FILE *fp = fopen(path, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot open %s: %s\n", path, strerror(errno));
    exit(2);
  }
  fputs(header, fp);
  fclose(fp);
}

static void atomic_rename (const char *tmp, const char *dst) {
  if (rename(tmp, dst) != 0) {
    fprintf(stderr, "ERROR cannot rename %s to %s: %s\n", tmp, dst, strerror(errno));
    exit(2);
  }
}

static int max_frame_from_csv (const char *path, int field_index) {
  FILE *fp = fopen(path, "r");
  if (!fp)
    return -1;
  char line[4096];
  int max_index = -1;
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return -1;
  }
  while (fgets(line, sizeof(line), fp)) {
    int field = 0;
    char *p = line;
    while (field < field_index && *p) {
      if (*p == ',')
        field++;
      p++;
    }
    if (field == field_index) {
      int v = atoi(p);
      if (v > max_index)
        max_index = v;
    }
  }
  fclose(fp);
  return max_index;
}

static int discover_latest_checkpoint (char *dst, int n) {
  char path[1024];
  output_path(path, sizeof(path), "checkpoint_index.csv");
  FILE *fp = fopen(path, "r");
  if (!fp)
    return 0;
  char line[2048], last_file[512] = "";
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return 0;
  }
  while (fgets(line, sizeof(line), fp)) {
    char ccase[128], mode[32], file[512], parent[512];
    int idx = 0, iter_value = 0, level_value = 0;
    double tt = 0.;
    if (sscanf(line, "%127[^,],%31[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
               ccase, mode, &idx, &tt, &iter_value, &level_value, file, parent) >= 7)
      copy_string(last_file, sizeof(last_file), file);
  }
  fclose(fp);
  if (!last_file[0])
    return 0;
  if (file_exists_nonzero(last_file)) {
    copy_string(dst, n, last_file);
    return 1;
  }
  return 0;
}

static double checkpoint_time_from_index (const char *checkpoint) {
  char path[1024];
  output_path(path, sizeof(path), "checkpoint_index.csv");
  FILE *fp = fopen(path, "r");
  if (!fp)
    return -1.;
  char line[4096];
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return -1.;
  }
  double found = -1.;
  while (fgets(line, sizeof(line), fp)) {
    char ccase[128], mode[32], file[512], parent[512];
    int idx = 0, iter_value = 0, level_value = 0;
    double tt = 0.;
    if (sscanf(line, "%127[^,],%31[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
               ccase, mode, &idx, &tt, &iter_value, &level_value, file, parent) >= 7 &&
        !strcmp(file, checkpoint))
      found = tt;
  }
  fclose(fp);
  return found;
}

static void recover_metrics_from_existing_raw (void) {
  char path[1024];
  output_path(path, sizeof(path), "raw_frame_summary.csv");
  FILE *fp = fopen(path, "r");
  if (!fp)
    return;
  char line[4096];
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return;
  }
  int seen = 0;
  while (fgets(line, sizeof(line), fp)) {
    char ccase[128];
    int frame = 0, iter_value = 0, nt = 0, nd = 0, debris = 0;
    double tt = 0., mean_u = 0., flow = 0., area = 0., ps = 0., lv = 0., lverr = 0.;
    double af = 0., afdh = 0., ip = 0., growth = 0.;
    if (sscanf(line,
               "%127[^,],%lf,%d,%d,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%d,%d,%d",
               ccase, &tt, &frame, &iter_value, &mean_u, &flow, &area, &ps,
               &lv, &lverr, &af, &afdh, &ip, &growth, &nt, &nd, &debris) == 17) {
      if (!seen) {
        initial_liquid_volume = lv;
        initial_interface_proxy = ip > 0. ? ip : initial_interface_proxy;
        seen = 1;
      }
      final_mean_exit_velocity = mean_u;
      final_exit_flow = flow;
      final_exit_area = area;
      final_liquid_volume = lv;
      final_liquid_volume_error = lverr;
      max_active_front = max(max_active_front, af);
      max_interface_proxy = max(max_interface_proxy, ip);
      max_interface_growth = max(max_interface_growth, growth);
      max_post_tag_count = max(max_post_tag_count, nt);
      max_detached_proxy_count = max(max_detached_proxy_count, nd);
      max_one_cell_debris_count = max(max_one_cell_debris_count, debris);
    }
  }
  fclose(fp);
}

static void recover_indices_for_restore (void) {
  char path[1024];
  output_path(path, sizeof(path), "raw_frame_summary.csv");
  int raw_max = max_frame_from_csv(path, 2);
  raw_frame_index = raw_max >= 0 ? raw_max + 1 : 0;
  output_path(path, sizeof(path), "visual_frame_manifest.csv");
  int visual_max = max_frame_from_csv(path, 2);
  visual_frame_index = visual_max >= 0 ? visual_max + 1 : 0;
  output_path(path, sizeof(path), "surface_manifest.csv");
  int surface_max = max_frame_from_csv(path, 2);
  surface_frame_index = surface_max >= 0 ? surface_max + 1 : 0;
  output_path(path, sizeof(path), "checkpoint_index.csv");
  int checkpoint_max = max_frame_from_csv(path, 2);
  checkpoint_index = checkpoint_max >= 0 ? checkpoint_max + 1 : 0;
}

static void print_usage (const char *prog) {
  fprintf(stdout,
          "usage: %s [options]\n"
          "\n"
          "Restartable native-VOF/checkpoint/facet pipeline for the pressure-driven W2 internal-nozzle case.\n"
          "\n"
          "Required smoke-style example:\n"
          "  %s --case-id smoke_full --domain full --maxlevel 5 --pressure 351.48 --end-time 0.015 --external-dh 3.0 --output-dir OUTPUT --diagnostic-dt 0.005 --visual-dt 0.005 --checkpoint-dt 0.005 --raw-export 1 --native-frames 1 --facet-export 1 --max-steps 1000\n"
          "\n"
          "Options:\n"
          "  --case-id STR              case identifier used in manifests and filenames\n"
          "  --domain full|quarter      full-domain or quarter-domain mode\n"
          "  --case-mode INT            numeric mode tag for compatibility metadata\n"
          "  --maxlevel INT             adaptive maximum level\n"
          "  --baselevel INT            base grid level\n"
          "  --pressure FLOAT           pressure forcing, default 351.48\n"
          "  --end-time FLOAT           final simulation time\n"
          "  --external-dh FLOAT        external domain length in Dh\n"
          "  --output-dir PATH          output directory, created if needed\n"
          "  --diagnostic-dt FLOAT      raw diagnostic cadence\n"
          "  --visual-dt FLOAT          native frame/facet cadence\n"
          "  --checkpoint-dt FLOAT      checkpoint cadence\n"
          "  --raw-export 0|1           enable raw station/interface CSV export\n"
          "  --native-frames 0|1        enable native Basilisk VOF PPM frames\n"
          "  --facet-export 0|1         enable true Basilisk output_facets export\n"
          "  --restore PATH             restore from a specific checkpoint dump\n"
          "  --auto-restore 0|1         restore latest checkpoint from checkpoint_index.csv\n"
          "  --max-steps INT            hard step cap\n"
          "  --camera STR               science_iso, side, or top metadata/camera preset\n"
          "  --dt-cap FLOAT             maximum Basilisk timestep\n"
          "  --station-half-dh FLOAT    raw station slab half-thickness in Dh\n"
          "  --transverse-scale FLOAT   raw export transverse filter scale\n"
          "  --perturb-amp FLOAT        pressure perturbation amplitude, default zero\n"
          "  --perturb-period FLOAT     pressure perturbation period\n"
          "\n"
          "The source preserves pressure-driven injection and does not impose an exit velocity.\n",
          prog, prog);
}

static int parse_bool_arg (const char *s) {
  if (!strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "yes") || !strcmp(s, "on"))
    return 1;
  if (!strcmp(s, "0") || !strcmp(s, "false") || !strcmp(s, "no") || !strcmp(s, "off"))
    return 0;
  fprintf(stderr, "ERROR expected boolean 0|1, got %s\n", s);
  exit(2);
}

static const char * require_value (int argc, char **argv, int *i) {
  if (*i + 1 >= argc) {
    fprintf(stderr, "ERROR missing value after %s\n", argv[*i]);
    exit(2);
  }
  (*i)++;
  return argv[*i];
}

static void parse_args (int argc, char **argv) {
  for (int a = 1; a < argc; a++) {
    if (!strcmp(argv[a], "--help") || !strcmp(argv[a], "-h")) {
      print_usage(argv[0]);
      exit(0);
    }
    else if (!strcmp(argv[a], "--case-id"))
      copy_string(case_id, sizeof(case_id), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--domain")) {
      const char *v = require_value(argc, argv, &a);
      if (!strcmp(v, "full"))
        domain_quarter = 0;
      else if (!strcmp(v, "quarter"))
        domain_quarter = 1;
      else {
        fprintf(stderr, "ERROR unknown domain %s\n", v);
        exit(2);
      }
    }
    else if (!strcmp(argv[a], "--case-mode"))
      case_mode = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--maxlevel"))
      maxlevel = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--baselevel"))
      baselevel = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--pressure"))
      pressure_value = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--end-time"))
      end_time = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--external-dh"))
      external_Dh = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--output-dir"))
      copy_string(output_dir, sizeof(output_dir), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--diagnostic-dt"))
      diagnostic_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--visual-dt"))
      visual_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--checkpoint-dt"))
      checkpoint_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--raw-export"))
      enable_raw_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--native-frames"))
      enable_native_frames = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--facet-export"))
      enable_facet_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--restore")) {
      copy_string(restore_path, sizeof(restore_path), require_value(argc, argv, &a));
      restore_requested = 1;
    }
    else if (!strcmp(argv[a], "--auto-restore"))
      auto_restore = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--max-steps"))
      max_steps = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--camera"))
      copy_string(camera_preset, sizeof(camera_preset), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--dt-cap"))
      dt_cap = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--station-half-dh"))
      station_half_dh = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--transverse-scale"))
      transverse_scale = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--perturb-amp"))
      perturb_amp = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--perturb-period"))
      perturb_period = atof(require_value(argc, argv, &a));
    else {
      fprintf(stderr, "ERROR unknown option %s\n", argv[a]);
      print_usage(argv[0]);
      exit(2);
    }
  }
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

u.n[bottom] = domain_quarter ? dirichlet(0.) : neumann(0.);
u.t[bottom] = neumann(0.);
u.r[bottom] = neumann(0.);
p[bottom] = neumann(0.);
pf[bottom] = neumann(0.);
f[bottom] = neumann(0.);

u.n[back] = domain_quarter ? dirichlet(0.) : neumann(0.);
u.t[back] = neumann(0.);
u.r[back] = neumann(0.);
p[back] = neumann(0.);
pf[back] = neumann(0.);
f[back] = neumann(0.);

/* The opposite transverse faces are far-field zero-gradient boundaries.  In
   full mode bottom/back use the same far-field treatment; in quarter mode
   they are replaced by the reflection conditions above.  Do not replace the
   reflection planes with periodic() calls: opposite radial faces are not a
   translationally repeating unit cell. */
u.n[top] = neumann(0.);
u.t[top] = neumann(0.);
u.r[top] = neumann(0.);
p[top] = neumann(0.);
pf[top] = neumann(0.);
f[top] = neumann(0.);

u.n[front] = neumann(0.);
u.t[front] = neumann(0.);
u.r[front] = neumann(0.);
p[front] = neumann(0.);
pf[front] = neumann(0.);
f[front] = neumann(0.);

static int in_refine_band (double xp, double yp, double zp) {
  double refine_band = plenum_scale*Wrect;
  if (xp > exit_x() + external_Dh*Dhrect)
    return 0;
  if (domain_quarter)
    return yp < 0.75*refine_band && zp < 0.75*refine_band;
  return fabs(yp) < 0.75*refine_band && fabs(zp) < 0.75*refine_band;
}

static int region_flag (double xp) {
  double xe = exit_x();
  if (xp < xe - 0.5*Dhrect)
    return 0;
  if (xp <= xe + 0.5*Dhrect)
    return 2;
  return 1;
}

static int interface_flag_value (double ff) {
  return ff > interface_threshold && ff < 1. - interface_threshold;
}

static double symmetry_leakage_now (void) {
  if (!domain_quarter)
    return 0.;
  /* Measure the actual reflection parity residual using the boundary ghost
     values. Sampling |u_normal| at the first interior cell is not a boundary
     leakage measure: an odd normal-velocity field can be nonzero away from
     the plane while still satisfying u_normal = 0 exactly on it. */
  boundary ({u});
  double leak = 0.;
  foreach_boundary(bottom, reduction(max:leak)) {
    if (cs[] > 1e-8) {
      leak = max(leak, fabs(u.y[] + u.y[0,-1,0]));
      leak = max(leak, fabs(u.x[] - u.x[0,-1,0]));
      leak = max(leak, fabs(u.z[] - u.z[0,-1,0]));
    }
  }
  foreach_boundary(back, reduction(max:leak)) {
    if (cs[] > 1e-8) {
      leak = max(leak, fabs(u.z[] + u.z[0,0,-1]));
      leak = max(leak, fabs(u.x[] - u.x[0,0,-1]));
      leak = max(leak, fabs(u.y[] - u.y[0,0,-1]));
    }
  }
  return leak;
}

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
      double wall_dist = domain_quarter ? min(wx/2. - y, hx/2. - z) : min(wx/2. - fabs(y), hx/2. - fabs(z));
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

static int interface_facet_cell_count (void) {
  int count = 0;
  foreach(reduction(+:count))
    if (cs[] > 1e-8 && f[] > 1e-6 && f[] < 1. - 1e-6)
      count++;
  return count;
}

static double active_front_now (void) {
  double af = 0.;
  double xe = exit_x();
  foreach(reduction(max:af))
    if (cs[] > 1e-8 && f[] > liquid_threshold && x > xe)
      af = max(af, x - xe);
  return af;
}

static void update_metrics (double *mean_u, double *flow, double *area, double *ps,
                            double *lv, double *af, double *ip, double *growth) {
  compute_exit_metrics(mean_u, flow, area, ps);
  final_mean_exit_velocity = *mean_u;
  final_exit_flow = *flow;
  final_exit_area = *area;
  *lv = liquid_volume_total();
  if (initial_liquid_volume < 0.)
    initial_liquid_volume = *lv;
  final_liquid_volume = *lv;
  final_liquid_volume_error = initial_liquid_volume > 0. ? fabs(*lv - initial_liquid_volume)/initial_liquid_volume : 0.;
  *af = active_front_now();
  *ip = interface_proxy_now();
  if (initial_interface_proxy <= 0. && *ip > 0.)
    initial_interface_proxy = *ip;
  *growth = initial_interface_proxy > 0. ? *ip/initial_interface_proxy : 1.;
  max_active_front = max(max_active_front, *af);
  max_interface_proxy = max(max_interface_proxy, *ip);
  max_interface_growth = max(max_interface_growth, *growth);
  max_symmetry_leakage = max(max_symmetry_leakage, symmetry_leakage_now());
}

static void write_profile_samples (FILE *fp) {
  double xs = exit_x() - 0.5*Dhrect;
  foreach(serial) {
    if (cs[] > 1e-8 && fabs(x - xs) <= 0.75*Delta) {
      fprintf(fp, "%s,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%d\n",
              case_id, t, raw_frame_index, x, y, z, f[], u.x[], u.y[], u.z[], p[], cs[],
              cs[]*sq(Delta), dv(), level, Delta, Wrect, Hrect, Dhrect, region_flag(x));
    }
  }
}

static void write_station_slab (FILE *fp, int station_id, double xi) {
  double xe = exit_x();
  double xp = xe + xi*Dhrect;
  double transverse = transverse_scale*plenum_scale*Wrect;
  foreach(serial) {
    int transverse_ok = domain_quarter ? (y <= transverse && z <= transverse) : (fabs(y) <= transverse && fabs(z) <= transverse);
    if (cs[] > 1e-8 && transverse_ok) {
      double slab_half = max(station_half_dh*Dhrect, 0.75*Delta);
      if (fabs(x - xp) <= slab_half) {
        fprintf(fp, "%s,%.12g,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%d,%d\n",
                case_id, t, raw_frame_index, station_id, xi, x - xe, x, y, z, f[], u.x[], u.y[], u.z[],
                p[], cs[], level, Delta, dv(), region_flag(x), interface_flag_value(f[]));
      }
    }
  }
}

static void write_station_slab_cells (FILE *fp, double active_front) {
  const double fixed_xi[] = {0.10, 0.20, 0.30, 0.40, 0.50, 0.75, 1.00};
  for (int s = 0; s < 7; s++)
    write_station_slab(fp, s, fixed_xi[s]);
  if (active_front > 0.25*Dhrect) {
    double af_xi = active_front/Dhrect;
    const double front_relative_xi[] = {0.25, 0.50, 0.75, 0.90};
    for (int s = 0; s < 4; s++)
      write_station_slab(fp, 90 + s, front_relative_xi[s]*af_xi);
  }
}

static void write_interface_cloud (FILE *fp) {
  double xe = exit_x();
  foreach(serial) {
    if (cs[] > 1e-8 && x >= xe - 0.5*Dhrect && x <= xe + external_Dh*Dhrect &&
        interface_flag_value(f[])) {
      fprintf(fp, "%s,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%d\n",
              case_id, t, raw_frame_index, x - xe, x, y, z, f[], u.x[], u.y[], u.z[], p[],
              cs[], level, Delta, dv(), region_flag(x));
    }
  }
}

static void write_reduced_cross_sections (FILE *fp) {
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
    fprintf(fp, "%s,%.12g,%d,%d,%.12g,%d,%.12g,%.12g,%.12g,%d,%d\n",
            case_id, t, j, n, vol[j], cells[j], cx - xe, cy, cz, credible, region_flag(cx));
  }
}

static void rewrite_visual_manifest (void) {
  char csv[1024], manifest[1024], tmp[1024];
  output_path(csv, sizeof(csv), "visual_frame_manifest.csv");
  output_path(manifest, sizeof(manifest), "visual_frame_manifest.json");
  output_path(tmp, sizeof(tmp), "visual_frame_manifest.json.tmp");
  FILE *in = fopen(csv, "r");
  FILE *out = fopen(tmp, "w");
  if (!out) {
    fprintf(stderr, "ERROR cannot write %s\n", tmp);
    exit(2);
  }
  fprintf(out,
          "{\n"
          "  \"case_id\": \"%s\",\n"
          "  \"domain_mode\": \"%s\",\n"
          "  \"pressure_driven_preserved\": true,\n"
          "  \"exit_velocity_imposed\": false,\n"
          "  \"native_frame_output_ready\": true,\n"
          "  \"coordinate_convention\": \"x_streamwise_y_width_z_height_origin_nozzle_inlet\",\n"
          "  \"nozzle_exit_x\": %.12g,\n"
          "  \"Dh\": %.12g,\n"
          "  \"frames\": [\n",
          case_id, domain_label(), exit_x(), Dhrect);
  int count = 0;
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], mode[32], filename[512], format[32], camera[64], marker[128];
      int idx = 0, iter_value = 0, level_value = 0;
      double tt = 0., xe = 0., dh = 0., pressure = 0.;
      if (sscanf(line, "%127[^,],%31[^,],%d,%lf,%d,%511[^,],%31[^,],%63[^,],%127[^,],%lf,%lf,%lf,%d",
                 ccase, mode, &idx, &tt, &iter_value, filename, format, camera, marker,
                 &xe, &dh, &pressure, &level_value) == 13) {
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"frame_index\": %d, \"time\": %.12g, \"iteration\": %d, \"filename\": \"%s\", \"format\": \"%s\", \"camera\": \"%s\", \"exit_marker\": \"%s\", \"nozzle_exit_x\": %.12g, \"Dh\": %.12g, \"pressure\": %.12g, \"maxlevel\": %d}",
                idx, tt, iter_value, filename, format, camera, marker, xe, dh, pressure, level_value);
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"frame_count\": %d\n}\n", count);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void rewrite_surface_manifest (void) {
  char csv[1024], manifest[1024], tmp[1024];
  output_path(csv, sizeof(csv), "surface_manifest.csv");
  output_path(manifest, sizeof(manifest), "surface_manifest.json");
  output_path(tmp, sizeof(tmp), "surface_manifest.json.tmp");
  FILE *in = fopen(csv, "r");
  FILE *out = fopen(tmp, "w");
  if (!out) {
    fprintf(stderr, "ERROR cannot write %s\n", tmp);
    exit(2);
  }
  fprintf(out,
          "{\n"
          "  \"case_id\": \"%s\",\n"
          "  \"surface_export_ready\": %s,\n"
          "  \"surface_export_method\": \"Basilisk output_facets(f)\",\n"
          "  \"coordinate_convention\": \"x_streamwise_y_width_z_height_origin_nozzle_inlet\",\n"
          "  \"topology_cleanup_operations\": \"none\",\n"
          "  \"surfaces\": [\n",
          case_id, enable_facet_export ? "true" : "false");
  int count = 0;
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], mode[32], filename[512], source_frame[64];
      int idx = 0, iter_value = 0, level_value = 0, facet_cells = 0;
      double tt = 0., xe = 0., dh = 0.;
      if (sscanf(line, "%127[^,],%31[^,],%d,%lf,%d,%511[^,],%d,%lf,%lf,%d,%63[^\n]",
                 ccase, mode, &idx, &tt, &iter_value, filename, &facet_cells,
                 &xe, &dh, &level_value, source_frame) == 11) {
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"surface_index\": %d, \"time\": %.12g, \"iteration\": %d, \"filename\": \"%s\", \"facet_cell_count\": %d, \"nozzle_exit_x\": %.12g, \"Dh\": %.12g, \"domain_mode\": \"%s\", \"maxlevel\": %d, \"source_frame_id\": \"%s\"}",
                idx, tt, iter_value, filename, facet_cells, xe, dh, mode, level_value, source_frame);
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"surface_count\": %d\n}\n", count);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void rewrite_checkpoint_manifest (void) {
  char csv[1024], manifest[1024], tmp[1024];
  output_path(csv, sizeof(csv), "checkpoint_index.csv");
  output_path(manifest, sizeof(manifest), "checkpoint_manifest.json");
  output_path(tmp, sizeof(tmp), "checkpoint_manifest.json.tmp");
  FILE *in = fopen(csv, "r");
  FILE *out = fopen(tmp, "w");
  if (!out) {
    fprintf(stderr, "ERROR cannot write %s\n", tmp);
    exit(2);
  }
  fprintf(out,
          "{\n"
          "  \"case_id\": \"%s\",\n"
          "  \"checkpoint_restore_supported\": true,\n"
          "  \"latest_valid_checkpoint\": null,\n"
          "  \"provenance_chain\": [\n",
          case_id);
  int count = 0;
  char latest[512] = "";
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], mode[32], filename[512], parent[512];
      int idx = 0, iter_value = 0, level_value = 0;
      double tt = 0.;
      if (sscanf(line, "%127[^,],%31[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
                 ccase, mode, &idx, &tt, &iter_value, &level_value, filename, parent) >= 7) {
        copy_string(latest, sizeof(latest), filename);
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"checkpoint_index\": %d, \"time\": %.12g, \"iteration\": %d, \"maxlevel\": %d, \"domain_mode\": \"%s\", \"filename\": \"%s\", \"parent_checkpoint\": \"%s\", \"verified_nonzero\": %s}",
                idx, tt, iter_value, level_value, mode, filename, parent, file_exists_nonzero(filename) ? "true" : "false");
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"checkpoint_count\": %d,\n  \"latest_checkpoint_file\": \"%s\"\n}\n", count, latest);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void initialize_output_files (void) {
  char path[1024];
  output_path(path, sizeof(path), "raw_frame_summary.csv");
  write_header_if_missing(path, "case_id,t,frame_index,i,mean_exit_velocity,exit_flow,exit_liquid_area,profile_sanity,liquid_volume,liquid_volume_error,active_front,active_front_Dh,interface_proxy,interface_growth,post_tag_count,detached_proxy_count,one_cell_debris_count\n");
  output_path(path, sizeof(path), "raw_component_summary.csv");
  write_header_if_missing(path, "case_id,t,component_id,tag_count,volume,cells,centroid_x_from_exit,centroid_y,centroid_z,credible,region_flag\n");
  output_path(path, sizeof(path), "raw_reduced_cross_section_metrics.csv");
  write_header_if_missing(path, "case_id,t,station_id,x_from_exit,area_proxy,width,thickness,aspect_ratio,centroid_y,centroid_z,cov_yz,warp_proxy,Dh\n");
  output_path(path, sizeof(path), "raw_profile_exit_cells.csv");
  write_header_if_missing(path, "case_id,t,frame_index,x,y,z,f,ux,uy,uz,p,cs,area_weight,cell_volume_proxy,level,Delta,width,height,Dh,region_flag\n");
  output_path(path, sizeof(path), "raw_station_cells.csv");
  write_header_if_missing(path, "case_id,t,frame_index,station_id,xi,x_from_exit,x,y,z,f,ux,uy,uz,p,cs,level,Delta,cell_volume_proxy,region_flag,interface_flag\n");
  output_path(path, sizeof(path), "raw_interface_cells.csv");
  write_header_if_missing(path, "case_id,t,frame_index,x_from_exit,x,y,z,f,ux,uy,uz,p,cs,level,Delta,cell_volume_proxy,region_flag\n");
  output_path(path, sizeof(path), "visual_frame_manifest.csv");
  write_header_if_missing(path, "case_id,domain_mode,frame_index,t,i,filename,format,camera,exit_marker,nozzle_exit_x,Dh,pressure,maxlevel\n");
  output_path(path, sizeof(path), "surface_manifest.csv");
  write_header_if_missing(path, "case_id,domain_mode,surface_index,t,i,filename,facet_cell_count,nozzle_exit_x,Dh,maxlevel,source_frame_id\n");
  output_path(path, sizeof(path), "checkpoint_index.csv");
  write_header_if_missing(path, "case_id,domain_mode,checkpoint_index,t,i,maxlevel,filename,parent_checkpoint\n");
  rewrite_visual_manifest();
  rewrite_surface_manifest();
  rewrite_checkpoint_manifest();
}

static void write_native_frame (int iter_value) {
  char leaf[256], path[1024], rel[768];
  snprintf(leaf, sizeof(leaf), "native_vof_%04d.ppm", visual_frame_index);
  subdir_path(path, sizeof(path), frames_dir, leaf);
  snprintf(rel, sizeof(rel), "native_frames/%s", leaf);

  clear();
  if (!strcmp(camera_preset, "side"))
    view(width = 1280, height = 720, fov = 16.0, tx = -0.22, ty = 0.0, bg = {1,1,1});
  else if (!strcmp(camera_preset, "top"))
    view(camera = "top", width = 1280, height = 720, fov = 18.0, tx = -0.20, ty = 0.0, bg = {1,1,1});
  else
    view(camera = "iso", width = 1280, height = 720, fov = 18.0, tx = -0.18, ty = 0.16, bg = {1,1,1});
  draw_vof("f");
  box(notics = true);
  char label[256];
  snprintf(label, sizeof(label), "%s t=%.5g frame=%04d exit_x=%.5g %s",
           case_id, t, visual_frame_index, exit_x(), domain_label());
  draw_string(label, pos = 1, size = 38);
  if (!save(path)) {
    fprintf(stderr, "ERROR native frame save failed: %s\n", path);
    stable_flag = 0;
    return;
  }

  char manifest_csv[1024];
  output_path(manifest_csv, sizeof(manifest_csv), "visual_frame_manifest.csv");
  FILE *fp = fopen(manifest_csv, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append %s\n", manifest_csv);
    exit(2);
  }
  fprintf(fp, "%s,%s,%d,%.12g,%d,%s,ppm,%s,nozzle_exit_text_overlay,%.12g,%.12g,%.12g,%d\n",
          case_id, domain_label(), visual_frame_index, t, iter_value, rel, camera_preset,
          exit_x(), Dhrect, pressure_value, maxlevel);
  fclose(fp);
  rewrite_visual_manifest();
  visual_frame_index++;
}

static void write_surface_facets (int iter_value) {
  char leaf[256], path[1024], rel[768], source_frame[64];
  snprintf(leaf, sizeof(leaf), "vof_facets_%04d.facets", surface_frame_index);
  subdir_path(path, sizeof(path), surfaces_dir, leaf);
  snprintf(rel, sizeof(rel), "vof_surfaces/%s", leaf);
  snprintf(source_frame, sizeof(source_frame), "visual_%04d", max(0, visual_frame_index - 1));
  int facet_cells = interface_facet_cell_count();

  FILE *fp = fopen(path, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot write %s\n", path);
    exit(2);
  }
  fprintf(fp, "# Basilisk output_facets(f)\n");
  fprintf(fp, "# case_id=%s\n# domain_mode=%s\n# time=%.12g\n# iteration=%d\n", case_id, domain_label(), t, iter_value);
  fprintf(fp, "# coordinate_convention=x_streamwise_y_width_z_height_origin_nozzle_inlet\n");
  fprintf(fp, "# nozzle_exit_x=%.12g\n# Dh=%.12g\n# source_frame_id=%s\n", exit_x(), Dhrect, source_frame);
  fprintf(fp, "# topology_cleanup_operations=none\n");
  output_facets(f, fp);
  fclose(fp);

  char manifest_csv[1024];
  output_path(manifest_csv, sizeof(manifest_csv), "surface_manifest.csv");
  FILE *mf = fopen(manifest_csv, "a");
  if (!mf) {
    fprintf(stderr, "ERROR cannot append %s\n", manifest_csv);
    exit(2);
  }
  fprintf(mf, "%s,%s,%d,%.12g,%d,%s,%d,%.12g,%.12g,%d,%s\n",
          case_id, domain_label(), surface_frame_index, t, iter_value, rel, facet_cells,
          exit_x(), Dhrect, maxlevel, source_frame);
  fclose(mf);
  rewrite_surface_manifest();
  surface_frame_index++;
}

static void write_checkpoint_dump (int iter_value) {
  char leaf[256], path[1024], parent[512] = "fresh";
  if (restored_ok && restored_from[0])
    copy_string(parent, sizeof(parent), restored_from);
  snprintf(leaf, sizeof(leaf), "%s_%s_t%09.6f_i%07d_l%d.dump",
           sanitized_case_id, domain_label(), t, iter_value, maxlevel);
  subdir_path(path, sizeof(path), checkpoints_dir, leaf);
  dump(file = path);
  if (!file_exists_nonzero(path)) {
    fprintf(stderr, "ERROR checkpoint dump is missing or empty: %s\n", path);
    stable_flag = 0;
    return;
  }
  char csv[1024];
  output_path(csv, sizeof(csv), "checkpoint_index.csv");
  FILE *fp = fopen(csv, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append %s\n", csv);
    exit(2);
  }
  fprintf(fp, "%s,%s,%d,%.12g,%d,%d,%s,%s\n",
          case_id, domain_label(), checkpoint_index, t, iter_value, maxlevel, path, parent);
  fclose(fp);
  rewrite_checkpoint_manifest();
  checkpoint_index++;
}

int main (int argc, char **argv) {
  parse_args(argc, argv);
  base_pressure_value = pressure_value;

  A0 = pi*sq(official_r);
  D0 = 2.*official_r;
  Wrect = sqrt(2.*A0);
  Hrect = Wrect/2.;
  Dhrect = 2.*Wrect*Hrect/(Wrect + Hrect);

  Ldomain = (plenum_Dh + contraction_Dh + straight_Dh + external_Dh)*Dhrect;
  x_origin_nozzle = 0.;
  size(Ldomain);
  if (domain_quarter)
    origin(x_origin_nozzle, 0., 0.);
  else
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

  ensure_output_dirs();
  if (auto_restore && !restore_requested && discover_latest_checkpoint(restore_path, sizeof(restore_path)))
    restore_requested = 1;
  initialize_output_files();
  run();
}

event init (t = 0) {
  for (scalar s in {u, p, pf})
    s.third = true;
  f.refine = f.prolongation = fraction_refine;

  if (restore_requested) {
    if (!restore(file = restore_path)) {
      fprintf(stderr, "ERROR restore failed for %s\n", restore_path);
      exit(2);
    }
    restored_ok = 1;
    copy_string(restored_from, sizeof(restored_from), restore_path);
    build_geometry();
    boundary({f, u, un});
    recover_indices_for_restore();
    recover_metrics_from_existing_raw();
    double indexed_time = checkpoint_time_from_index(restore_path);
    restore_time = indexed_time >= 0. ? indexed_time : t;
    fprintf(stderr, "restored checkpoint %s at t %.12g i %d next_visual %d next_raw %d next_surface %d next_checkpoint %d\n",
            restored_from, restore_time, i, visual_frame_index, raw_frame_index, surface_frame_index, checkpoint_index);
    return 0;
  }

  refine (in_refine_band(x, y, z) && level < maxlevel);
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
}

event pressure_update (i++) {
  if (perturb_amp != 0. && perturb_period > 0.)
    pressure_value = base_pressure_value*(1. + perturb_amp*sin(2.*pi*t/perturb_period));
  else
    pressure_value = base_pressure_value;
}

event diagnostics (t = 0.; t += diagnostic_dt; t <= end_time + 1e-12) {
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  last_iter = i;
  double mean_u = 0., flow = 0., area = 0., ps = 0., lv = 0., af = 0., ip = 0., growth = 1.;
  update_metrics(&mean_u, &flow, &area, &ps, &lv, &af, &ip, &growth);

  int nt = 0, nd = 0, debris = 0;
  char path[1024];
  output_path(path, sizeof(path), "raw_component_summary.csv");
  FILE *comp = fopen(path, "a");
  write_component_diagnostics(comp, &nt, &nd, &debris);
  fclose(comp);
  max_post_tag_count = max(max_post_tag_count, nt);
  max_detached_proxy_count = max(max_detached_proxy_count, nd);
  max_one_cell_debris_count = max(max_one_cell_debris_count, debris);

  output_path(path, sizeof(path), "raw_reduced_cross_section_metrics.csv");
  FILE *xs = fopen(path, "a");
  write_reduced_cross_sections(xs);
  fclose(xs);

  if (enable_raw_export) {
    output_path(path, sizeof(path), "raw_station_cells.csv");
    FILE *station = fopen(path, "a");
    write_station_slab_cells(station, af);
    fclose(station);

    output_path(path, sizeof(path), "raw_interface_cells.csv");
    FILE *iface = fopen(path, "a");
    write_interface_cloud(iface);
    fclose(iface);

    output_path(path, sizeof(path), "raw_profile_exit_cells.csv");
    FILE *prof = fopen(path, "a");
    write_profile_samples(prof);
    fclose(prof);
  }

  output_path(path, sizeof(path), "raw_frame_summary.csv");
  FILE *fp = fopen(path, "a");
  fprintf(fp, "%s,%.12g,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d\n",
          case_id, t, raw_frame_index, i, mean_u, flow, area, ps, lv, final_liquid_volume_error,
          af, Dhrect > 0. ? af/Dhrect : 0., ip, growth, nt, nd, debris);
  fclose(fp);
  raw_frame_index++;

  if (final_liquid_volume_error > 0.5)
    stable_flag = 0;
}

event native_frames (t = 0.; t += visual_dt; t <= end_time + 1e-12) {
  if (!enable_native_frames)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_native_frame(i);
}

event surface_facets (t = 0.; t += visual_dt; t <= end_time + 1e-12) {
  if (!enable_facet_export)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_surface_facets(i);
}

event checkpoint_dumps (t = checkpoint_dt; t += checkpoint_dt; t <= end_time + 1e-12) {
  if (checkpoint_dt <= 0.)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_checkpoint_dump(i);
}

event logfile (i++) {
  last_iter = i;
  double du = change(u.x, un);
  if (i >= max_steps) {
    stable_flag = 0;
    fprintf(stderr, "maximum step cap reached at i=%d t=%.12g\n", i, t);
    return 1;
  }
  if (du != du) {
    stable_flag = 0;
    fprintf(stderr, "nan velocity change at i=%d t=%.12g\n", i, t);
    return 1;
  }
}

event end (t = end_time) {
  if (wrote_summary)
    return 0;
  wrote_summary = 1;
  double mean_u = 0., flow = 0., area = 0., ps = 0., lv = 0., af = 0., ip = 0., growth = 1.;
  update_metrics(&mean_u, &flow, &area, &ps, &lv, &af, &ip, &growth);

  char path[1024];
  output_path(path, sizeof(path), "visual_pipeline_case_summary.csv");
  FILE *fp = fopen(path, "w");
  fprintf(fp, "case_id,domain_mode,case_mode,t,i,maxlevel,baselevel,pressure_value,base_pressure_value,perturb_amp,perturb_period,target_u,mean_exit_velocity,pressure_retuned,exit_flow,exit_liquid_area,liquid_volume,liquid_volume_error,max_active_front,max_active_front_Dh,max_interface_proxy,max_interface_growth,max_post_tag_count,max_detached_proxy_count,max_one_cell_debris_count,symmetry_leakage,width,height,Dh,area,external_Dh,diagnostic_dt,visual_dt,checkpoint_dt,raw_export,native_frames,facet_export,restored_from,stable_flag\n");
  fprintf(fp, "%s,%s,%d,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%s,%d\n",
          case_id, domain_label(), case_mode, t, last_iter, maxlevel, baselevel,
          pressure_value, base_pressure_value, perturb_amp, perturb_period, target_u,
          final_mean_exit_velocity, fabs(base_pressure_value - 2524.75) > 1e-6 || perturb_amp != 0.,
          final_exit_flow, final_exit_area, final_liquid_volume, final_liquid_volume_error,
          max_active_front, Dhrect > 0. ? max_active_front/Dhrect : 0.,
          max_interface_proxy, max_interface_growth, max_post_tag_count,
          max_detached_proxy_count, max_one_cell_debris_count, max_symmetry_leakage,
          Wrect, Hrect, Dhrect, A0, external_Dh, diagnostic_dt, visual_dt,
          checkpoint_dt, enable_raw_export, enable_native_frames, enable_facet_export,
          restored_from[0] ? restored_from : "fresh", stable_flag);
  fclose(fp);

  output_path(path, sizeof(path), "raw_export_manifest.json");
  fp = fopen(path, "w");
  fprintf(fp,
          "{\n"
          "  \"case_id\": \"%s\",\n"
          "  \"domain_mode\": \"%s\",\n"
          "  \"selected_case\": \"W2_longer_duration\",\n"
          "  \"pressure_driven_preserved\": true,\n"
          "  \"exit_velocity_imposed\": false,\n"
          "  \"transverse_periodic_boundaries\": false,\n"
          "  \"boundary_model\": \"%s\",\n"
          "  \"mirrored_quadrants_render_only\": %s,\n"
          "  \"maxlevel\": %d,\n"
          "  \"end_time\": %.12g,\n"
          "  \"diagnostic_dt\": %.12g,\n"
          "  \"visual_dt\": %.12g,\n"
          "  \"checkpoint_dt\": %.12g,\n"
          "  \"geometry\": {\"W\": %.12g, \"H\": %.12g, \"Dh\": %.12g, \"A0\": %.12g, \"nozzle_exit_x\": %.12g},\n"
          "  \"export_modes\": [\"station_slab_raw_export\", \"interface_cloud_export\", \"component_diagnostics_export\", \"profile_exit_export\", \"native_vof_frames\", \"output_facets_surfaces\", \"checkpoint_dumps\"],\n"
          "  \"files\": {\n"
          "    \"case_summary\": \"visual_pipeline_case_summary.csv\",\n"
          "    \"frame_summary\": \"raw_frame_summary.csv\",\n"
          "    \"station_cells\": \"raw_station_cells.csv\",\n"
          "    \"interface_cells\": \"raw_interface_cells.csv\",\n"
          "    \"component_summary\": \"raw_component_summary.csv\",\n"
          "    \"profile_exit_cells\": \"raw_profile_exit_cells.csv\",\n"
          "    \"reduced_cross_sections\": \"raw_reduced_cross_section_metrics.csv\",\n"
          "    \"visual_manifest\": \"visual_frame_manifest.json\",\n"
          "    \"surface_manifest\": \"surface_manifest.json\",\n"
          "    \"checkpoint_manifest\": \"checkpoint_manifest.json\"\n"
          "  },\n"
          "  \"claim_boundary\": \"internal restartable visual-output pipeline only; not validation or public media; fit_ready=false; public_ready=false\"\n"
          "}\n",
          case_id, domain_label(),
          domain_quarter ? "reflection_planes_y0_z0" : "full_domain_far_field",
          domain_quarter ? "true" : "false",
          maxlevel, t, diagnostic_dt, visual_dt, checkpoint_dt,
          Wrect, Hrect, Dhrect, A0, exit_x());
  fclose(fp);
}
