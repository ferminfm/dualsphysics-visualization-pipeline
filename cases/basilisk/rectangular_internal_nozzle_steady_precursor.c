#include "grid/octree.h"
#include "embed.h"
#ifndef INTERNAL_NOZZLE_RESTARTABLE_TIMESTEP
# error "compile through the hash-gated restartable centered-header preparation path"
#endif
#include "internal_nozzle_centered.h"
#include "navier-stokes/perfs.h"
#include "internal_nozzle_precursor_geometry.h"

#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <sys/stat.h>
#include <string.h>

/*
 * Unsteady single-liquid precursor for the accepted W2 internal nozzle.
 *
 * This is a pressure-driven development case, not a prescribed-profile case:
 *   p(left) = 351.48, p(right) = 0, velocity gradients are zero at both;
 *   embedded walls are no-slip; rho = mu = 1; initial velocity is zero.
 * The full unsteady centered equations are retained.  No stokes=true shortcut,
 * two-phase interface, surface tension, body force or imposed nonzero velocity
 * is present.  The external gas/free-jet domain is intentionally absent.
 *
 * Each segment writes a native checkpoint, a complete leaf-cell u/p transfer
 * table and durable compact diagnostics.  The table is deliberately unsealed;
 * prepare_internal_nozzle_precursor_transfer.py validates steady-state evidence,
 * hashes the checkpoint/table and emits the only accepted transfer manifest.
 */

/* `f` is a restart-closure topology marker for this single-liquid case.  It is
 * identically equal to the embedded fluid fraction `cs`; no two-phase physics
 * reads it.  This lets the already-validated keyed v4 closure audit the same
 * active-cell shape as the two-phase source without changing its format. */
scalar f[], previous_ux[], previous_normalized_profile[];
face vector muv[];

static InternalNozzleGeometry geometry;
static int maxlevel = 7;
static int baselevel = 4;
static int maximum_steps = 1000000;
static int metric_stride = 10;
static int last_metric_iteration = -1;
static int restored = 0;
static int previous_profile_available = 0;
static double end_time = 1.;
static double timestep_cap = 2e-4;
static double pressure_forcing = 351.48;
static double density_liquid = 1.;
static double viscosity_liquid = 1.;
static char case_id[128] = "steady_precursor_w2";
static char output_dir[1024] = "";
static char source_commit[64] = "";
static char source_sha256[80] = "";
static char restore_checkpoint[1024] = "";
static char restore_metadata[1024] = "";
static char target_template[1024] = "";
static char precursor_closure_path[1200] = "";
static char source_sha[128] = "";
static char restore_source_sha[128] = "";
static char schedule_version[128] = "internal_nozzle_precursor_schedule_v1";
static char schedule_sha[128] =
  "3598151fc5833c68d778830532e9c90e5d451f0c08b44e5da95a11b2952dcd11";
static int pending_precursor_closure_restore = 0;
static int expected_restore_iteration = -1;
static int expected_previous_profile_available = -1;
static double expected_restore_time = -1.;
static double expected_restore_dt = -1.;
static double expected_restore_dtmax = -1.;
static double expected_timestep_previous = -1.;
static long target_transfer_sample_count = 0;
static long target_transfer_exit_clamp_count = 0;

#define INTERNAL_NOZZLE_TARGET_SAMPLE_SCHEMA \
  "internal_nozzle_precursor_unsealed_export_v2"
#define INTERNAL_NOZZLE_TARGET_SAMPLE_METHOD \
  "basilisk_interpolate_at_target_leaf_center_or_strict_outlet_straddle_internal_limit_v2"
#define INTERNAL_NOZZLE_TARGET_CLAMP_RULE \
  "clamp_only_when_target_leaf_strictly_straddles_geometric_outlet"

#define INTERNAL_NOZZLE_PROBE_VARIANT "steady_precursor"
#include "internal_nozzle_nonmutation_probe.h"
#include "internal_nozzle_checkpoint_v4.h"

static const double plane_locations_dh[] = {0.5, 2.0, 5.0, 10.0, 14.5};
static const char *plane_labels[] = {
  "upstream_plenum", "contraction_entry", "straight_entry",
  "mid_straight", "near_exit"
};
#define PRECURSOR_PLANE_COUNT 5

static int is_hex_string (const char *text, size_t required_length) {
  if (!text || strlen(text) != required_length)
    return 0;
  for (size_t index = 0; index < required_length; index++)
    if (!isxdigit((unsigned char)text[index]))
      return 0;
  return 1;
}

static int is_safe_case_id (const char *text) {
  if (!text || !text[0])
    return 0;
  for (size_t index = 0; text[index]; index++)
    if (!isalnum((unsigned char)text[index]) && text[index] != '_' &&
        text[index] != '-')
      return 0;
  return 1;
}

static int regular_nonzero_file (const char *path) {
  struct stat status;
  return lstat(path, &status) == 0 && S_ISREG(status.st_mode) &&
    status.st_size > 0;
}

static void output_path (char *buffer, size_t size, const char *leaf) {
  if (snprintf(buffer, size, "%s/%s", output_dir, leaf) >= (int)size) {
    fprintf(stderr, "ERROR output path exceeds buffer for %s\n", leaf);
    exit(2);
  }
}

