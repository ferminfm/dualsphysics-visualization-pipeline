#ifndef INTERNAL_NOZZLE_PRECURSOR_START_H
#define INTERNAL_NOZZLE_PRECURSOR_START_H

/*
 * Optional fresh-state initialization for the steady-precursor audit.
 *
 * This header does not alter native dump/restore.  It is included by the
 * accepted two-phase source; its default mode is the historical zero-velocity
 * rest start.  A precursor start is admitted only from a table sampled on the
 * exact already-built target leaves.  The table is intentionally prepared by
 * deterministic tooling before launch, so the solver never guesses at field
 * interpolation or silently accepts partial coverage.
 */

enum InternalNozzleInitialState {
  INTERNAL_NOZZLE_REST_START = 0,
  INTERNAL_NOZZLE_PRECURSOR_START = 1
};

enum InternalNozzlePrecursorPressureMode {
  INTERNAL_NOZZLE_TRANSFER_PRESSURE = 0,
  INTERNAL_NOZZLE_VELOCITY_ONLY = 1
};

static int internal_nozzle_initial_state = INTERNAL_NOZZLE_REST_START;
static int internal_nozzle_precursor_pressure_mode =
  INTERNAL_NOZZLE_TRANSFER_PRESSURE;
static char internal_nozzle_transfer_path[1024] = "";
static char internal_nozzle_transfer_sha256[65] = "not_applicable";
static char internal_nozzle_transfer_template_path[1024] = "";
static long internal_nozzle_transfer_expected_cells = 0;
static long internal_nozzle_transfer_loaded_cells = 0;
static double internal_nozzle_profile_bulk_velocity = -1.;
static double internal_nozzle_profile_normalization = 1.;
static double internal_nozzle_profile_discrete_unit_bulk = -1.;

static const char * internal_nozzle_initial_state_label (void) {
  return internal_nozzle_initial_state == INTERNAL_NOZZLE_PRECURSOR_START ?
    "precursor_start" : "rest_start";
}

static const char * internal_nozzle_inlet_mode_label (void) {
#ifdef INTERNAL_NOZZLE_PROFILE_CONTROLLED
  return "poiseuille_profile_controlled_diagnostic";
#else
  return "pressure_driven";
#endif
}

static const char * internal_nozzle_precursor_pressure_mode_label (void) {
  if (internal_nozzle_initial_state != INTERNAL_NOZZLE_PRECURSOR_START)
    return "not_applicable";
  return internal_nozzle_precursor_pressure_mode ==
    INTERNAL_NOZZLE_TRANSFER_PRESSURE ? "transferred" : "velocity_only";
}

static int internal_nozzle_hex_string (const char * value, size_t length) {
  if (!value || strlen(value) != length)
    return 0;
  for (size_t k = 0; k < length; k++)
    if (!isxdigit((unsigned char) value[k]))
      return 0;
  return 1;
}

static int internal_nozzle_sha256_string (const char * value) {
  return internal_nozzle_hex_string(value, 64);
}

static const char * internal_nozzle_option_value
  (int argc, char ** argv, int * index)
{
  if (*index + 1 >= argc) {
    fprintf(stderr, "ERROR missing value after %s\n", argv[*index]);
    exit(2);
  }
  return argv[++(*index)];
}

