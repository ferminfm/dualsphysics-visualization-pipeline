#include "grid/octree.h"
#include "embed.h"
#ifdef INTERNAL_NOZZLE_PROJECTION_TRACE
# include "internal_nozzle_projection_trace.h"
#endif
#ifndef INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP
# error "compile through the hash-gated restartable centered-header preparation path"
#endif
#include "internal_nozzle_centered.h"
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
int enable_field_export = 1;
int enable_native_frames = 1;
int enable_facet_export = 1;
int auto_restore = 0;
int restore_requested = 0;
int restored_ok = 0;
int visual_frame_index = 0;
int raw_frame_index = 0;
int field_frame_index = 0;
int checkpoint_index = 0;
int surface_frame_index = 0;
int recovered_checkpoint_iteration = -1;

double official_r = 1./12.;
double A0, D0, Wrect, Hrect, Dhrect;
double pressure_value = 351.48;
double base_pressure_value = 351.48;
double perturb_amp = 0.;
double perturb_period = 0.03;
double target_u = 1.0;
double end_time = 0.18;
double diagnostic_dt = 0.03;
double field_dt = 0.03;
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
double next_field_export_time = 0.;
double schedule_tick_dt = 0.;
double schedule_time_tolerance = 1e-12;
int light_base_stride = 2;
int light_dense_stride = 1;
int field_base_stride = 8;
int field_dense_stride = 4;
int checkpoint_stride = 6;
int dense_start_tick = 24;
int dense_end_tick = 120;
int current_master_tick = -1;
double current_target_time = -1.;
double current_actual_time = -1.;

double cumulative_liquid_inflow = 0.;
double cumulative_liquid_outflow = 0.;
double previous_liquid_inflow_rate = 0.;
double previous_liquid_outflow_rate = 0.;
double last_mass_balance_time = -1.;
double liquid_inventory_change_fraction = 0.;
double liquid_mass_balance_residual = 0.;
double liquid_mass_balance_relative_error = 0.;
double mass_balance_tolerance = 0.05;

char case_id[128] = "W2_visual_pipeline";
char output_dir[512] = ".";
char restore_path[512] = "";
char restored_from[512] = "";
char camera_preset[64] = "science_iso";
char frames_dir[640] = "";
char surfaces_dir[640] = "";
char checkpoints_dir[640] = "";
char fields_dir[640] = "";
char sanitized_case_id[128] = "W2_visual_pipeline";
char schedule_version[128] = "legacy_unspecified";
char schedule_sha[128] = "legacy_unspecified";
char source_sha[128] = "unresolved";
char pending_prediction_closure_path[1200] = "";
int pending_prediction_closure_restore = 0;
int enable_forensic_probes = 0;
int forensic_probe_index = 0;
double forensic_start_time = -1.;
double forensic_end_time = -1.;
char forensic_dir[640] = "";
int projection_trace_index = 0;
char projection_trace_dir[700] = "";

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
double min_runtime_pressure_range = HUGE;
double max_runtime_pressure_range = 0.;
int zero_range_pressure_frames = 0;

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

static void atomic_rename (const char *tmp, const char *dst);

static int file_exists_nonzero (const char *path) {
  struct stat st;
  return stat(path, &st) == 0 && st.st_size > 0;
}

static int canonical_schedule_enabled (void) {
  return schedule_tick_dt > 0.;
}

static int canonical_tick_for_time (double actual) {
  if (!canonical_schedule_enabled())
    return -1;
  int tick = (int) llround(actual/schedule_tick_dt);
  double target = tick*schedule_tick_dt;
  return fabs(actual - target) <= schedule_time_tolerance ? tick : -1;
}

static int dense_tick (int tick) {
  return tick >= dense_start_tick && tick <= dense_end_tick;
}

static int lightweight_tick (int tick) {
  return tick >= 0 &&
    (tick % light_base_stride == 0 ||
     (dense_tick(tick) && tick % light_dense_stride == 0));
}

static int full_field_tick (int tick) {
  return tick >= 0 &&
    (tick % field_base_stride == 0 ||
     (dense_tick(tick) && tick % field_dense_stride == 0));
}

static int checkpoint_target_tick (int tick) {
  return tick > 0 && tick % checkpoint_stride == 0;
}

static void select_output_target (int tick) {
  current_master_tick = tick;
  current_target_time = canonical_schedule_enabled() ? tick*schedule_tick_dt : t;
  current_actual_time = t;
}

static int text_file_contains (const char *path, const char *needle) {
  FILE *fp = fopen(path, "r");
  if (!fp)
    return 0;
  char buffer[4096];
  int found = 0;
  while (fgets(buffer, sizeof(buffer), fp))
    if (strstr(buffer, needle)) {
      found = 1;
      break;
    }
  fclose(fp);
  return found;
}

static void write_schedule_contract (void) {
  char path[1024], tmp[1024], expected_version[320], expected_sha[320];
  output_path(path, sizeof(path), "run_schedule_contract.json");
  snprintf(expected_version, sizeof(expected_version), "\"schedule_version\": \"%s\"", schedule_version);
  snprintf(expected_sha, sizeof(expected_sha), "\"schedule_sha256\": \"%s\"", schedule_sha);
  if (file_exists_nonzero(path) &&
      (!text_file_contains(path, expected_version) || !text_file_contains(path, expected_sha))) {
    fprintf(stderr, "ERROR schedule migration denied: existing contract does not match %s %s\n",
            schedule_version, schedule_sha);
    exit(2);
  }
  output_path(tmp, sizeof(tmp), "run_schedule_contract.json.tmp");
  FILE *fp = fopen(tmp, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot write %s\n", tmp);
    exit(2);
  }
  fprintf(fp,
          "{\n"
          "  \"schema\": \"internal_nozzle_runtime_schedule_v1\",\n"
          "  \"schedule_version\": \"%s\",\n"
          "  \"schedule_sha256\": \"%s\",\n"
          "  \"source_sha256\": \"%s\",\n"
          "  \"master_tick_dt\": %.17g,\n"
          "  \"event_time_tolerance\": %.17g,\n"
          "  \"lightweight\": {\"base_stride\": %d, \"dense_stride\": %d},\n"
          "  \"full_field\": {\"base_stride\": %d, \"dense_stride\": %d},\n"
          "  \"checkpoint_stride\": %d,\n"
          "  \"dense_window\": {\"start_tick\": %d, \"end_tick\": %d},\n"
          "  \"restart_policy\": \"schedule identity mismatch fails closed; completed target times are skipped\"\n"
          "}\n",
          schedule_version, schedule_sha, source_sha, schedule_tick_dt,
          schedule_time_tolerance, light_base_stride, light_dense_stride,
          field_base_stride, field_dense_stride, checkpoint_stride,
          dense_start_tick, dense_end_tick);
  fclose(fp);
  atomic_rename(tmp, path);
}

#define INTERNAL_NOZZLE_PROBE_VARIANT "frozen_candidate"
#include "internal_nozzle_nonmutation_probe.h"
#include "internal_nozzle_checkpoint_v4.h"

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
  snprintf(fields_dir, sizeof(fields_dir), "%s/fields", output_dir);
  ensure_dir(output_dir);
  ensure_dir(frames_dir);
  ensure_dir(surfaces_dir);
  ensure_dir(checkpoints_dir);
  ensure_dir(fields_dir);
  if (enable_forensic_probes) {
    snprintf(forensic_dir, sizeof(forensic_dir), "%s/forensic_probes", output_dir);
    ensure_dir(forensic_dir);
#ifdef INTERNAL_NOZZLE_PROJECTION_TRACE
    snprintf(projection_trace_dir, sizeof(projection_trace_dir),
             "%s/projection_trace", output_dir);
    ensure_dir(projection_trace_dir);
#endif
  }
}

/* Read-only keyed state snapshots for Task 02R. These are called only from
 * phases which already exist in the solver schedule and never call boundary(),
 * restriction(), adaptation, or a solver routine. */