static void require_new_output_file (const char *path) {
  struct stat status;
  if (lstat(path, &status) == 0) {
    fprintf(stderr, "ERROR refusing to overwrite existing output %s\n", path);
    exit(2);
  }
  if (errno != ENOENT) {
    fprintf(stderr, "ERROR cannot inspect output %s: %s\n", path,
            strerror(errno));
    exit(2);
  }
}

static void ensure_output_directory (void) {
  struct stat status;
  if (!output_dir[0]) {
    fprintf(stderr, "ERROR --output-dir is required\n");
    exit(2);
  }
  if (lstat(output_dir, &status) != 0) {
    if (errno != ENOENT || mkdir(output_dir, 0755) != 0) {
      fprintf(stderr, "ERROR cannot create output directory %s: %s\n",
              output_dir, strerror(errno));
      exit(2);
    }
  }
  else if (!S_ISDIR(status.st_mode) || S_ISLNK(status.st_mode)) {
    fprintf(stderr, "ERROR output directory is not a real directory: %s\n",
            output_dir);
    exit(2);
  }
}

static const char *require_value (int argc, char **argv, int *index) {
  if (*index + 1 >= argc) {
    fprintf(stderr, "ERROR missing value after %s\n", argv[*index]);
    exit(2);
  }
  (*index)++;
  return argv[*index];
}

static void copy_text (char *destination, size_t size, const char *source) {
  if (snprintf(destination, size, "%s", source) >= (int)size) {
    fprintf(stderr, "ERROR argument exceeds destination buffer\n");
    exit(2);
  }
}

static void print_usage (const char *program) {
  fprintf(stdout,
          "usage: %s --output-dir PATH --source-commit SHA40 "
          "--source-sha256 SHA256 [options]\n"
          "\n"
          "Options:\n"
          "  --case-id ID              safe manifest identifier\n"
          "  --maxlevel INT            default 7; must be physical-L7-equivalent\n"
          "  --baselevel INT           default 4\n"
          "  --end-time FLOAT          segment terminal code time\n"
          "  --dt-cap FLOAT            maximum timestep, default 2e-4\n"
          "  --metric-stride INT       post-projection iteration cadence\n"
          "  --max-steps INT           hard iteration cap\n"
          "  --restore PATH            native predecessor dump\n"
          "  --restore-metadata PATH   required sidecar for --restore\n"
          "  --target-template PATH    exact two-phase target-leaf template to sample\n"
          "\n"
          "Fixed physical contract: rho=1, mu=1, p_left=351.48, p_right=0, "
          "2Dh+3Dh+10Dh geometry and embedded no-slip walls.\n",
          program);
}