/* Return one only for a recognized option. */
static int internal_nozzle_parse_precursor_option
  (int argc, char ** argv, int * index)
{
  const char * option = argv[*index];
  if (!strcmp(option, "--initial-state")) {
    const char * value = internal_nozzle_option_value(argc, argv, index);
    if (!strcmp(value, "rest"))
      internal_nozzle_initial_state = INTERNAL_NOZZLE_REST_START;
    else if (!strcmp(value, "precursor"))
      internal_nozzle_initial_state = INTERNAL_NOZZLE_PRECURSOR_START;
    else {
      fprintf(stderr, "ERROR --initial-state must be rest or precursor\n");
      exit(2);
    }
    return 1;
  }
  if (!strcmp(option, "--precursor-transfer")) {
    copy_string(internal_nozzle_transfer_path,
                sizeof(internal_nozzle_transfer_path),
                internal_nozzle_option_value(argc, argv, index));
    return 1;
  }
  if (!strcmp(option, "--precursor-transfer-sha256")) {
    copy_string(internal_nozzle_transfer_sha256,
                sizeof(internal_nozzle_transfer_sha256),
                internal_nozzle_option_value(argc, argv, index));
    return 1;
  }
  if (!strcmp(option, "--precursor-pressure-mode")) {
    const char * value = internal_nozzle_option_value(argc, argv, index);
    if (!strcmp(value, "transferred"))
      internal_nozzle_precursor_pressure_mode =
        INTERNAL_NOZZLE_TRANSFER_PRESSURE;
    else if (!strcmp(value, "velocity-only"))
      internal_nozzle_precursor_pressure_mode = INTERNAL_NOZZLE_VELOCITY_ONLY;
    else {
      fprintf(stderr,
              "ERROR --precursor-pressure-mode must be transferred or velocity-only\n");
      exit(2);
    }
    return 1;
  }
  if (!strcmp(option, "--write-transfer-template")) {
    copy_string(internal_nozzle_transfer_template_path,
                sizeof(internal_nozzle_transfer_template_path),
                internal_nozzle_option_value(argc, argv, index));
    return 1;
  }
  if (!strcmp(option, "--profile-bulk-velocity")) {
    internal_nozzle_profile_bulk_velocity = atof
      (internal_nozzle_option_value(argc, argv, index));
    return 1;
  }
  return 0;
}

static void internal_nozzle_print_precursor_usage (void) {
  fputs(
    "  --initial-state rest|precursor  fresh-state initialization (default rest)\n"
    "  --precursor-transfer PATH       exact target-grid u/p transfer CSV\n"
    "  --precursor-transfer-sha256 HEX preverified transfer-file SHA-256\n"
    "  --precursor-pressure-mode MODE transferred (primary) or velocity-only control\n"
    "  --write-transfer-template PATH  write internal target leaves and stop at t=0\n"
    "  --profile-bulk-velocity FLOAT   Case-C plenum bulk velocity\n",
    stdout);
}

static int internal_nozzle_validate_precursor_options
  (int restore_is_requested)
{
  if (internal_nozzle_transfer_template_path[0]) {
    if (restore_is_requested ||
        internal_nozzle_initial_state != INTERNAL_NOZZLE_REST_START ||
        internal_nozzle_transfer_path[0]) {
      fprintf(stderr,
              "ERROR transfer-template mode cannot restore or import a precursor\n");
      return 0;
    }
    return 1;
  }
  if (internal_nozzle_initial_state == INTERNAL_NOZZLE_PRECURSOR_START &&
      !internal_nozzle_sha256_string(internal_nozzle_transfer_sha256)) {
    fprintf(stderr,
            "ERROR precursor start requires a 64-hex transfer SHA-256 identity\n");
    return 0;
  }
  if (internal_nozzle_initial_state == INTERNAL_NOZZLE_PRECURSOR_START &&
      !restore_is_requested && !internal_nozzle_transfer_path[0]) {
    fprintf(stderr,
            "ERROR fresh precursor start requires --precursor-transfer\n");
    return 0;
  }
  /* A restored precursor segment keeps the exact transfer path in protected
   * argv as provenance.  The native checkpoint remains the only loaded state. */
  if (internal_nozzle_initial_state == INTERNAL_NOZZLE_REST_START &&
      internal_nozzle_transfer_path[0]) {
    fprintf(stderr, "ERROR precursor transfer supplied for rest start\n");
    return 0;
  }
  if (internal_nozzle_initial_state == INTERNAL_NOZZLE_REST_START &&
      strcmp(internal_nozzle_transfer_sha256, "not_applicable")) {
    fprintf(stderr, "ERROR transfer SHA-256 supplied for rest start\n");
    return 0;
  }
  if (internal_nozzle_initial_state == INTERNAL_NOZZLE_REST_START &&
      internal_nozzle_precursor_pressure_mode !=
      INTERNAL_NOZZLE_TRANSFER_PRESSURE) {
    fprintf(stderr, "ERROR precursor pressure mode supplied for rest start\n");
    return 0;
  }
#ifdef INTERNAL_NOZZLE_PROFILE_CONTROLLED
  if (internal_nozzle_initial_state != INTERNAL_NOZZLE_PRECURSOR_START ||
      !(internal_nozzle_profile_bulk_velocity > 0.)) {
    fprintf(stderr,
            "ERROR profile-controlled diagnostic requires precursor start and positive bulk velocity\n");
    return 0;
  }
#else
  if (internal_nozzle_profile_bulk_velocity > 0.) {
    fprintf(stderr,
            "ERROR --profile-bulk-velocity is only valid in profile-controlled build\n");
    return 0;
  }
#endif
  return 1;
}