static void write_forensic_probe (const char *phase, int iter_value) {
  if (!enable_forensic_probes ||
      (forensic_start_time >= 0. && t < forensic_start_time - 1e-14) ||
      (forensic_end_time >= 0. && t > forensic_end_time + 1e-14))
    return;
  char cell_path[1024], face_path[1024], manifest_path[1024];
  snprintf(cell_path, sizeof(cell_path), "%s/probe_%05d_%s_t%.9f_i%07d_cells.csv",
           forensic_dir, forensic_probe_index, phase, t, iter_value);
  snprintf(face_path, sizeof(face_path), "%s/probe_%05d_%s_t%.9f_i%07d_faces.csv",
           forensic_dir, forensic_probe_index, phase, t, iter_value);
  FILE *cells = fopen(cell_path, "w");
  FILE *faces = fopen(face_path, "w");
  if (!cells || !faces) {
    fprintf(stderr, "ERROR cannot write forensic probe %s at t %.17g i %d\n",
            phase, t, iter_value);
    exit(2);
  }
  fputs("x,y,z,level,Delta,f,ux,uy,uz,p,pf,gx,gy,gz,cs,cm,un\n", cells);
  foreach(serial) {
    fprintf(cells,
            "%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
            x, y, z, level, Delta, f[], u.x[], u.y[], u.z[], p[], pf[],
            g.x[], g.y[], g.z[], cs[], cm[], un[]);
  }
  fputs("axis,x,y,z,level,Delta,uf,fs,a\n", faces);
  foreach_face(x, serial) {
    fprintf(faces, "x,%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g\n",
            x, y, z, level, Delta, uf.x[], fs.x[], a.x[]);
  }
  foreach_face(y, serial) {
    fprintf(faces, "y,%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g\n",
            x, y, z, level, Delta, uf.y[], fs.y[], a.y[]);
  }
  foreach_face(z, serial) {
    fprintf(faces, "z,%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g\n",
            x, y, z, level, Delta, uf.z[], fs.z[], a.z[]);
  }
  fclose(cells);
  fclose(faces);
  snprintf(manifest_path, sizeof(manifest_path), "%s/probe_manifest.csv", forensic_dir);
  int exists = file_exists_nonzero(manifest_path);
  FILE *manifest = fopen(manifest_path, "a");
  if (!manifest) {
    fprintf(stderr, "ERROR cannot append forensic probe manifest %s\n", manifest_path);
    exit(2);
  }
  if (!exists)
    fputs("probe_index,phase,t,i,cell_file,face_file\n", manifest);
  fprintf(manifest, "%d,%s,%.17g,%d,%s,%s\n", forensic_probe_index, phase,
          t, iter_value, cell_path, face_path);
  fclose(manifest);
  forensic_probe_index++;
}

#ifdef INTERNAL_NOZZLE_PROJECTION_TRACE
static int projection_trace_active (scalar pressure_trace) {
  const char * name = pressure_trace.name;
  return enable_forensic_probes && projection_trace_dir[0] && name &&
    (!strcmp(name, "p") || !strcmp(name, "pf")) &&
    (forensic_start_time < 0. || t >= forensic_start_time - 1e-14) &&
    (forensic_end_time < 0. || t <= forensic_end_time + 1e-14);
}

static void write_trace_scalar_rows
  (FILE * fp, scalar * fields, const char ** labels)
{
  fputs("sequence,x,y,z,level,Delta,is_leaf,field_index,field_role,value\n",
        fp);
  int seq = 0;
  foreach_cell() {
    for (int k = 0; fields[k].i >= 0; k++)
      fprintf(fp, "%d,%a,%a,%a,%d,%a,%d,%d,%s,%a\n",
              seq, x, y, z, level, Delta, is_leaf(cell), k, labels[k],
              is_constant(fields[k]) ? constant(fields[k]) :
              val(fields[k],0,0,0));
    seq++;
  }
}

static void write_trace_boundary_rows
  (FILE * fp, scalar * fields, const char ** labels)
{
  fputs("boundary,sequence,x,y,z,level,Delta,field_index,field_role,value\n",
        fp);
  int seq = 0;
  for (int l = 0; l <= grid->maxdepth; l++)
    foreach_level (l) {
      double eps = 1e-12*max(1., L0);
      if (x - Delta/2. <= X0 + eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "left,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x - Delta, y, z, level, Delta, k, labels[k],
                  val(fields[k],-1,0,0));
        seq++;
      }
      if (x + Delta/2. >= X0 + L0 - eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "right,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x + Delta, y, z, level, Delta, k, labels[k],
                  val(fields[k],1,0,0));
        seq++;
      }
#if dimension > 1
      if (y - Delta/2. <= Y0 + eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "bottom,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x, y - Delta, z, level, Delta, k, labels[k],
                  val(fields[k],0,-1,0));
        seq++;
      }
      if (y + Delta/2. >= Y0 + L0 - eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "top,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x, y + Delta, z, level, Delta, k, labels[k],
                  val(fields[k],0,1,0));
        seq++;
      }
#endif
#if dimension > 2
      if (z - Delta/2. <= Z0 + eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "back,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x, y, z - Delta, level, Delta, k, labels[k],
                  val(fields[k],0,0,-1));
        seq++;
      }
      if (z + Delta/2. >= Z0 + L0 - eps) {
        for (int k = 0; fields[k].i >= 0; k++)
          fprintf(fp, "front,%d,%a,%a,%a,%d,%a,%d,%s,%a\n",
                  seq, x, y, z + Delta, level, Delta, k, labels[k],
                  val(fields[k],0,0,1));
        seq++;
      }
#endif
    }
}

static void append_projection_trace_manifest
  (const char * kind, const char * stage, scalar pressure_trace,
   int cycle, int active_level, int nrelax, double residual_value,
   const char * data_file, const char * boundary_file)
{
  char path[1024];
  snprintf(path, sizeof(path), "%s/trace_manifest.csv", projection_trace_dir);
  int exists = file_exists_nonzero(path);
  FILE * fp = fopen(path, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append projection trace manifest %s\n", path);
    exit(2);
  }
  if (!exists)
    fputs("trace_index,kind,stage,pressure,t,i,dt,DT,dtmax,CFL,"
          "cycle,active_level,nrelax,residual,TOLERANCE,NITERMIN,NITERMAX,"
          "grid_maxdepth,mgp_i,mgp_resb,mgp_resa,mgp_nrelax,"
          "mgpf_i,mgpf_resb,mgpf_resa,mgpf_nrelax,"
          "pressure_nodump,pf_nodump,data_file,boundary_file\n", fp);
  fprintf(fp,
          "%d,%s,%s,%s,%.17g,%d,%.17g,%.17g,%.17g,%.17g,"
          "%d,%d,%d,%.17g,%.17g,%d,%d,%d,"
          "%d,%.17g,%.17g,%d,%d,%.17g,%.17g,%d,%d,%d,%s,%s\n",
          projection_trace_index, kind, stage, pressure_trace.name, t, iter,
          dt, DT, dtmax, CFL, cycle, active_level, nrelax, residual_value,
          TOLERANCE, NITERMIN, NITERMAX, grid->maxdepth,
          mgp.i, mgp.resb, mgp.resa, mgp.nrelax,
          mgpf.i, mgpf.resb, mgpf.resa, mgpf.nrelax,
          p.nodump, pf.nodump, data_file, boundary_file);
  fclose(fp);
}

static void write_projection_boundary_rows
  (FILE * fp, scalar pressure_trace, scalar div_trace)
{
  scalar * fields = (scalar *){pressure_trace, p, pf, div_trace, cm, cs};
  const char * labels[] = {
    "active_pressure", "p", "pf", "div", "cm", "cs"
  };
  write_trace_boundary_rows(fp, fields, labels);
}