static void parse_arguments (int argc, char **argv) {
  for (int index = 1; index < argc; index++) {
    if (!strcmp(argv[index], "--help") || !strcmp(argv[index], "-h")) {
      print_usage(argv[0]);
      exit(0);
    }
    else if (!strcmp(argv[index], "--output-dir"))
      copy_text(output_dir, sizeof(output_dir),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--source-commit"))
      copy_text(source_commit, sizeof(source_commit),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--source-sha256"))
      copy_text(source_sha256, sizeof(source_sha256),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--case-id"))
      copy_text(case_id, sizeof(case_id),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--maxlevel"))
      maxlevel = atoi(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--baselevel"))
      baselevel = atoi(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--end-time"))
      end_time = atof(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--dt-cap"))
      timestep_cap = atof(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--metric-stride"))
      metric_stride = atoi(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--max-steps"))
      maximum_steps = atoi(require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--restore"))
      copy_text(restore_checkpoint, sizeof(restore_checkpoint),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--restore-metadata"))
      copy_text(restore_metadata, sizeof(restore_metadata),
                require_value(argc, argv, &index));
    else if (!strcmp(argv[index], "--target-template"))
      copy_text(target_template, sizeof(target_template),
                require_value(argc, argv, &index));
    else {
      fprintf(stderr, "ERROR unknown option %s\n", argv[index]);
      exit(2);
    }
  }
}

static void verify_arguments (void) {
  if (!is_safe_case_id(case_id) || !is_hex_string(source_commit, 40) ||
      !is_hex_string(source_sha256, 64)) {
    fprintf(stderr, "ERROR invalid case ID or source identity\n");
    exit(2);
  }
  if (baselevel < 1 || maxlevel < baselevel || maxlevel > 12 ||
      !internal_nozzle_is_physical_l7_equivalent(maxlevel)) {
    fprintf(stderr,
            "ERROR invalid levels or resolution is coarser than accepted "
            "physical-L7-equivalent delta %.17g Dh\n",
            internal_nozzle_accepted_l7_delta_dh());
    exit(2);
  }
  if (!(end_time > 0.) || !(timestep_cap > 0.) || metric_stride <= 0 ||
      maximum_steps <= 0) {
    fprintf(stderr, "ERROR invalid time, cadence or step limit\n");
    exit(2);
  }
  if ((restore_checkpoint[0] && !restore_metadata[0]) ||
      (!restore_checkpoint[0] && restore_metadata[0])) {
    fprintf(stderr, "ERROR --restore and --restore-metadata are inseparable\n");
    exit(2);
  }
  if (target_template[0] && !regular_nonzero_file(target_template)) {
    fprintf(stderr, "ERROR target template is missing, empty or non-regular\n");
    exit(2);
  }
}

static void build_geometry (void) {
  vertex scalar phi[];
  foreach_vertex()
    phi[] = internal_nozzle_internal_phi(&geometry, x, y, z);
  boundary({phi});
  fractions(phi, cs, fs);
  fractions_cleanup(cs, fs);
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
p[left] = dirichlet(pressure_forcing);
pf[left] = dirichlet(pressure_forcing);
p[right] = dirichlet(0.);
pf[right] = dirichlet(0.);

event properties (i++) {
  foreach_face()
    muv.x[] = viscosity_liquid*fm.x[];
  boundary((scalar *){muv});
}

static int precursor_same_double (double left, double right) {
  return isfinite(left) && isfinite(right) &&
    fabs(left - right) <= 64.*DBL_EPSILON*max(1., max(fabs(left), fabs(right)));
}

static void verify_restore_sidecar (void) {
  if (!regular_nonzero_file(restore_checkpoint) ||
      !regular_nonzero_file(restore_metadata)) {
    fprintf(stderr, "ERROR restore dump or sidecar is missing/non-regular\n");
    exit(2);
  }
  char expected_metadata[1200];
  if (snprintf(expected_metadata, sizeof(expected_metadata), "%s.meta",
               restore_checkpoint) >= (int)sizeof(expected_metadata) ||
      strcmp(expected_metadata, restore_metadata)) {
    fprintf(stderr, "ERROR restore metadata must be the dump's exact sidecar\n");
    exit(2);
  }
  if (snprintf(precursor_closure_path, sizeof(precursor_closure_path),
               "%s.prediction-closure-v4", restore_checkpoint) >=
      (int)sizeof(precursor_closure_path) ||
      !regular_nonzero_file(precursor_closure_path)) {
    fprintf(stderr, "ERROR precursor prediction closure is missing/non-regular\n");
    exit(2);
  }
  FILE *stream = fopen(restore_metadata, "r");
  if (!stream) {
    fprintf(stderr, "ERROR cannot open restore sidecar %s\n", restore_metadata);
    exit(2);
  }
  char line[2048], schema[128] = "", fingerprint[256] = "";
  char found_case[128] = "", found_commit[64] = "", found_sha[80] = "";
  char closure_schema[128] = "", closure_state[256] = "";
  int found_level = -1, found_iteration = -1, found_profile = -1;
  double found_pressure = HUGE, found_density = HUGE, found_viscosity = HUGE;
  double found_time = HUGE, found_t_star = HUGE, found_dt = HUGE;
  double found_dtmax = HUGE, found_timestep_previous = HUGE;
  unsigned long seen = 0;
#define PRECURSOR_META_SCAN(bit, expression) do { \
    if ((expression) == 1) { \
      if (seen & (1UL << (bit))) { \
        fprintf(stderr, "ERROR duplicate precursor checkpoint metadata key\n"); \
        exit(2); \
      } \
      seen |= 1UL << (bit); \
      continue; \
    } \
  } while (0)
  while (fgets(line, sizeof(line), stream)) {
    PRECURSOR_META_SCAN(0, sscanf(line, "schema=%127s", schema));
    PRECURSOR_META_SCAN(1, sscanf(line, "case_id=%127s", found_case));
    PRECURSOR_META_SCAN(2, sscanf(line, "geometry_fingerprint=%255s", fingerprint));
    PRECURSOR_META_SCAN(3, sscanf(line, "source_commit=%63s", found_commit));
    PRECURSOR_META_SCAN(4, sscanf(line, "source_sha256=%79s", found_sha));
    PRECURSOR_META_SCAN(5, sscanf(line, "maxlevel=%d", &found_level));
    PRECURSOR_META_SCAN(6, sscanf(line, "pressure_forcing=%lf", &found_pressure));
    PRECURSOR_META_SCAN(7, sscanf(line, "density_liquid=%lf", &found_density));
    PRECURSOR_META_SCAN(8, sscanf(line, "viscosity_liquid=%lf", &found_viscosity));
    PRECURSOR_META_SCAN(9, sscanf(line, "t=%lf", &found_time));
    PRECURSOR_META_SCAN(10, sscanf(line, "t_star=%lf", &found_t_star));
    PRECURSOR_META_SCAN(11, sscanf(line, "i=%d", &found_iteration));
    PRECURSOR_META_SCAN(12, sscanf(line, "solver_dt=%lf", &found_dt));
    PRECURSOR_META_SCAN(13, sscanf(line, "solver_dtmax=%lf", &found_dtmax));
    PRECURSOR_META_SCAN(14, sscanf(line, "timestep_previous=%lf", &found_timestep_previous));
    PRECURSOR_META_SCAN(15, sscanf(line, "previous_profile_available=%d", &found_profile));
    PRECURSOR_META_SCAN(16, sscanf(line, "prediction_closure_schema=%127s", closure_schema));
    PRECURSOR_META_SCAN(17, sscanf(line, "prediction_closure_state=%255s", closure_state));
  }
#undef PRECURSOR_META_SCAN
  fclose(stream);
  if (seen != ((1UL << 18) - 1) ||
      strcmp(schema, "internal_nozzle_precursor_checkpoint_v2") ||
      strcmp(found_case, case_id) ||
      strcmp(fingerprint, INTERNAL_NOZZLE_GEOMETRY_FINGERPRINT) ||
      strcmp(found_commit, source_commit) || strcmp(found_sha, source_sha256) ||
      found_level != maxlevel || !precursor_same_double(found_pressure, pressure_forcing) ||
      !precursor_same_double(found_density, density_liquid) ||
      !precursor_same_double(found_viscosity, viscosity_liquid) ||
      !precursor_same_double(found_t_star, found_time/geometry.hydraulic_diameter) ||
      found_iteration < 0 || !(found_dt > 0.) || !(found_dtmax > 0.) ||
      !(found_timestep_previous >= 0.) ||
      (found_profile != 0 && found_profile != 1) ||
      strcmp(closure_schema, "internal_nozzle_prediction_closure_v4") ||
      strcmp(closure_state, "precursor-final.dump.prediction-closure-v4")) {
    fprintf(stderr, "ERROR restore sidecar does not match active contract\n");
    exit(2);
  }
  expected_restore_time = found_time;
  expected_restore_iteration = found_iteration;
  expected_restore_dt = found_dt;
  expected_restore_dtmax = found_dtmax;
  expected_timestep_previous = found_timestep_previous;
  expected_previous_profile_available = found_profile;
  internal_nozzle_timestep_restore_probe = 1;
}

static void verify_restored_precursor_identity (void) {
  if (!precursor_same_double(t, expected_restore_time) ||
      iter != expected_restore_iteration) {
    fprintf(stderr, "ERROR native precursor dump does not match its sidecar t/i\n");
    exit(2);
  }
  /* Basilisk's native DumpHeader owns both time and iteration.  Never replace
   * either value from a sidecar after a mismatch. */
  internal_nozzle_verify_prediction_closure_identity_v4
    (precursor_closure_path, source_sha, expected_restore_time,
     expected_restore_iteration, maxlevel, expected_restore_dt,
     expected_restore_dtmax, expected_timestep_previous);
}

typedef struct {
  double area;
  double flow;
  double kinetic_flux;
  double pressure_mean;
  double bulk_velocity;
  double beta;
  double alpha;
} PlaneMetrics;

static PlaneMetrics measure_plane (double plane_dh) {
  PlaneMetrics result = {0., 0., 0., 0., 0., 0., 0.};
  const double plane_x = plane_dh*geometry.hydraulic_diameter;
  double area = 0., flow = 0., kinetic_flux = 0.;
  double pressure_integral = 0., cubic_integral = 0.;
  foreach(reduction(+:area) reduction(+:flow)
          reduction(+:kinetic_flux) reduction(+:pressure_integral)
          reduction(+:cubic_integral)) {
    if (cs[] > 1e-10 && x - 0.5*Delta <= plane_x &&
        plane_x < x + 0.5*Delta) {
      const double weight = internal_nozzle_aperture_overlap
        (&geometry, plane_x, y, z, Delta);
      if (weight > 0.) {
        area += weight;
        flow += u.x[]*weight;
        kinetic_flux += density_liquid*u.x[]*u.x[]*weight;
        pressure_integral += p[]*weight;
        cubic_integral += u.x[]*u.x[]*u.x[]*weight;
      }
    }
  }
  result.area = area;
  result.flow = flow;
  result.kinetic_flux = kinetic_flux;
  if (result.area > 0.) {
    result.pressure_mean = pressure_integral/result.area;
    result.bulk_velocity = result.flow/result.area;
  }
  if (result.area > 0. && fabs(result.flow) > 1e-30) {
    result.beta = result.kinetic_flux*result.area/
      (density_liquid*result.flow*result.flow);
    result.alpha = cubic_integral*result.area*result.area/
      (result.flow*result.flow*result.flow);
  }
  return result;
}

static double update_exit_profile_change (double bulk_velocity) {
  const double plane_x = plane_locations_dh[PRECURSOR_PLANE_COUNT - 1]*
    geometry.hydraulic_diameter;
  double numerator = 0., denominator = 0.;
  foreach(reduction(+:numerator) reduction(+:denominator)) {
    if (cs[] > 1e-10 && x - 0.5*Delta <= plane_x &&
        plane_x < x + 0.5*Delta) {
      const double weight = internal_nozzle_aperture_overlap
        (&geometry, plane_x, y, z, Delta);
      if (weight > 0. && fabs(bulk_velocity) > 1e-30) {
        const double normalized = u.x[]/bulk_velocity;
        if (previous_profile_available) {
          const double difference = normalized - previous_normalized_profile[];
          numerator += difference*difference*weight;
          denominator += previous_normalized_profile[]*
            previous_normalized_profile[]*weight;
        }
        previous_normalized_profile[] = normalized;
      }
    }
  }
  boundary({previous_normalized_profile});
  if (!previous_profile_available) {
    previous_profile_available = 1;
    return -1.;
  }
  return denominator > 0. ? sqrt(numerator/denominator) : -1.;
}

static void write_metric_row (int iter_value) {
  PlaneMetrics planes[PRECURSOR_PLANE_COUNT];
  for (int plane = 0; plane < PRECURSOR_PLANE_COUNT; plane++)
    planes[plane] = measure_plane(plane_locations_dh[plane]);
  const PlaneMetrics upstream = planes[0];
  const PlaneMetrics exit_plane = planes[PRECURSOR_PLANE_COUNT - 1];
  const double profile_change =
    update_exit_profile_change(exit_plane.bulk_velocity);
  const double imbalance_scale =
    fabs(exit_plane.flow) > 1e-30 ? fabs(exit_plane.flow) : 1.;
  const double mass_imbalance =
    fabs(upstream.flow - exit_plane.flow)/imbalance_scale;
  double maximum_change = 0., cell_count = 0.;
  foreach(reduction(max:maximum_change) reduction(+:cell_count)) {
    if (cs[] > 1e-10) {
      maximum_change = max(maximum_change,
                           fabs(u.x[] - previous_ux[]));
      cell_count += 1.;
      previous_ux[] = u.x[];
    }
  }
  boundary({previous_ux});

  char path[1400];
  output_path(path, sizeof(path), "precursor_history.csv");
  FILE *stream = fopen(path, "a");
  if (!stream) {
    fprintf(stderr, "ERROR cannot append precursor history\n");
    exit(2);
  }
  fprintf(stream,
          "%s,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
          "%.17g,%.17g,%.17g,%.17g,%.17g,%d,%d,%.17g,%.17g,%d,%s\n",
          case_id, t, t/geometry.hydraulic_diameter, iter_value,
          exit_plane.flow, density_liquid*exit_plane.flow,
          exit_plane.kinetic_flux,
          pressure_forcing - exit_plane.pressure_mean,
          exit_plane.area, exit_plane.bulk_velocity,
          exit_plane.beta, exit_plane.alpha, mass_imbalance,
          profile_change, maximum_change, mgp.i, mgu.i,
          mgp.resa, mgu.resa, (int)cell_count,
          restored ? "restored" : "fresh");
  fclose(stream);

  output_path(path, sizeof(path), "precursor_plane_history.csv");
  stream = fopen(path, "a");
  if (!stream) {
    fprintf(stderr, "ERROR cannot append plane history\n");
    exit(2);
  }
  for (int plane = 0; plane < PRECURSOR_PLANE_COUNT; plane++)
    fprintf(stream,
            "%s,%.17g,%.17g,%d,%s,%.17g,%.17g,%.17g,%.17g,%.17g,"
            "%.17g,%.17g,%.17g\n",
            case_id, t, t/geometry.hydraulic_diameter, iter_value,
            plane_labels[plane], plane_locations_dh[plane],
            planes[plane].area, planes[plane].flow,
            density_liquid*planes[plane].flow,
            planes[plane].kinetic_flux, planes[plane].pressure_mean,
            planes[plane].beta, planes[plane].alpha);
  fclose(stream);
  last_metric_iteration = iter_value;
}

static void initialize_outputs (void) {
  char path[1400];
  output_path(path, sizeof(path), "precursor_history.csv");
  require_new_output_file(path);
  FILE *stream = fopen(path, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create precursor history\n");
    exit(2);
  }
  fputs("case_id,t,t_star,i,Q_l,mdot_l,J_k,pressure_drop,exit_area,U_bulk,"
        "beta,alpha,mass_flow_imbalance,profile_l2_change,max_ux_change,"
        "mgp_iterations,mgu_iterations,mgp_residual,mgu_residual,cell_count,"
        "restart_state\n", stream);
  fclose(stream);

  output_path(path, sizeof(path), "precursor_plane_history.csv");
  require_new_output_file(path);
  stream = fopen(path, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create precursor plane history\n");
    exit(2);
  }
  fputs("case_id,t,t_star,i,plane_label,plane_dh,area,Q_l,mdot_l,J_k,"
        "pressure_mean,beta,alpha\n", stream);
  fclose(stream);

  output_path(path, sizeof(path), "run_contract.json");
  require_new_output_file(path);
  stream = fopen(path, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create run contract\n");
    exit(2);
  }
  fprintf(stream,
          "{\n"
          "  \"schema\": \"internal_nozzle_precursor_run_v1\",\n"
          "  \"case_id\": \"%s\",\n"
          "  \"geometry_schema\": \"%s\",\n"
          "  \"geometry_fingerprint\": \"%s\",\n"
          "  \"source_commit\": \"%s\",\n"
          "  \"source_sha256\": \"%s\",\n"
          "  \"pressure_forcing\": %.17g,\n"
          "  \"density_liquid\": %.17g,\n"
          "  \"viscosity_liquid\": %.17g,\n"
          "  \"initial_velocity\": \"zero_everywhere_fresh_start\",\n"
          "  \"boundary_contract\": \"pressure_dirichlet_351_48_to_zero_velocity_neumann_embedded_no_slip\",\n"
          "  \"equations\": \"unsteady_single_liquid_centered_navier_stokes\",\n"
          "  \"maxlevel\": %d,\n"
          "  \"baselevel\": %d,\n"
          "  \"delta_min_Dh\": %.17g,\n"
          "  \"accepted_physical_L7_delta_Dh\": %.17g,\n"
          "  \"end_time\": %.17g,\n"
          "  \"dt_cap\": %.17g,\n"
          "  \"metric_stride\": %d,\n"
          "  \"target_template\": \"%s\",\n"
          "  \"restore_checkpoint\": \"%s\",\n"
          "  \"restore_metadata\": \"%s\"\n"
          "}\n",
          case_id, INTERNAL_NOZZLE_GEOMETRY_SCHEMA,
          INTERNAL_NOZZLE_GEOMETRY_FINGERPRINT, source_commit, source_sha256,
          pressure_forcing, density_liquid, viscosity_liquid, maxlevel,
          baselevel, internal_nozzle_precursor_delta_dh(maxlevel),
          internal_nozzle_accepted_l7_delta_dh(), end_time, timestep_cap,
          metric_stride, target_template[0] ? target_template :
          "not_applicable", restore_checkpoint[0] ? restore_checkpoint :
          "not_applicable", restore_metadata[0] ? restore_metadata :
          "not_applicable");
  fclose(stream);
}

static void write_target_transfer_samples (void) {
  if (!target_template[0])
    return;
  target_transfer_sample_count = 0;
  target_transfer_exit_clamp_count = 0;
  FILE *input = fopen(target_template, "r");
  if (!input) {
    fprintf(stderr, "ERROR cannot open target template %s\n", target_template);
    exit(2);
  }
  char line[2048];
  if (!fgets(line, sizeof(line), input) ||
      strcmp(line, "x,y,z,level,Delta,cs,f\n")) {
    fprintf(stderr, "ERROR incompatible target-template header\n");
    exit(2);
  }
  char output[1400], temporary[1400];
  output_path(output, sizeof(output), "precursor-target-samples.csv");
  output_path(temporary, sizeof(temporary), "precursor-target-samples.csv.tmp");
  require_new_output_file(output);
  require_new_output_file(temporary);
  FILE *stream = fopen(temporary, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create target-sampled transfer table\n");
    exit(2);
  }
  fputs("x,y,z,level,Delta,cs,f,source_sample_x,exit_clamped,ux,uy,uz,p\n",
        stream);
  long count = 0;
  while (fgets(line, sizeof(line), input)) {
    double rx, ry, rz, delta, target_cs, target_f;
    int target_level;
    char trailing;
    int parsed = sscanf(line, "%lf,%lf,%lf,%d,%lf,%lf,%lf %c",
                        &rx, &ry, &rz, &target_level, &delta,
                        &target_cs, &target_f, &trailing);
    if (parsed != 7 || !isfinite(rx) || !isfinite(ry) || !isfinite(rz) ||
        !isfinite(delta) || !isfinite(target_cs) || !isfinite(target_f) ||
        delta <= 0. || target_level < 0 || target_cs <= 1e-8 ||
        target_cs > 1. || target_f <= 1e-8 || target_f > 1.) {
      fprintf(stderr, "ERROR malformed target-template row %ld\n", count + 2);
      exit(2);
    }
    const double outlet_x =
      geometry.internal_dh*geometry.hydraulic_diameter;
    /* A target VOF cell may straddle the initial exit plane while its center
     * lies just downstream of the internal-only precursor domain.  Clamp only
     * a geometrically verified straddling leaf; a farther downstream row is a
     * wrong target and must not silently inherit the exit state. */
    double sample_x = rx;
    int exit_clamped = 0;
    if (rx >= outlet_x) {
      const double lower = rx - 0.5*delta;
      const double upper = rx + 0.5*delta;
      if (!(lower < outlet_x && upper > outlet_x)) {
        fprintf(stderr,
                "ERROR downstream target row %ld does not straddle outlet: "
                "x=%.17g Delta=%.17g outlet=%.17g\n",
                count + 2, rx, delta, outlet_x);
        exit(2);
      }
      sample_x = nextafter(outlet_x, 0.);
      exit_clamped = 1;
      target_transfer_exit_clamp_count++;
    }
    double ux = interpolate(u.x, sample_x, ry, rz);
    double uy = interpolate(u.y, sample_x, ry, rz);
    double uz = interpolate(u.z, sample_x, ry, rz);
    double pressure = interpolate(p, sample_x, ry, rz);
    if (!isfinite(ux) || !isfinite(uy) || !isfinite(uz) ||
        !isfinite(pressure) || fabs(ux) >= 0.5*HUGE ||
        fabs(uy) >= 0.5*HUGE || fabs(uz) >= 0.5*HUGE ||
        fabs(pressure) >= 0.5*HUGE) {
      fprintf(stderr, "ERROR nonfinite/nodata precursor sample at target row %ld\n",
              count + 2);
      exit(2);
    }
    fprintf(stream,
            "%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g,%.17g,%d,"
            "%.17g,%.17g,%.17g,%.17g\n",
            rx, ry, rz, target_level, delta, target_cs, target_f,
            sample_x, exit_clamped, ux, uy, uz, pressure);
    count++;
  }
  fclose(input);
  if (!count || fclose(stream) || rename(temporary, output)) {
    fprintf(stderr, "ERROR failed to persist target-sampled transfer table\n");
    exit(2);
  }
  target_transfer_sample_count = count;
}

static void write_checkpoint_and_transfer (int iter_value) {
  char checkpoint[1400], checkpoint_tmp[1400], metadata[1400];
  char cells[1400], cells_tmp[1400], export_metadata[1400], closure[1400];
  output_path(checkpoint, sizeof(checkpoint), "precursor-final.dump");
  output_path(checkpoint_tmp, sizeof(checkpoint_tmp), "precursor-final.dump.tmp");
  output_path(metadata, sizeof(metadata), "precursor-final.dump.meta");
  output_path(cells, sizeof(cells), "precursor-transfer-cells.csv");
  output_path(cells_tmp, sizeof(cells_tmp), "precursor-transfer-cells.csv.tmp");
  output_path(export_metadata, sizeof(export_metadata),
              "precursor-transfer-unsealed.json");
  if (snprintf(closure, sizeof(closure), "%s.prediction-closure-v4",
               checkpoint) >= (int)sizeof(closure)) {
    fprintf(stderr, "ERROR precursor closure path exceeds buffer\n");
    exit(2);
  }
  require_new_output_file(checkpoint);
  require_new_output_file(checkpoint_tmp);
  require_new_output_file(metadata);
  require_new_output_file(cells);
  require_new_output_file(cells_tmp);
  require_new_output_file(export_metadata);
  require_new_output_file(closure);

  internal_nozzle_write_prediction_closure_v4(closure);
  dump(file = checkpoint_tmp);
  if (!regular_nonzero_file(checkpoint_tmp) || rename(checkpoint_tmp, checkpoint)) {
    fprintf(stderr, "ERROR failed to persist native precursor checkpoint\n");
    exit(2);
  }

  FILE *stream = fopen(cells_tmp, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create precursor transfer table\n");
    exit(2);
  }
  fputs("source_cell_id,x,y,z,Delta,cs,ux,uy,uz,p\n", stream);
  long cell_id = 0;
  foreach(serial) {
    if (cs[] > 1e-10) {
      fprintf(stream,
              "%ld,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
              cell_id, x, y, z, Delta, cs[], u.x[], u.y[], u.z[], p[]);
      cell_id++;
    }
  }
  if (fclose(stream) || rename(cells_tmp, cells)) {
    fprintf(stderr, "ERROR failed to persist precursor transfer table\n");
    exit(2);
  }
  write_target_transfer_samples();

  stream = fopen(metadata, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create precursor checkpoint sidecar\n");
    exit(2);
  }
  fprintf(stream,
          "schema=internal_nozzle_precursor_checkpoint_v2\n"
          "case_id=%s\n"
          "geometry_fingerprint=%s\n"
          "source_commit=%s\n"
          "source_sha256=%s\n"
          "maxlevel=%d\n"
          "pressure_forcing=%.17g\n"
          "density_liquid=%.17g\n"
          "viscosity_liquid=%.17g\n"
          "t=%.17g\n"
          "t_star=%.17g\n"
          "i=%d\n"
          "solver_dt=%.17g\n"
          "solver_dtmax=%.17g\n"
          "timestep_previous=%.17g\n"
          "previous_profile_available=%d\n"
          "prediction_closure_schema=internal_nozzle_prediction_closure_v4\n"
          "prediction_closure_state=precursor-final.dump.prediction-closure-v4\n",
          case_id, INTERNAL_NOZZLE_GEOMETRY_FINGERPRINT, source_commit,
          source_sha256, maxlevel, pressure_forcing, density_liquid,
          viscosity_liquid, t, t/geometry.hydraulic_diameter, iter_value,
          dt, dtmax, internal_nozzle_timestep_previous,
          previous_profile_available);
  fclose(stream);

  stream = fopen(export_metadata, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot create unsealed transfer metadata\n");
    exit(2);
  }
  const double domain_size = geometry.internal_dh*geometry.hydraulic_diameter;
  fprintf(stream,
          "{\n"
          "  \"schema\": \"%s\",\n"
          "  \"case_id\": \"%s\",\n"
          "  \"geometry_fingerprint\": \"%s\",\n"
          "  \"source_commit\": \"%s\",\n"
          "  \"source_sha256\": \"%s\",\n"
          "  \"checkpoint_file\": \"precursor-final.dump\",\n"
          "  \"checkpoint_metadata_file\": \"precursor-final.dump.meta\",\n"
          "  \"prediction_closure_file\": \"precursor-final.dump.prediction-closure-v4\",\n"
          "  \"cells_file\": \"precursor-transfer-cells.csv\",\n"
          "  \"history_file\": \"precursor_history.csv\",\n"
          "  \"target_template\": \"%s\",\n"
          "  \"target_samples_file\": \"%s\",\n"
          "  \"target_sampling_method\": \"%s\",\n"
          "  \"target_sample_columns\": [\"x\", \"y\", \"z\", \"level\", \"Delta\", \"cs\", \"f\", \"source_sample_x\", \"exit_clamped\", \"ux\", \"uy\", \"uz\", \"p\"],\n"
          "  \"target_exit_clamp_rule\": \"%s\",\n"
          "  \"target_exit_coordinate\": %.17g,\n"
          "  \"target_sample_count\": %ld,\n"
          "  \"target_exit_clamp_count\": %ld,\n"
          "  \"cell_count\": %ld,\n"
          "  \"domain_origin\": [0.0, %.17g, %.17g],\n"
          "  \"domain_size\": %.17g,\n"
          "  \"maxlevel\": %d,\n"
          "  \"delta_min_Dh\": %.17g,\n"
          "  \"pressure_forcing\": %.17g,\n"
          "  \"density_liquid\": %.17g,\n"
          "  \"viscosity_liquid\": %.17g,\n"
          "  \"t\": %.17g,\n"
          "  \"t_star\": %.17g,\n"
          "  \"field_state\": \"post_projection_terminal_native_checkpoint\",\n"
          "  \"steady_state\": \"unclassified_pending_deterministic_reducer\"\n"
          "}\n",
          INTERNAL_NOZZLE_TARGET_SAMPLE_SCHEMA,
          case_id, INTERNAL_NOZZLE_GEOMETRY_FINGERPRINT, source_commit,
          source_sha256,
          target_template[0] ? target_template : "not_applicable",
          target_template[0] ? "precursor-target-samples.csv" : "not_applicable",
          INTERNAL_NOZZLE_TARGET_SAMPLE_METHOD,
          INTERNAL_NOZZLE_TARGET_CLAMP_RULE,
          geometry.internal_dh*geometry.hydraulic_diameter,
          target_transfer_sample_count, target_transfer_exit_clamp_count,
          cell_id, -0.5*domain_size, -0.5*domain_size,
          domain_size, maxlevel,
          internal_nozzle_precursor_delta_dh(maxlevel), pressure_forcing,
          density_liquid, viscosity_liquid, t,
          t/geometry.hydraulic_diameter);
  fclose(stream);
}

int main (int argc, char **argv) {
  geometry = internal_nozzle_w2_geometry();
  parse_arguments(argc, argv);
  verify_arguments();
  copy_text(source_sha, sizeof(source_sha), source_sha256);
  ensure_output_directory();
  if (restore_checkpoint[0])
    verify_restore_sidecar();
  initialize_outputs();

  const double domain_size = geometry.internal_dh*geometry.hydraulic_diameter;
  size(domain_size);
  origin(0., -0.5*domain_size, -0.5*domain_size);
  init_grid(1 << baselevel);
  mu = muv;
  DT = timestep_cap;
  TOLERANCE = 1e-5;
  NITERMIN = 2;
  run();
}

event init (t = 0) {
  p.nodump = pf.nodump = false;
  f.nodump = previous_ux.nodump = previous_normalized_profile.nodump = false;
  for (scalar field in {f, u, p, pf, previous_ux,
                        previous_normalized_profile})
    field.third = true;
  if (restore_checkpoint[0]) {
    if (!restore(file = restore_checkpoint)) {
      fprintf(stderr, "ERROR native restore failed for %s\n",
              restore_checkpoint);
      exit(2);
    }
    restored = 1;
    build_geometry();
    boundary({f, u, p, pf, g, previous_ux, previous_normalized_profile});
    verify_restored_precursor_identity();
    previous_profile_available = expected_previous_profile_available;
    internal_nozzle_timestep_previous = expected_timestep_previous;
    pending_precursor_closure_restore = 1;
    return 0;
  }

  const double refine_half_band =
    0.6*geometry.plenum_scale*geometry.width;
  refine(fabs(y) < refine_half_band && fabs(z) < refine_half_band &&
         level < maxlevel);
  build_geometry();
  const double domain_size = geometry.internal_dh*geometry.hydraulic_diameter;
  foreach() {
    f[] = cs[];
    foreach_dimension()
      u.x[] = 0.;
    previous_ux[] = 0.;
    previous_normalized_profile[] = 0.;
    p[] = pressure_forcing*(1. - x/domain_size);
    pf[] = p[];
  }
  boundary({f, u, p, pf, previous_ux, previous_normalized_profile});
}

/* Restore the keyed face/centered prediction state after centered's setup and
 * immediately before the first resumed prediction, matching the validated
 * two-phase restart ordering. */
event stability (i++, last) {
  if (pending_precursor_closure_restore) {
    event("properties");
    boundary({f, u, p, pf, g, previous_ux, previous_normalized_profile});
    internal_nozzle_restore_prediction_closure_v4(precursor_closure_path);
    if (!precursor_same_double(dt, expected_restore_dt) ||
        !precursor_same_double(dtmax, expected_restore_dtmax) ||
        !precursor_same_double(internal_nozzle_timestep_previous,
                               expected_timestep_previous)) {
      fprintf(stderr, "ERROR precursor timestep closure restore mismatch\n");
      exit(2);
    }
    pending_precursor_closure_restore = 0;
  }
}

/* Registered after centered.h, so the row describes a completed projection. */
event precursor_metrics (i++, last) {
  /* A time-scheduled terminal event may run before this iteration event at
   * the same (t,i).  Make both writers idempotent so the retained history has
   * one authoritative row per state regardless of Basilisk event ordering. */
  if ((i == 0 || i % metric_stride == 0) &&
      last_metric_iteration != i)
    write_metric_row(i);
}

event logfile (i++) {
  if (i >= maximum_steps) {
    fprintf(stderr, "ERROR maximum step cap reached at i=%d t=%.17g\n", i, t);
    return 1;
  }
  double maximum_speed = 0.;
  foreach(reduction(max:maximum_speed))
    if (cs[] > 1e-10)
      maximum_speed = max(maximum_speed,
                          sqrt(sq(u.x[]) + sq(u.y[]) + sq(u.z[])));
  if (!isfinite(maximum_speed)) {
    fprintf(stderr, "ERROR nonfinite velocity at i=%d t=%.17g\n", i, t);
    return 1;
  }
}

event end (t = end_time) {
  if (last_metric_iteration != i)
    write_metric_row(i);
  write_checkpoint_and_transfer(i);
}