#ifdef INTERNAL_NOZZLE_PROFILE_CONTROLLED
/* Fully-developed rectangular-duct series, normalized to unit bulk velocity.
 * W and H are the actual 2:1 plenum aperture dimensions at the inlet. */
static double internal_nozzle_poiseuille_unit_bulk (double yp, double zp) {
  double width = plenum_scale*Wrect;
  double height = plenum_scale*Hrect;
  if (fabs(yp) >= 0.5*width || fabs(zp) >= 0.5*height)
    return 0.;
  double value = 0., bulk = 0.;
  for (int n = 1; n <= 39; n += 2) {
    double nd = n;
    double sign = ((n - 1)/2) % 2 ? -1. : 1.;
    double argument = n*pi*width/(2.*height);
    double transverse = 1. - cosh(n*pi*yp/height)/cosh(argument);
    value += sign*transverse*cos(n*pi*zp/height)/(nd*nd*nd);
    bulk += 2./(pi*sq(sq(nd)))*
      (1. - 2.*height*tanh(argument)/(n*pi*width));
  }
  return bulk > 0. ? value/bulk : 0.;
}

static double internal_nozzle_profile_inlet_velocity
  (double yp, double zp)
{
  return internal_nozzle_profile_bulk_velocity*
    internal_nozzle_profile_normalization*
    internal_nozzle_poiseuille_unit_bulk(yp, zp);
}

/* Normalize the sampled boundary profile on the actual cut-face aperture.
 * The series has unit continuum bulk velocity, but a coarse embedded boundary
 * must not silently change the declared Case-C bulk-flow target. */
static void internal_nozzle_configure_profile_normalization (void) {
  double area = 0., unit_flow = 0.;
  foreach_boundary(left, reduction(+:area) reduction(+:unit_flow)) {
    double weight = fs.x[]*sq(Delta);
    if (weight > 0.) {
      area += weight;
      unit_flow += internal_nozzle_poiseuille_unit_bulk(y, z)*weight;
    }
  }
  if (!(area > 0.) || !(unit_flow > 0.)) {
    fprintf(stderr, "ERROR profile-controlled inlet aperture is empty\n");
    exit(2);
  }
  internal_nozzle_profile_discrete_unit_bulk = unit_flow/area;
  internal_nozzle_profile_normalization =
    1./internal_nozzle_profile_discrete_unit_bulk;
}
#endif

static void internal_nozzle_write_transfer_template (void) {
  FILE * stream = fopen(internal_nozzle_transfer_template_path, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot write transfer template %s\n",
            internal_nozzle_transfer_template_path);
    exit(2);
  }
  fputs("x,y,z,level,Delta,cs,f\n", stream);
  long count = 0;
  foreach(serial)
    if (cs[] > 1e-8 && f[] > 1e-8) {
      fprintf(stream, "%.17g,%.17g,%.17g,%d,%.17g,%.17g,%.17g\n",
              x, y, z, level, Delta, cs[], f[]);
      count++;
    }
  fclose(stream);
  if (!count) {
    fprintf(stderr, "ERROR empty transfer template\n");
    exit(2);
  }
  fprintf(stderr, "wrote exact target-grid transfer template with %ld leaves\n",
          count);
}

static int internal_nozzle_close_enough (double a, double b, double scale) {
  return fabs(a - b) <= 64.*DBL_EPSILON*max(1., scale);
}