void internal_nozzle_prediction_trace_stage
  (const char * stage, face vector uf_trace,
   (const) face vector alpha_trace)
{
  if (!projection_trace_active(pf))
    return;
  char cell_path[1024], face_path[1024], boundary_path[1024], manifest_path[1024];
  snprintf(cell_path, sizeof(cell_path), "%s/prediction_%s_cells.csv",
           projection_trace_dir, stage);
  snprintf(face_path, sizeof(face_path), "%s/prediction_%s_faces.csv",
           projection_trace_dir, stage);
  snprintf(boundary_path, sizeof(boundary_path), "%s/prediction_%s_boundary.csv",
           projection_trace_dir, stage);
  FILE * cells = fopen(cell_path, "w");
  FILE * faces = fopen(face_path, "w");
  FILE * boundaries = fopen(boundary_path, "w");
  if (!cells || !faces || !boundaries) {
    fprintf(stderr, "ERROR cannot create prediction trace %s\n", stage);
    exit(2);
  }
  scalar * cell_fields = (scalar *){f, u, g, p, pf, cm, cs};
  const char * cell_labels[] = {
    "f", "ux", "uy", "uz", "gx", "gy", "gz", "p", "pf", "cm", "cs"
  };
  write_trace_scalar_rows(cells, cell_fields, cell_labels);
  scalar * boundary_fields = (scalar *){u, g, p, pf, f, cm, cs};
  const char * boundary_labels[] = {
    "ux", "uy", "uz", "gx", "gy", "gz", "p", "pf", "f", "cm", "cs"
  };
  write_trace_boundary_rows(boundaries, boundary_fields, boundary_labels);
  fputs("axis,sequence,x,y,z,level,Delta,uf,alpha,fm,fs,a\n", faces);
  int seq = 0;
  foreach_face(x, serial)
    fprintf(faces, "x,%d,%a,%a,%a,%d,%a,%a,%a,%a,%a,%a\n",
            seq++, x, y, z, level, Delta, uf_trace.x[], alpha_trace.x[],
            fm.x[], fs.x[], a.x[]);
  seq = 0;
  foreach_face(y, serial)
    fprintf(faces, "y,%d,%a,%a,%a,%d,%a,%a,%a,%a,%a,%a\n",
            seq++, x, y, z, level, Delta, uf_trace.y[], alpha_trace.y[],
            fm.y[], fs.y[], a.y[]);
  seq = 0;
  foreach_face(z, serial)
    fprintf(faces, "z,%d,%a,%a,%a,%d,%a,%a,%a,%a,%a,%a\n",
            seq++, x, y, z, level, Delta, uf_trace.z[], alpha_trace.z[],
            fm.z[], fs.z[], a.z[]);
  fclose(cells);
  fclose(faces);
  fclose(boundaries);
  snprintf(manifest_path, sizeof(manifest_path),
           "%s/prediction_trace_manifest.csv", projection_trace_dir);
  int exists = file_exists_nonzero(manifest_path);
  FILE * manifest = fopen(manifest_path, "a");
  if (!manifest) {
    fprintf(stderr, "ERROR cannot append prediction trace manifest %s\n",
            manifest_path);
    exit(2);
  }
  if (!exists)
    fputs("stage,t,i,dt,DT,dtmax,CFL,grid_maxdepth,cell_file,face_file,boundary_file\n",
          manifest);
  fprintf(manifest, "%s,%.17g,%d,%.17g,%.17g,%.17g,%.17g,%d,%s,%s,%s\n",
          stage, t, iter, dt, DT, dtmax, CFL, grid->maxdepth,
          cell_path, face_path, boundary_path);
  fclose(manifest);
}

void internal_nozzle_projection_trace_stage
  (const char * stage, face vector uf_trace, scalar pressure_trace,
   (const) face vector alpha_trace, scalar div_trace,
   double projection_dt, int requested_nrelax)
{
  if (!projection_trace_active(pressure_trace))
    return;
  char data_path[1024], boundary_path[1024];
  snprintf(data_path, sizeof(data_path), "%s/trace_%05d_project_%s_%s_cells.csv",
           projection_trace_dir, projection_trace_index, pressure_trace.name, stage);
  snprintf(boundary_path, sizeof(boundary_path),
           "%s/trace_%05d_project_%s_%s_boundary.csv",
           projection_trace_dir, projection_trace_index, pressure_trace.name, stage);
  FILE * cells = fopen(data_path, "w");
  FILE * boundaries = fopen(boundary_path, "w");
  if (!cells || !boundaries) {
    fprintf(stderr, "ERROR cannot create projection trace %s %s\n",
            pressure_trace.name, stage);
    exit(2);
  }
  scalar * fields = (scalar *){pressure_trace, p, pf, div_trace, f, u, g,
                                cm, cs, uf_trace, alpha_trace, fm};
  const char * labels[] = {
    "active_pressure", "p", "pf", "div", "f",
    "ux", "uy", "uz", "gx", "gy", "gz", "cm", "cs",
    "ufx", "ufy", "ufz", "alphax", "alphay", "alphaz",
    "fmx", "fmy", "fmz"
  };
  write_trace_scalar_rows(cells, fields, labels);
  write_projection_boundary_rows(boundaries, pressure_trace, div_trace);
  fclose(cells);
  fclose(boundaries);
  append_projection_trace_manifest("project", stage, pressure_trace, -1, -1,
                                   requested_nrelax, projection_dt,
                                   data_path, boundary_path);
  projection_trace_index++;
}

void internal_nozzle_poisson_trace_stage
  (const char * stage, scalar pressure_trace, scalar rhs_trace,
   (const) face vector alpha_trace, (const) scalar lambda_trace,
   double tolerance, int nrelax, int minlevel)
{
  if (!projection_trace_active(pressure_trace))
    return;
  char data_path[1024], boundary_path[1024];
  snprintf(data_path, sizeof(data_path), "%s/trace_%05d_poisson_%s_%s.csv",
           projection_trace_dir, projection_trace_index, pressure_trace.name, stage);
  snprintf(boundary_path, sizeof(boundary_path),
           "%s/trace_%05d_poisson_%s_%s_boundary.csv",
           projection_trace_dir, projection_trace_index, pressure_trace.name, stage);
  FILE * cells = fopen(data_path, "w");
  FILE * boundaries = fopen(boundary_path, "w");
  if (!cells || !boundaries) {
    fprintf(stderr, "ERROR cannot create Poisson trace %s %s\n",
            pressure_trace.name, stage);
    exit(2);
  }
  scalar * fields = (scalar *){pressure_trace, p, pf, rhs_trace,
                                lambda_trace, alpha_trace, cm, cs, fm};
  const char * labels[] = {
    "active_pressure", "p", "pf", "rhs", "lambda",
    "alphax", "alphay", "alphaz", "cm", "cs", "fmx", "fmy", "fmz"
  };
  write_trace_scalar_rows(cells, fields, labels);
  write_projection_boundary_rows(boundaries, pressure_trace, rhs_trace);
  fclose(cells);
  fclose(boundaries);
  append_projection_trace_manifest("poisson", stage, pressure_trace, -1,
                                   minlevel, nrelax, tolerance,
                                   data_path, boundary_path);
  projection_trace_index++;
}

static void write_mg_boundary_rows
  (FILE * fp, scalar solution, scalar rhs, scalar residual_trace,
   scalar correction_trace, int active_level)
{
  scalar * fields = (scalar *){solution, rhs, residual_trace,
                                correction_trace, p, pf};
  const char * labels[] = {
    "solution", "rhs", "residual", "correction", "p", "pf"
  };
  write_trace_boundary_rows(fp, fields, labels);
}

void internal_nozzle_mg_trace_stage
  (const char * stage, scalar * solution_list, scalar * rhs_list,
   scalar * residual_list, scalar * correction_list,
   int cycle, int active_level, int nrelax, double residual_value)
{
  if (!solution_list)
    return;
  scalar solution = solution_list[0];
  if (!projection_trace_active(solution) || !residual_list || !correction_list)
    return;
  scalar rhs = rhs_list ? rhs_list[0] : residual_list[0];
  scalar residual_trace = residual_list[0];
  scalar correction_trace = correction_list[0];
  char data_path[1024], boundary_path[1024];
  snprintf(data_path, sizeof(data_path), "%s/trace_%05d_mg_%s_%s_c%03d_l%03d.csv",
           projection_trace_dir, projection_trace_index, solution.name, stage,
           cycle, active_level);
  snprintf(boundary_path, sizeof(boundary_path),
           "%s/trace_%05d_mg_%s_%s_c%03d_l%03d_boundary.csv",
           projection_trace_dir, projection_trace_index, solution.name, stage,
           cycle, active_level);
  FILE * cells = fopen(data_path, "w");
  FILE * boundaries = fopen(boundary_path, "w");
  if (!cells || !boundaries) {
    fprintf(stderr, "ERROR cannot create multigrid trace %s %s\n",
            solution.name, stage);
    exit(2);
  }
  scalar * fields = (scalar *){solution, rhs, residual_trace,
                                correction_trace, p, pf};
  const char * labels[] = {
    "solution", "rhs", "residual", "correction", "p", "pf"
  };
  write_trace_scalar_rows(cells, fields, labels);
  if (active_level >= 0)
    write_mg_boundary_rows(boundaries, solution, rhs, residual_trace,
                           correction_trace, active_level);
  fclose(cells);
  fclose(boundaries);
  append_projection_trace_manifest("multigrid", stage, solution, cycle,
                                   active_level, nrelax, residual_value,
                                   data_path, boundary_path);
  projection_trace_index++;
}