static void internal_nozzle_load_precursor_transfer (void) {
  FILE * stream = fopen(internal_nozzle_transfer_path, "r");
  if (!stream) {
    fprintf(stderr, "ERROR cannot open precursor transfer %s\n",
            internal_nozzle_transfer_path);
    exit(2);
  }
  char line[2048];
  if (!fgets(line, sizeof(line), stream) ||
      strcmp(line, "x,y,z,level,Delta,cs,f,ux,uy,uz,p\n")) {
    fprintf(stderr, "ERROR incompatible precursor transfer header\n");
    exit(2);
  }
  long loaded = 0, expected = 0;
  /* The deterministic preparation tool preserves the target-template order.
   * Load in the identical serial leaf traversal so no coordinate lookup or
   * approximate remapping is possible inside the solver. */
  foreach(serial)
    if (cs[] > 1e-8 && f[] > 1e-8) {
    expected++;
    if (!fgets(line, sizeof(line), stream)) {
      fprintf(stderr, "ERROR precursor transfer ended before target leaf %ld\n", expected);
      exit(2);
    }
    double rx, ry, rz, rdelta, rcs, rf, ux, uy, uz, pressure;
    int rlevel;
    char trailing;
    int parsed = sscanf(line,
      "%lf,%lf,%lf,%d,%lf,%lf,%lf,%lf,%lf,%lf,%lf %c",
      &rx, &ry, &rz, &rlevel, &rdelta, &rcs, &rf,
      &ux, &uy, &uz, &pressure,
      &trailing);
    if (parsed != 11 || !isfinite(rx) || !isfinite(ry) || !isfinite(rz) ||
        !isfinite(rdelta) || !isfinite(rcs) || !isfinite(rf) ||
        !isfinite(ux) || !isfinite(uy) ||
        !isfinite(uz) || !isfinite(pressure)) {
      fprintf(stderr, "ERROR malformed/nonfinite precursor transfer row %ld\n",
              loaded + 2);
      exit(2);
    }
    if (level != rlevel || !internal_nozzle_close_enough(x, rx, rdelta) ||
        !internal_nozzle_close_enough(y, ry, rdelta) ||
        !internal_nozzle_close_enough(z, rz, rdelta) ||
        !internal_nozzle_close_enough(Delta, rdelta, rdelta) ||
        !internal_nozzle_close_enough(cs[], rcs, 1.) ||
        !internal_nozzle_close_enough(f[], rf, 1.)) {
      fprintf(stderr, "ERROR out-of-order/non-target precursor row %ld\n",
              loaded + 2);
      exit(2);
    }
    u.x[] = ux;
    u.y[] = uy;
    u.z[] = uz;
    if (internal_nozzle_precursor_pressure_mode ==
        INTERNAL_NOZZLE_TRANSFER_PRESSURE)
      p[] = pf[] = pressure;
    else
      p[] = pf[] = 0.;
    un[] = ux;
    loaded++;
  }
  if (fgets(line, sizeof(line), stream)) {
    fprintf(stderr, "ERROR precursor transfer contains rows beyond target coverage\n");
    exit(2);
  }
  fclose(stream);
  if (!expected || loaded != expected) {
    fprintf(stderr,
            "ERROR precursor transfer coverage loaded=%ld expected=%ld\n",
            loaded, expected);
    exit(2);
  }
  internal_nozzle_transfer_expected_cells = expected;
  internal_nozzle_transfer_loaded_cells = loaded;
  restriction({u, un, p, pf});
  boundary({u, un, p, pf});
}

static void internal_nozzle_write_initialization_contract (void) {
  char leaf[320], path[1024], temporary[1032];
  double profile_achieved_bulk_velocity = -1.;
  double profile_target_absolute_error = -1.;
  double profile_numerical_tolerance = -1.;
  int poiseuille_profile_validation_passed = 0;
#ifdef INTERNAL_NOZZLE_PROFILE_CONTROLLED
  profile_achieved_bulk_velocity = internal_nozzle_profile_bulk_velocity*
    internal_nozzle_profile_discrete_unit_bulk*
    internal_nozzle_profile_normalization;
  profile_target_absolute_error = fabs(profile_achieved_bulk_velocity -
                                       internal_nozzle_profile_bulk_velocity);
  profile_numerical_tolerance = 64.*DBL_EPSILON*
    max(1., fabs(internal_nozzle_profile_bulk_velocity));
  poiseuille_profile_validation_passed =
    isfinite(profile_achieved_bulk_velocity) &&
    internal_nozzle_profile_discrete_unit_bulk > 0. &&
    internal_nozzle_profile_normalization > 0. &&
    profile_target_absolute_error <= profile_numerical_tolerance;
  if (!poiseuille_profile_validation_passed) {
    fprintf(stderr, "ERROR sampled Poiseuille inlet does not preserve the bound bulk target\n");
    exit(2);
  }
#endif
  snprintf(leaf, sizeof(leaf), "initialization_contract.%s.json", segment_id);
  output_path(path, sizeof(path), leaf);
  if (lstat(path, &(struct stat){0}) == 0) {
    fprintf(stderr, "ERROR refusing to overwrite immutable initialization contract\n");
    exit(2);
  }
  if (snprintf(temporary, sizeof(temporary), "%s.tmp", path) >=
      (int)sizeof(temporary)) {
    fprintf(stderr, "ERROR initialization-contract path exceeds buffer\n");
    exit(2);
  }
  FILE * stream = fopen(temporary, "w");
  if (!stream) {
    fprintf(stderr, "ERROR cannot write initialization contract\n");
    exit(2);
  }
  fprintf(stream,
    "{\n"
    "  \"schema\": \"internal_nozzle_initialization_v2\",\n"
    "  \"execution_id\": \"%s\",\n"
    "  \"segment_id\": \"%s\",\n"
    "  \"case_role\": \"%s\",\n"
    "  \"case_id\": \"%s\",\n"
    "  \"scientific_source_commit\": \"%s\",\n"
    "  \"source_sha256\": \"%s\",\n"
    "  \"solver_sha256\": \"%s\",\n"
    "  \"schedule_version\": \"%s\",\n"
    "  \"schedule_sha256\": \"%s\",\n"
    "  \"segment_start\": \"%s\",\n"
    "  \"initial_state\": \"%s\",\n"
    "  \"inlet_mode\": \"%s\",\n"
    "  \"transfer_sha256\": \"%s\",\n"
    "  \"precursor_pressure_mode\": \"%s\",\n"
    "  \"expected_target_cells\": %ld,\n"
    "  \"loaded_target_cells\": %ld,\n"
    "  \"profile_bulk_velocity\": %.17g,\n"
    "  \"profile_discrete_unit_bulk\": %.17g,\n"
    "  \"profile_normalization\": %.17g,\n"
    "  \"profile_achieved_bulk_velocity\": %.17g,\n"
    "  \"profile_target_absolute_error\": %.17g,\n"
    "  \"profile_numerical_tolerance\": %.17g,\n"
    "  \"poiseuille_profile_validation_passed\": %s,\n"
    "  \"predecessor_segment_id\": \"%s\",\n"
    "  \"restore_checkpoint_sha256\": \"%s\",\n"
    "  \"restore_metadata_sha256\": \"%s\",\n"
    "  \"restore_closure_sha256\": \"%s\",\n"
    "  \"native_restore_unchanged\": true\n"
    "}\n",
    execution_id, segment_id, case_role, case_id, scientific_source_commit,
    source_sha, solver_sha256, schedule_version, schedule_sha,
    restore_requested ? "native_restore" : "fresh_initialization",
    internal_nozzle_initial_state_label(), internal_nozzle_inlet_mode_label(),
    internal_nozzle_transfer_sha256,
    internal_nozzle_precursor_pressure_mode_label(),
    internal_nozzle_transfer_expected_cells,
    internal_nozzle_transfer_loaded_cells,
    internal_nozzle_profile_bulk_velocity,
    internal_nozzle_profile_discrete_unit_bulk,
    internal_nozzle_profile_normalization,
    profile_achieved_bulk_velocity, profile_target_absolute_error,
    profile_numerical_tolerance,
    poiseuille_profile_validation_passed ? "true" : "false",
    predecessor_segment_id,
    restore_checkpoint_sha256, restore_metadata_sha256,
    restore_closure_sha256);
  fclose(stream);
  atomic_rename(temporary, path);
}

#endif