void internal_nozzle_projection_trace_summary
  (scalar pressure_trace, int iterations, double residual_before,
   double residual_after, double rhs_sum, int nrelax, int minlevel)
{
  if (!projection_trace_active(pressure_trace))
    return;
  char path[1024];
  snprintf(path, sizeof(path), "%s/projection_summaries.csv", projection_trace_dir);
  int exists = file_exists_nonzero(path);
  FILE * fp = fopen(path, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append projection summary %s\n", path);
    exit(2);
  }
  if (!exists)
    fputs("pressure,t,i,iterations,residual_before,residual_after,rhs_sum,nrelax,minlevel\n",
          fp);
  fprintf(fp, "%s,%.17g,%d,%d,%.17g,%.17g,%.17g,%d,%d\n",
          pressure_trace.name, t, iter, iterations, residual_before,
          residual_after, rhs_sum, nrelax, minlevel);
  fclose(fp);
}
#endif

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

static void recover_checkpoint_metadata (const char *checkpoint) {
  char meta[1200];
  snprintf(meta, sizeof(meta), "%s.meta", checkpoint);
  FILE *fp = fopen(meta, "r");
  if (!fp) {
    if (canonical_schedule_enabled()) {
      fprintf(stderr, "ERROR canonical restart metadata is missing: %s\n", meta);
      exit(2);
    }
    return;
  }
  char line[2048], found_version[128] = "", found_sha[128] = "";
  int found_tick = -1, found_iteration = -1;
  double found_target = -1., found_actual = -1.;
  while (fgets(line, sizeof(line), fp)) {
    if (sscanf(line, "schedule_version=%127s", found_version) == 1)
      continue;
    if (sscanf(line, "schedule_sha256=%127s", found_sha) == 1)
      continue;
    if (sscanf(line, "master_tick=%d", &found_tick) == 1)
      continue;
    if (sscanf(line, "iteration=%d", &found_iteration) == 1)
      continue;
    if (sscanf(line, "target_time=%lf", &found_target) == 1)
      continue;
    if (sscanf(line, "actual_time=%lf", &found_actual) == 1)
      continue;
    if (sscanf(line, "initial_liquid_volume=%lf", &initial_liquid_volume) == 1)
      continue;
    if (sscanf(line, "cumulative_liquid_inflow=%lf", &cumulative_liquid_inflow) == 1)
      continue;
    if (sscanf(line, "cumulative_liquid_outflow=%lf", &cumulative_liquid_outflow) == 1)
      continue;
    if (sscanf(line, "previous_liquid_inflow_rate=%lf", &previous_liquid_inflow_rate) == 1)
      continue;
    if (sscanf(line, "previous_liquid_outflow_rate=%lf", &previous_liquid_outflow_rate) == 1)
      continue;
    if (sscanf(line, "last_mass_balance_time=%lf", &last_mass_balance_time) == 1)
      continue;
    if (sscanf(line, "timestep_previous=%lf", &internal_nozzle_timestep_previous) == 1)
      continue;
    if (sscanf(line, "mgp_nrelax=%d", &mgp.nrelax) == 1)
      continue;
    if (sscanf(line, "mgpf_nrelax=%d", &mgpf.nrelax) == 1)
      continue;
    if (sscanf(line, "mgu_nrelax=%d", &mgu.nrelax) == 1)
      continue;
    if (sscanf(line, "initial_interface_proxy=%lf", &initial_interface_proxy) == 1)
      continue;
    if (sscanf(line, "max_interface_growth=%lf", &max_interface_growth) == 1)
      continue;
    if (sscanf(line, "max_active_front=%lf", &max_active_front) == 1)
      continue;
    if (sscanf(line, "max_post_tag_count=%d", &max_post_tag_count) == 1)
      continue;
    if (sscanf(line, "max_detached_proxy_count=%d", &max_detached_proxy_count) == 1)
      continue;
    sscanf(line, "max_one_cell_debris_count=%d", &max_one_cell_debris_count);
  }
  fclose(fp);
  if (canonical_schedule_enabled() &&
      (strcmp(found_version, schedule_version) || strcmp(found_sha, schedule_sha))) {
    fprintf(stderr,
            "ERROR schedule migration denied for checkpoint: found %s %s, requested %s %s\n",
            found_version, found_sha, schedule_version, schedule_sha);
    exit(2);
  }
  if (canonical_schedule_enabled() &&
      (found_tick < 0 || fabs(found_actual - found_target) > schedule_time_tolerance)) {
    fprintf(stderr, "ERROR invalid canonical checkpoint timing metadata in %s\n", meta);
    exit(2);
  }
  current_master_tick = found_tick;
  current_target_time = found_target;
  current_actual_time = found_actual;
  if (canonical_schedule_enabled())
    restore_time = found_target;
  if (canonical_schedule_enabled()) {
    t = found_target;
    recovered_checkpoint_iteration = found_iteration;
    /* centered.h calls stability once from its init event and again for the
     * resumed iteration. The first call may compute dt but must not advance
     * the persisted timestep-ramp history. */
    internal_nozzle_timestep_restore_probe = 1;
    snprintf(pending_prediction_closure_path,
             sizeof(pending_prediction_closure_path),
             "%s.prediction-closure-v4", checkpoint);
    if (!file_exists_nonzero(pending_prediction_closure_path)) {
      fprintf(stderr, "ERROR prediction-closure-v4 checkpoint is missing: %s\n",
              pending_prediction_closure_path);
      exit(2);
    }
    pending_prediction_closure_restore = 1;
  }
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
  output_path(path, sizeof(path), "field_frame_manifest.csv");
  int field_max = max_frame_from_csv(path, 2);
  field_frame_index = field_max >= 0 ? field_max + 1 : 0;
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
          "  %s --case-id smoke_full --domain full --maxlevel 5 --pressure 351.48 --end-time 0.015 --external-dh 3.0 --output-dir OUTPUT --diagnostic-dt 0.005 --field-dt 0.005 --visual-dt 0.005 --checkpoint-dt 0.005 --raw-export 1 --field-export 1 --native-frames 1 --facet-export 1 --max-steps 1000\n"
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
          "  --field-dt FLOAT           post-projection field-export cadence\n"
          "  --visual-dt FLOAT          native frame/facet cadence\n"
          "  --checkpoint-dt FLOAT      checkpoint cadence\n"
          "  --schedule-tick-dt FLOAT   canonical master-tick spacing; enables exact schedule\n"
          "  --schedule-version STR     canonical schedule version (required with schedule)\n"
          "  --schedule-sha STR         canonical schedule SHA-256 (required with schedule)\n"
          "  --source-sha STR           source SHA-256 recorded in every output manifest\n"
          "  --schedule-tolerance FLOAT event-time acceptance tolerance\n"
          "  --light-base-stride INT    lightweight base stride in master ticks\n"
          "  --light-dense-stride INT   lightweight dense-window stride\n"
          "  --field-base-stride INT    full-field base stride in master ticks\n"
          "  --field-dense-stride INT   full-field dense-window stride\n"
          "  --checkpoint-stride INT    checkpoint stride in master ticks\n"
          "  --dense-start-tick INT     dense-window first master tick\n"
          "  --dense-end-tick INT       dense-window final master tick\n"
          "  --mass-balance-tolerance FLOAT relative liquid mass-balance gate\n"
          "  --raw-export 0|1           enable raw station/interface CSV export\n"
          "  --field-export 0|1         enable post-projection phase/u/vorticity/p CSV export\n"
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
    else if (!strcmp(argv[a], "--field-dt"))
      field_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--visual-dt"))
      visual_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--checkpoint-dt"))
      checkpoint_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--schedule-tick-dt"))
      schedule_tick_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--schedule-version"))
      copy_string(schedule_version, sizeof(schedule_version), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--schedule-sha"))
      copy_string(schedule_sha, sizeof(schedule_sha), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--source-sha"))
      copy_string(source_sha, sizeof(source_sha), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--schedule-tolerance"))
      schedule_time_tolerance = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--light-base-stride"))
      light_base_stride = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--light-dense-stride"))
      light_dense_stride = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--field-base-stride"))
      field_base_stride = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--field-dense-stride"))
      field_dense_stride = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--checkpoint-stride"))
      checkpoint_stride = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--dense-start-tick"))
      dense_start_tick = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--dense-end-tick"))
      dense_end_tick = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--mass-balance-tolerance"))
      mass_balance_tolerance = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--raw-export"))
      enable_raw_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--field-export"))
      enable_field_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--native-frames"))
      enable_native_frames = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--facet-export"))
      enable_facet_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--forensic-probes"))
      enable_forensic_probes = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--forensic-start-time"))
      forensic_start_time = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--forensic-end-time"))
      forensic_end_time = atof(require_value(argc, argv, &a));
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
  double leak = 0.;
  foreach(reduction(max:leak)) {
    if (cs[] > 1e-8) {
      if (y < 1.5*Delta)
        leak = max(leak, fabs(u.y[]));
      if (z < 1.5*Delta)
        leak = max(leak, fabs(u.z[]));
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

static void liquid_boundary_fluxes (double *inflow, double *outflow) {
  double qin = 0., qexit = 0.;
  foreach_boundary(left, reduction(+:qin))
    qin += clamp(f[], 0., 1.)*u.x[]*cs[]*sq(Delta);
  foreach_boundary(right, reduction(+:qexit))
    qexit += clamp(f[], 0., 1.)*u.x[]*cs[]*sq(Delta);
  *inflow = qin;
  *outflow = qexit;
}

static void integrate_liquid_flux_to_time (double actual_time) {
  double qin = 0., qexit = 0.;
  liquid_boundary_fluxes(&qin, &qexit);
  if (initial_liquid_volume < 0.)
    initial_liquid_volume = liquid_volume_total();
  if (last_mass_balance_time >= 0. &&
      actual_time > last_mass_balance_time + schedule_time_tolerance) {
    double interval = actual_time - last_mass_balance_time;
    cumulative_liquid_inflow += 0.5*(previous_liquid_inflow_rate + qin)*interval;
    cumulative_liquid_outflow += 0.5*(previous_liquid_outflow_rate + qexit)*interval;
  }
  previous_liquid_inflow_rate = qin;
  previous_liquid_outflow_rate = qexit;
  last_mass_balance_time = actual_time;
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
  liquid_inventory_change_fraction = initial_liquid_volume > 0. ?
    (*lv - initial_liquid_volume)/initial_liquid_volume : 0.;
  double expected = initial_liquid_volume + cumulative_liquid_inflow - cumulative_liquid_outflow;
  liquid_mass_balance_residual = *lv - expected;
  double scale = max(initial_liquid_volume + fabs(cumulative_liquid_inflow), 1e-30);
  liquid_mass_balance_relative_error = fabs(liquid_mass_balance_residual)/scale;
  final_liquid_volume_error = liquid_mass_balance_relative_error;
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

static void write_field_export_contract (void) {
  char path[1024], tmp[1024];
  output_path(path, sizeof(path), "field_export_contract.json");
  output_path(tmp, sizeof(tmp), "field_export_contract.json.tmp");
  FILE *fp = fopen(tmp, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot write %s\n", tmp);
    exit(2);
  }
  fprintf(fp,
          "{\n"
          "  \"schema\": \"internal_nozzle_post_projection_fields_v2\",\n"
          "  \"selected_case\": \"W2_longer_duration\",\n"
          "  \"pressure_provenance\": \"runtime_cell_centered_p_after_centered_projection\",\n"
          "  \"event_provenance\": \"canonical_master_tick_post_projection_i_plus_plus_last\",\n"
          "  \"pressure_gauge_context\": \"Dirichlet p=pressure_value at left and p=0 at right; values are outlet-gauge-relative\",\n"
          "  \"gravity_enabled\": false,\n"
          "  \"fields\": [\"phase_fraction\", \"velocity_x\", \"velocity_y\", \"velocity_z\", \"velocity_magnitude\", \"vorticity_magnitude\", \"pressure\", \"embedded_fluid_fraction\"],\n"
          "  \"coordinate_convention\": \"x_streamwise_y_width_z_height_origin_nozzle_inlet\",\n"
          "  \"frame_naming\": \"field_tTTTTTT.TTTTTT_iIIIIIII_fFFFF.csv\",\n"
          "  \"station_frame_join\": \"case_id+schedule_sha256+master_tick; frame index is local\",\n"
          "  \"source_sha256\": \"%s\",\n"
          "  \"schedule_version\": \"%s\",\n"
          "  \"schedule_sha256\": \"%s\",\n"
          "  \"instrumentation_changes_solver_state\": false\n"
          "}\n", source_sha, schedule_version, schedule_sha);
  fclose(fp);
  atomic_rename(tmp, path);
}

static void write_post_projection_fields (int iter_value) {
  char leaf[256], path[1024], rel[768], source_frame[96];
  snprintf(leaf, sizeof(leaf), "field_t%013.6f_i%07d_f%04d.csv",
           current_target_time, iter_value, field_frame_index);
  subdir_path(path, sizeof(path), fields_dir, leaf);
  snprintf(rel, sizeof(rel), "fields/%s", leaf);
  snprintf(source_frame, sizeof(source_frame), "tick%06d_t%013.6f_i%07d",
           current_master_tick, current_target_time, iter_value);

  FILE *fp = fopen(path, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot write %s\n", path);
    exit(2);
  }
  fprintf(fp, "case_id,source_frame_id,field_frame_index,t,i,x,y,z,f,ux,uy,uz,velocity_magnitude,vorticity_magnitude,p,cs,level,Delta,region_flag,pressure_provenance,event_provenance,gravity_enabled,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,restart_lineage\n");

  double pmin = HUGE, pmax = -HUGE, fmin = HUGE, fmax = -HUGE;
  double umin = HUGE, umax = -HUGE, omin = HUGE, omax = -HUGE;
  int sample_count = 0;
  double transverse = transverse_scale*plenum_scale*Wrect;
  foreach(serial) {
    int transverse_ok = domain_quarter ? (y <= transverse && z <= transverse) :
      (fabs(y) <= transverse && fabs(z) <= transverse);
    if (cs[] > 1e-8 && x <= exit_x() + external_Dh*Dhrect && transverse_ok) {
      double ux = u.x[], uy = u.y[], uz = u.z[];
      double omx = (u.z[0,1,0] - u.z[0,-1,0] - u.y[0,0,1] + u.y[0,0,-1])/(2.*Delta);
      double omy = (u.x[0,0,1] - u.x[0,0,-1] - u.z[1,0,0] + u.z[-1,0,0])/(2.*Delta);
      double omz = (u.y[1,0,0] - u.y[-1,0,0] - u.x[0,1,0] + u.x[0,-1,0])/(2.*Delta);
      double umag = sqrt(sq(ux) + sq(uy) + sq(uz));
      double omag = sqrt(sq(omx) + sq(omy) + sq(omz));
      pmin = min(pmin, p[]); pmax = max(pmax, p[]);
      fmin = min(fmin, f[]); fmax = max(fmax, f[]);
      umin = min(umin, umag); umax = max(umax, umag);
      omin = min(omin, omag); omax = max(omax, omag);
      fprintf(fp, "%s,%s,%d,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%d,runtime_cell_centered_p_after_centered_projection,canonical_master_tick_post_projection_i_plus_plus_last,0,%s,%s,%s,%d,%.17g,%.17g,%s\n",
              case_id, source_frame, field_frame_index, t, iter_value, x, y, z,
              f[], ux, uy, uz, umag, omag, p[], cs[], level, Delta, region_flag(x),
              source_sha, schedule_version, schedule_sha, current_master_tick,
              current_target_time, current_actual_time,
              restored_from[0] ? restored_from : "fresh");
      sample_count++;
    }
  }
  fclose(fp);

  double prange = sample_count > 0 ? pmax - pmin : 0.;
  int pressure_nonzero = sample_count > 0 && isfinite(prange) && prange > 1e-12;
  if (sample_count > 0) {
    min_runtime_pressure_range = min(min_runtime_pressure_range, prange);
    max_runtime_pressure_range = max(max_runtime_pressure_range, prange);
  }
  if (!pressure_nonzero)
    zero_range_pressure_frames++;

  char manifest[1024];
  output_path(manifest, sizeof(manifest), "field_frame_manifest.csv");
  FILE *mf = fopen(manifest, "a");
  if (!mf) {
    fprintf(stderr, "ERROR cannot append %s\n", manifest);
    exit(2);
  }
  fprintf(mf, "%s,%s,%d,%.12g,%d,%s,%d,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,runtime_cell_centered_p_after_centered_projection,canonical_master_tick_post_projection_i_plus_plus_last,outlet_dirichlet_zero_gauge,0,%s,%s,%s,%d,%.17g,%.17g,%d,%s,%s\n",
          case_id, domain_label(), field_frame_index, t, iter_value, rel, sample_count,
          sample_count > 0 ? pmin : 0., sample_count > 0 ? pmax : 0., prange,
          pressure_nonzero, sample_count > 0 ? fmin : 0., sample_count > 0 ? fmax : 0.,
          sample_count > 0 ? umin : 0., sample_count > 0 ? umax : 0.,
          sample_count > 0 ? omin : 0., sample_count > 0 ? omax : 0.,
          source_sha, schedule_version, schedule_sha, current_master_tick,
          current_target_time, current_actual_time, maxlevel,
          restored_from[0] ? restored_from : "fresh",
          "f|ux|uy|uz|velocity_magnitude|vorticity_magnitude|p|cs");
  fclose(mf);
  field_frame_index++;
}

static void initialize_output_files (void) {
  char path[1024];
  output_path(path, sizeof(path), "raw_frame_summary.csv");
  write_header_if_missing(path, "case_id,t,frame_index,i,mean_exit_velocity,exit_flow,exit_liquid_area,profile_sanity,liquid_volume,liquid_mass_balance_relative_error,active_front,active_front_Dh,interface_proxy,interface_growth,post_tag_count,detached_proxy_count,one_cell_debris_count,liquid_inventory_change_fraction,cumulative_liquid_inflow,cumulative_liquid_outflow,liquid_mass_balance_residual,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,maxlevel,pressure_provenance,gravity_enabled,restart_lineage\n");
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
  write_header_if_missing(path, "case_id,domain_mode,frame_index,t,i,filename,format,camera,exit_marker,nozzle_exit_x,Dh,pressure,maxlevel,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,pressure_provenance,gravity_enabled,restart_lineage\n");
  output_path(path, sizeof(path), "surface_manifest.csv");
  write_header_if_missing(path, "case_id,domain_mode,surface_index,t,i,filename,facet_cell_count,nozzle_exit_x,Dh,maxlevel,source_frame_id,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,pressure_provenance,gravity_enabled,restart_lineage\n");
  output_path(path, sizeof(path), "checkpoint_index.csv");
  write_header_if_missing(path, "case_id,domain_mode,checkpoint_index,t,i,maxlevel,filename,parent_checkpoint,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,metadata_file,prediction_closure_state_file\n");
  output_path(path, sizeof(path), "field_frame_manifest.csv");
  write_header_if_missing(path, "case_id,domain_mode,field_frame_index,t,i,filename,sample_count,p_min,p_max,p_range,pressure_nonzero,f_min,f_max,velocity_magnitude_min,velocity_magnitude_max,vorticity_magnitude_min,vorticity_magnitude_max,pressure_provenance,event_provenance,pressure_gauge_context,gravity_enabled,source_sha256,schedule_version,schedule_sha256,master_tick,target_time,actual_time,maxlevel,restart_lineage,field_list\n");
  write_field_export_contract();
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
  fprintf(fp, "%s,%s,%d,%.12g,%d,%s,ppm,%s,nozzle_exit_text_overlay,%.12g,%.12g,%.12g,%d,%s,%s,%s,%d,%.17g,%.17g,runtime_cell_centered_p_after_centered_projection,0,%s\n",
          case_id, domain_label(), visual_frame_index, t, iter_value, rel, camera_preset,
          exit_x(), Dhrect, pressure_value, maxlevel, source_sha, schedule_version,
          schedule_sha, current_master_tick, current_target_time, current_actual_time,
          restored_from[0] ? restored_from : "fresh");
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
  fprintf(fp, "# source_sha256=%s\n# schedule_version=%s\n# schedule_sha256=%s\n", source_sha, schedule_version, schedule_sha);
  fprintf(fp, "# master_tick=%d\n# target_time=%.17g\n# actual_time=%.17g\n", current_master_tick, current_target_time, current_actual_time);
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
  fprintf(mf, "%s,%s,%d,%.12g,%d,%s,%d,%.12g,%.12g,%d,%s,%s,%s,%s,%d,%.17g,%.17g,runtime_cell_centered_p_after_centered_projection,0,%s\n",
          case_id, domain_label(), surface_frame_index, t, iter_value, rel, facet_cells,
          exit_x(), Dhrect, maxlevel, source_frame, source_sha, schedule_version,
          schedule_sha, current_master_tick, current_target_time, current_actual_time,
          restored_from[0] ? restored_from : "fresh");
  fclose(mf);
  rewrite_surface_manifest();
  surface_frame_index++;
}

static void write_checkpoint_dump (int iter_value) {
  char leaf[256], path[1024], parent[512] = "fresh";
  internal_nozzle_probe_mark
    ("checkpoint_event_entry", "candidate_modified", "write_checkpoint_dump");
  if (restored_ok && restored_from[0])
    copy_string(parent, sizeof(parent), restored_from);
  snprintf(leaf, sizeof(leaf), "%s_%s_t%09.6f_i%07d_l%d.dump",
           sanitized_case_id, domain_label(), t, iter_value, maxlevel);
  subdir_path(path, sizeof(path), checkpoints_dir, leaf);
  InternalNozzleProbeSnapshot operation_before = internal_nozzle_probe_capture();
  InternalNozzleInvariantSnapshotV4 before =
    internal_nozzle_invariant_snapshot_v4();
  InternalNozzleProbeSnapshot operation_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&operation_before, &operation_after, "candidate_aggregate_snapshot_before",
     "candidate_added", "internal_nozzle_invariant_snapshot_v4");
  char closure_state[1200];
  snprintf(closure_state, sizeof(closure_state),
           "%s.prediction-closure-v4", path);
  operation_before = internal_nozzle_probe_capture();
  internal_nozzle_write_prediction_closure_v4(closure_state);
  operation_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&operation_before, &operation_after, "candidate_prediction_closure_writer",
     "candidate_added", "internal_nozzle_write_prediction_closure_v4");
  p.nodump = pf.nodump = false;
  operation_before = internal_nozzle_probe_capture();
  dump(file = path);
  operation_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&operation_before, &operation_after, "native_dump", "pre_existing",
     "dump:file_path");
  operation_before = internal_nozzle_probe_capture();
  InternalNozzleInvariantSnapshotV4 after =
    internal_nozzle_invariant_snapshot_v4();
  operation_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&operation_before, &operation_after, "candidate_aggregate_snapshot_after",
     "candidate_added", "internal_nozzle_invariant_snapshot_v4");
  if (before.active_physical_hash != after.active_physical_hash ||
      before.actual_face_hash != after.actual_face_hash ||
      before.active_physical_count != after.active_physical_count ||
      before.actual_face_count != after.actual_face_count) {
    fprintf(stderr, "ERROR checkpoint persistence writer changed active cells or actual faces\n");
    exit(2);
  }
  if (!file_exists_nonzero(path)) {
    fprintf(stderr, "ERROR checkpoint dump is missing or empty: %s\n", path);
    stable_flag = 0;
    return;
  }
  char meta[1200];
  snprintf(meta, sizeof(meta), "%s.meta", path);
  FILE *metadata = fopen(meta, "w");
  if (!metadata) {
    fprintf(stderr, "ERROR cannot write checkpoint metadata %s\n", meta);
    exit(2);
  }
  fprintf(metadata,
          "schema=internal_nozzle_checkpoint_metadata_v4\n"
          "case_id=%s\n"
          "source_sha256=%s\n"
          "schedule_version=%s\n"
          "schedule_sha256=%s\n"
          "master_tick=%d\n"
          "target_time=%.17g\n"
          "actual_time=%.17g\n"
          "iteration=%d\n"
          "maxlevel=%d\n"
          "pressure_provenance=runtime_cell_centered_p_after_centered_projection\n"
          "gravity_enabled=false\n"
          "restored_from=%s\n"
          "initial_liquid_volume=%.17g\n"
          "cumulative_liquid_inflow=%.17g\n"
          "cumulative_liquid_outflow=%.17g\n"
          "previous_liquid_inflow_rate=%.17g\n"
          "previous_liquid_outflow_rate=%.17g\n"
          "last_mass_balance_time=%.17g\n"
          "solver_dt=%.17g\n"
          "timestep_previous=%.17g\n"
          "mgp_nrelax=%d\n"
          "mgpf_nrelax=%d\n"
          "mgu_nrelax=%d\n"
          "initial_interface_proxy=%.17g\n"
          "max_interface_growth=%.17g\n"
          "max_active_front=%.17g\n"
          "max_post_tag_count=%d\n"
          "max_detached_proxy_count=%d\n"
          "max_one_cell_debris_count=%d\n"
          "prediction_closure_schema=internal_nozzle_prediction_closure_v4\n"
          "prediction_closure_state=%s\n",
          case_id, source_sha, schedule_version, schedule_sha,
          current_master_tick, current_target_time, current_actual_time,
          iter_value, maxlevel, parent, initial_liquid_volume,
          cumulative_liquid_inflow, cumulative_liquid_outflow,
          previous_liquid_inflow_rate, previous_liquid_outflow_rate,
          last_mass_balance_time, dt, internal_nozzle_timestep_previous,
          mgp.nrelax, mgpf.nrelax, mgu.nrelax, initial_interface_proxy,
          max_interface_growth, max_active_front, max_post_tag_count,
          max_detached_proxy_count, max_one_cell_debris_count, closure_state);
  fclose(metadata);
  char csv[1024];
  output_path(csv, sizeof(csv), "checkpoint_index.csv");
  FILE *fp = fopen(csv, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append %s\n", csv);
    exit(2);
  }
  fprintf(fp, "%s,%s,%d,%.12g,%d,%d,%s,%s,%s,%s,%s,%d,%.17g,%.17g,%s,%s\n",
          case_id, domain_label(), checkpoint_index, t, iter_value, maxlevel, path, parent,
          source_sha, schedule_version, schedule_sha, current_master_tick,
          current_target_time, current_actual_time, meta, closure_state);
  fclose(fp);
  rewrite_checkpoint_manifest();
  checkpoint_index++;
}

int main (int argc, char **argv) {
  parse_args(argc, argv);
  base_pressure_value = pressure_value;
  if (!canonical_schedule_enabled() && enable_field_export && field_dt <= 0.) {
    fprintf(stderr, "ERROR --field-dt must be positive when field export is enabled\n");
    return 2;
  }
  if (!canonical_schedule_enabled() && enable_field_export && fabs(field_dt - diagnostic_dt) > 1e-12) {
    fprintf(stderr, "ERROR --field-dt must equal --diagnostic-dt for matched field/station cadence\n");
    return 2;
  }
  if (canonical_schedule_enabled()) {
    if (!strcmp(schedule_version, "legacy_unspecified") ||
        !strcmp(schedule_sha, "legacy_unspecified") ||
        !strcmp(source_sha, "unresolved")) {
      fprintf(stderr, "ERROR canonical schedule requires --schedule-version, --schedule-sha, and --source-sha\n");
      return 2;
    }
    if (schedule_time_tolerance <= 0. || light_base_stride <= 0 ||
        light_dense_stride <= 0 || field_base_stride <= 0 ||
        field_dense_stride <= 0 || checkpoint_stride <= 0 ||
        dense_start_tick < 0 || dense_end_tick < dense_start_tick) {
      fprintf(stderr, "ERROR invalid canonical schedule controls\n");
      return 2;
    }
    int final_tick = (int) llround(end_time/schedule_tick_dt);
    if (fabs(end_time - final_tick*schedule_tick_dt) > schedule_time_tolerance) {
      fprintf(stderr, "ERROR end_time %.17g is not a canonical master tick for dt %.17g\n",
              end_time, schedule_tick_dt);
      return 2;
    }
    diagnostic_dt = schedule_tick_dt;
    field_dt = schedule_tick_dt;
    visual_dt = schedule_tick_dt;
    checkpoint_dt = schedule_tick_dt;
  }
  if (mass_balance_tolerance <= 0.) {
    fprintf(stderr, "ERROR mass-balance tolerance must be positive\n");
    return 2;
  }

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
  write_schedule_contract();
  if (auto_restore && !restore_requested && discover_latest_checkpoint(restore_path, sizeof(restore_path)))
    restore_requested = 1;
  initialize_output_files();
  run();
}

event init (t = 0) {
  p.nodump = pf.nodump = false;
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
    /* Generic dumps contain cell-centered interior values, not ghost-cell
     * state. Reconstruct every persisted solver field boundary before the
     * centered init event consumes g, p, or pf on the resumed step. */
    boundary({f, u, un, p, pf, g});
    recover_indices_for_restore();
    recover_metrics_from_existing_raw();
    double indexed_time = checkpoint_time_from_index(restore_path);
    restore_time = indexed_time >= 0. ? indexed_time : t;
    recover_checkpoint_metadata(restore_path);
    next_field_export_time = restore_time + field_dt;
    write_forensic_probe("post_restore_pre_centered", i);
    fprintf(stderr, "restored checkpoint %s at t %.12g i %d next_visual %d next_raw %d next_surface %d next_checkpoint %d mg_nrelax=%d/%d/%d\n",
            restored_from, restore_time, i, visual_frame_index, raw_frame_index,
            surface_frame_index, checkpoint_index, mgp.nrelax, mgpf.nrelax,
            mgu.nrelax);
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

/* Validate and apply the complete keyed prediction-read closure only after
 * properties and field-specific boundary reconstruction. No operation may
 * rewrite the closure between this hook and the first resumed prediction. */
event stability (i++, last) {
  if (pending_prediction_closure_restore) {
    event("properties");
    boundary ({f, u, p, pf, g});
    internal_nozzle_restore_prediction_closure_v4
      (pending_prediction_closure_path);
    char closure_probe[1024];
    output_path(closure_probe, sizeof(closure_probe),
                "restored_prediction_closure_probe.v4");
    internal_nozzle_write_prediction_closure_v4(closure_probe);
    fprintf(stderr,
            "restored prediction-closure-v4 and timestep-ramp history %.17g before resumed advection; probe=%s\n",
            internal_nozzle_timestep_previous, closure_probe);
    pending_prediction_closure_restore = 0;
  }
  write_forensic_probe("stability_post_sidecar", i);
}

event pressure_update (i++) {
  if (perturb_amp != 0. && perturb_period > 0.)
    pressure_value = base_pressure_value*(1. + perturb_amp*sin(2.*pi*t/perturb_period));
  else
    pressure_value = base_pressure_value;
  write_forensic_probe("pressure_update", i);
}

/* Integrate signed liquid fluxes at both streamwise boundaries.  Inventory
 * change is reported separately from the conservation residual. */
event liquid_mass_balance (i++, last) {
  integrate_liquid_flux_to_time(t);
}

/*
 * centered.h registers projection(i++,last) before this event. Keeping this
 * export in the same last-event group and declaring it later makes p[] the
 * runtime cell-centered pressure produced by that completed projection.
 * The event is read-only with respect to solver fields.
 */
event post_projection_fields (i++, last) {
  write_forensic_probe("post_projection", i);
  if (!enable_field_export || field_dt <= 0.)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  if (canonical_schedule_enabled()) {
    int tick = canonical_tick_for_time(t);
    if (tick < 0 || !full_field_tick(tick))
      return 0;
    select_output_target(tick);
  }
  else {
    if (t + 1e-12 < next_field_export_time)
      return 0;
    current_master_tick = field_frame_index;
    current_target_time = t;
    current_actual_time = t;
  }
  write_post_projection_fields(i);
  if (!canonical_schedule_enabled())
    next_field_export_time = t + field_dt;
}

event diagnostics (t = 0.; t += diagnostic_dt; t <= end_time + 1e-12) {
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  if (canonical_schedule_enabled()) {
    int tick = canonical_tick_for_time(t);
    if (tick < 0 || !lightweight_tick(tick))
      return 0;
    select_output_target(tick);
  }
  else {
    current_master_tick = raw_frame_index;
    current_target_time = t;
    current_actual_time = t;
  }
  integrate_liquid_flux_to_time(t);
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

  if (enable_raw_export &&
      (!canonical_schedule_enabled() || full_field_tick(current_master_tick))) {
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
  fprintf(fp, "%s,%.12g,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%s,%s,%s,%d,%.17g,%.17g,%d,runtime_cell_centered_p_after_centered_projection,0,%s\n",
          case_id, t, raw_frame_index, i, mean_u, flow, area, ps, lv, final_liquid_volume_error,
          af, Dhrect > 0. ? af/Dhrect : 0., ip, growth, nt, nd, debris,
          liquid_inventory_change_fraction, cumulative_liquid_inflow,
          cumulative_liquid_outflow, liquid_mass_balance_residual, source_sha,
          schedule_version, schedule_sha, current_master_tick, current_target_time,
          current_actual_time, maxlevel, restored_from[0] ? restored_from : "fresh");
  fclose(fp);
  raw_frame_index++;

  if (final_liquid_volume_error > mass_balance_tolerance) {
    fprintf(stderr, "ERROR liquid mass-balance relative error %.12g exceeds %.12g at t %.12g\n",
            final_liquid_volume_error, mass_balance_tolerance, t);
    stable_flag = 0;
  }
}

event native_frames (t = 0.; t += visual_dt; t <= end_time + 1e-12) {
  if (!enable_native_frames)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  if (canonical_schedule_enabled()) {
    int tick = canonical_tick_for_time(t);
    if (tick < 0 || !lightweight_tick(tick))
      return 0;
    select_output_target(tick);
  }
  else {
    current_master_tick = visual_frame_index;
    current_target_time = t;
    current_actual_time = t;
  }
  write_native_frame(i);
}

event surface_facets (t = 0.; t += visual_dt; t <= end_time + 1e-12) {
  if (!enable_facet_export)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  if (canonical_schedule_enabled()) {
    int tick = canonical_tick_for_time(t);
    if (tick < 0 || !lightweight_tick(tick))
      return 0;
    select_output_target(tick);
  }
  else {
    current_master_tick = surface_frame_index;
    current_target_time = t;
    current_actual_time = t;
  }
  write_surface_facets(i);
}

event checkpoint_dumps (t = checkpoint_dt; t += checkpoint_dt; t <= end_time + 1e-12) {
  if (canonical_schedule_enabled())
    return 0;
  if (checkpoint_dt <= 0.)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  current_master_tick = checkpoint_index + 1;
  current_target_time = t;
  current_actual_time = t;
  write_checkpoint_dump(i);
}

/* Canonical checkpoints are taken only after the completed projection and
 * other last-timestep solver events at the exact master tick. */
event canonical_checkpoint_dumps (i++, last) {
  if (!canonical_schedule_enabled())
    return 0;
  if (restored_ok && t <= restore_time + schedule_time_tolerance)
    return 0;
  int tick = canonical_tick_for_time(t);
  if (tick < 0 || !checkpoint_target_tick(tick))
    return 0;
  select_output_target(tick);
  integrate_liquid_flux_to_time(t);
  write_checkpoint_dump(i);
  write_forensic_probe("post_checkpoint", i);
}

event logfile (i++) {
  write_forensic_probe("logfile", i);
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
  fprintf(fp, "case_id,domain_mode,case_mode,t,i,maxlevel,baselevel,pressure_value,base_pressure_value,perturb_amp,perturb_period,target_u,mean_exit_velocity,pressure_retuned,exit_flow,exit_liquid_area,liquid_volume,liquid_mass_balance_relative_error,max_active_front,max_active_front_Dh,max_interface_proxy,max_interface_growth,max_post_tag_count,max_detached_proxy_count,max_one_cell_debris_count,symmetry_leakage,width,height,Dh,area,external_Dh,diagnostic_dt,visual_dt,checkpoint_dt,raw_export,native_frames,facet_export,restored_from,stable_flag,liquid_inventory_change_fraction,cumulative_liquid_inflow,cumulative_liquid_outflow,liquid_mass_balance_residual,mass_balance_tolerance,source_sha256,schedule_version,schedule_sha256\n");
  fprintf(fp, "%s,%s,%d,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%s,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%s,%s,%s\n",
          case_id, domain_label(), case_mode, t, last_iter, maxlevel, baselevel,
          pressure_value, base_pressure_value, perturb_amp, perturb_period, target_u,
          final_mean_exit_velocity, fabs(base_pressure_value - 2524.75) > 1e-6 || perturb_amp != 0.,
          final_exit_flow, final_exit_area, final_liquid_volume, final_liquid_volume_error,
          max_active_front, Dhrect > 0. ? max_active_front/Dhrect : 0.,
          max_interface_proxy, max_interface_growth, max_post_tag_count,
          max_detached_proxy_count, max_one_cell_debris_count, max_symmetry_leakage,
          Wrect, Hrect, Dhrect, A0, external_Dh, diagnostic_dt, visual_dt,
          checkpoint_dt, enable_raw_export, enable_native_frames, enable_facet_export,
          restored_from[0] ? restored_from : "fresh", stable_flag,
          liquid_inventory_change_fraction, cumulative_liquid_inflow,
          cumulative_liquid_outflow, liquid_mass_balance_residual,
          mass_balance_tolerance, source_sha, schedule_version, schedule_sha);
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
          "  \"gravity_enabled\": false,\n"
          "  \"maxlevel\": %d,\n"
          "  \"end_time\": %.12g,\n"
          "  \"diagnostic_dt\": %.12g,\n"
          "  \"field_dt\": %.12g,\n"
          "  \"visual_dt\": %.12g,\n"
          "  \"checkpoint_dt\": %.12g,\n"
          "  \"source_sha256\": \"%s\",\n"
          "  \"schedule_version\": \"%s\",\n"
          "  \"schedule_sha256\": \"%s\",\n"
          "  \"master_tick_dt\": %.17g,\n"
          "  \"mass_balance\": {\"inventory_change_fraction\": %.12g, \"cumulative_inflow\": %.12g, \"cumulative_outflow\": %.12g, \"residual\": %.12g, \"relative_error\": %.12g, \"tolerance\": %.12g, \"passed\": %s},\n"
          "  \"geometry\": {\"W\": %.12g, \"H\": %.12g, \"Dh\": %.12g, \"A0\": %.12g, \"nozzle_exit_x\": %.12g},\n"
          "  \"export_modes\": [\"post_projection_runtime_fields\", \"station_slab_raw_export\", \"interface_cloud_export\", \"component_diagnostics_export\", \"profile_exit_export\", \"native_vof_frames\", \"output_facets_surfaces\", \"checkpoint_dumps\"],\n"
          "  \"pressure_export\": {\"provenance\": \"runtime_cell_centered_p_after_centered_projection\", \"gauge_context\": \"outlet_dirichlet_zero_gauge\", \"min_frame_range\": %.12g, \"max_frame_range\": %.12g, \"zero_range_frames\": %d},\n"
          "  \"files\": {\n"
          "    \"case_summary\": \"visual_pipeline_case_summary.csv\",\n"
          "    \"frame_summary\": \"raw_frame_summary.csv\",\n"
          "    \"station_cells\": \"raw_station_cells.csv\",\n"
          "    \"interface_cells\": \"raw_interface_cells.csv\",\n"
          "    \"component_summary\": \"raw_component_summary.csv\",\n"
          "    \"profile_exit_cells\": \"raw_profile_exit_cells.csv\",\n"
          "    \"reduced_cross_sections\": \"raw_reduced_cross_section_metrics.csv\",\n"
          "    \"field_contract\": \"field_export_contract.json\",\n"
          "    \"field_manifest\": \"field_frame_manifest.csv\",\n"
          "    \"visual_manifest\": \"visual_frame_manifest.json\",\n"
          "    \"surface_manifest\": \"surface_manifest.json\",\n"
          "    \"checkpoint_manifest\": \"checkpoint_manifest.json\"\n"
          "  },\n"
          "  \"claim_boundary\": \"internal restartable visual-output pipeline only; not validation or public media; fit_ready=false; public_ready=false\"\n"
          "}\n",
          case_id, domain_label(), maxlevel, t, diagnostic_dt, field_dt, visual_dt, checkpoint_dt,
          source_sha, schedule_version, schedule_sha, schedule_tick_dt,
          liquid_inventory_change_fraction, cumulative_liquid_inflow,
          cumulative_liquid_outflow, liquid_mass_balance_residual,
          liquid_mass_balance_relative_error, mass_balance_tolerance,
          liquid_mass_balance_relative_error <= mass_balance_tolerance ? "true" : "false",
          Wrect, Hrect, Dhrect, A0, exit_x(),
          min_runtime_pressure_range < HUGE ? min_runtime_pressure_range : 0.,
          max_runtime_pressure_range, zero_range_pressure_frames);
  fclose(fp);
}
