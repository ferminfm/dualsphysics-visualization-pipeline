/*
 * Canonical bounded official/rectangular pulsed atomisation-family source.
 *
 * This source keeps the local Basilisk examples/atomisation.c control as the
 * circular default and adds area-matched 2:1 rectangular inlet-boundary profile
 * modes. The rectangular route imposes the profile at the inlet plane; it is
 * not an internal-nozzle-flow simulation.
 */

#include "navier-stokes/centered.h"
#include "two-phase.h"
#include "tension.h"
#include "tag.h"
#include "view.h"
#include <ctype.h>
#include <errno.h>
#include <float.h>
#include <string.h>
#include <sys/stat.h>

enum {
  MODE_ROUND_OFFICIAL_TOP_HAT = 0,
  MODE_RECT_AREA_TOP_HAT = 1,
  MODE_RECT_AREA_SEPARABLE_PARABOLIC = 2,
  MODE_RECT_AREA_POISSEUILLE_SERIES = 3
};

double radius = 1./12.;
double initial_length = 0.025;
double Re = 5800.;
double SIGMA = 3e-5;
double u0 = 1.;
double pulse_amplitude = 0.05;
double T0 = 0.1;
double end_time = 0.18;
double output_dt = 0.02;
double facet_dt = 0.02;
double raw_dt = 0.02;
double checkpoint_dt = 0.06;
double uemax = 0.1;
double tag_threshold = 1e-3;
double interface_threshold = 1e-6;
double min_component_cell_factor = 4.;
double restore_time = -1.;
double poisseuille_raw_mean = 1.;
double A0 = 0.;
double rect_W = 0.;
double rect_H = 0.;
double rect_half_W = 0.;
double rect_half_H = 0.;
double rect_Dh = 0.;

int maxlevel = 7;
int max_steps = 12000;
int mode = MODE_ROUND_OFFICIAL_TOP_HAT;
int enable_native_frames = 1;
int enable_facet_export = 1;
int enable_raw_export = 1;
int enable_checkpoints = 1;
int auto_restore = 0;
int restore_requested = 0;
int restored_ok = 0;
int visual_frame_index = 0;
int surface_frame_index = 0;
int raw_frame_index = 0;
int checkpoint_index = 0;
int stable_flag = 1;
int wrote_final_summary = 0;
int poisseuille_terms = 61;
int poisseuille_norm_ny = 240;
int poisseuille_norm_nz = 120;
int last_iter = 0;

double final_liquid_volume = 0.;
double initial_liquid_volume = -1.;
double final_liquid_volume_error = 0.;
double max_active_front = 0.;
double max_interface_proxy = 0.;
double initial_interface_proxy = 0.;
double max_interface_growth = 1.;
int max_tag_count = 0;
int max_credible_component_count = 0;
int max_detached_proxy_count = 0;

char case_id[128] = "canonical_round_official_top_hat";
char sanitized_case_id[128] = "canonical_round_official_top_hat";
char output_dir[512] = ".";
char frames_dir[640] = "";
char surfaces_dir[640] = "";
char checkpoints_dir[640] = "";
char restore_path[512] = "";
char restored_from[512] = "";
char camera_preset[64] = "official_iso";

scalar f0[];

static double clamp0 (double a) {
  return a < 0. ? 0. : a;
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

static int file_exists_nonzero (const char *path) {
  struct stat st;
  return stat(path, &st) == 0 && st.st_size > 0;
}

static void ensure_dir_recursive (const char *path) {
  char tmp[1024];
  copy_string(tmp, sizeof(tmp), path);
  size_t len = strlen(tmp);
  if (len == 0)
    return;
  if (tmp[len - 1] == '/')
    tmp[len - 1] = '\0';
  for (char *p = tmp + 1; *p; p++) {
    if (*p == '/') {
      *p = '\0';
      if (mkdir(tmp, 0775) != 0 && errno != EEXIST) {
        fprintf(stderr, "ERROR cannot create directory %s: %s\n", tmp, strerror(errno));
        exit(2);
      }
      *p = '/';
    }
  }
  if (mkdir(tmp, 0775) != 0 && errno != EEXIST) {
    fprintf(stderr, "ERROR cannot create directory %s: %s\n", tmp, strerror(errno));
    exit(2);
  }
}

static void output_path (char *buf, int n, const char *leaf) {
  snprintf(buf, n, "%s/%s", output_dir, leaf);
}

static void subdir_path (char *buf, int n, const char *dir, const char *leaf) {
  snprintf(buf, n, "%s/%s", dir, leaf);
}

static void atomic_rename (const char *tmp, const char *dst) {
  if (rename(tmp, dst) != 0) {
    fprintf(stderr, "ERROR cannot rename %s to %s: %s\n", tmp, dst, strerror(errno));
    exit(2);
  }
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

static const char * mode_name (void) {
  if (mode == MODE_ROUND_OFFICIAL_TOP_HAT)
    return "round_official_top_hat";
  if (mode == MODE_RECT_AREA_TOP_HAT)
    return "rect_area_top_hat";
  if (mode == MODE_RECT_AREA_SEPARABLE_PARABOLIC)
    return "rect_area_separable_parabolic";
  return "rect_area_poisseuille_series";
}

static int mode_is_rectangular (void) {
  return mode != MODE_ROUND_OFFICIAL_TOP_HAT;
}

static double hydraulic_diameter (double w, double h) {
  return 2.*w*h/(w + h);
}

static void compute_geometry_constants (void) {
  A0 = pi*sq(radius);
  rect_H = sqrt(A0/2.);
  rect_W = 2.*rect_H;
  rect_half_W = rect_W/2.;
  rect_half_H = rect_H/2.;
  rect_Dh = hydraulic_diameter(rect_W, rect_H);
}

static double aperture_phi (double yy, double zz) {
  if (!mode_is_rectangular())
    return sq(radius) - sq(yy) - sq(zz);
  return radius*min(rect_half_W - fabs(yy), rect_half_H - fabs(zz));
}

static int inside_rectangle (double yy, double zz) {
  return fabs(yy) <= rect_half_W && fabs(zz) <= rect_half_H;
}

static int strictly_inside_rectangle (double yy, double zz) {
  return fabs(yy) < rect_half_W && fabs(zz) < rect_half_H;
}

static double bulk_velocity (double tt) {
  return u0*(1. + pulse_amplitude*sin(2.*pi*tt/T0));
}

static double separable_parabolic_profile (double yy, double zz) {
  if (!inside_rectangle(yy, zz))
    return 0.;
  double yn = yy/rect_half_W;
  double zn = zz/rect_half_H;
  return (9./4.)*clamp0(1. - yn*yn)*clamp0(1. - zn*zn);
}

static double poisseuille_raw_profile (double yy, double zz) {
  if (!inside_rectangle(yy, zz))
    return 0.;
  double a = rect_half_W;
  double b = rect_half_H;
  double sum = 0.;
  for (int k = 0; k < poisseuille_terms; k++) {
    int n = 2*k + 1;
    double sign = (k % 2) ? -1. : 1.;
    double nd = (double)n;
    double denom = cosh(nd*pi*b/(2.*a));
    double wall = 1. - cosh(nd*pi*zz/(2.*a))/denom;
    double mode_y = cos(nd*pi*yy/(2.*a));
    sum += sign*wall*mode_y/(nd*nd*nd);
  }
  return sum;
}

static double inlet_profile (double yy, double zz) {
  if (mode == MODE_ROUND_OFFICIAL_TOP_HAT)
    return sq(yy) + sq(zz) <= sq(radius) + 1e-14 ? 1. : 0.;
  if (mode == MODE_RECT_AREA_TOP_HAT)
    return strictly_inside_rectangle(yy, zz) ? 1. : 0.;
  if (mode == MODE_RECT_AREA_SEPARABLE_PARABOLIC)
    return separable_parabolic_profile(yy, zz);
  if (poisseuille_raw_mean <= 0.)
    return 0.;
  return clamp0(poisseuille_raw_profile(yy, zz)/poisseuille_raw_mean);
}

static void compute_poisseuille_normalization (void) {
  if (mode != MODE_RECT_AREA_POISSEUILLE_SERIES) {
    poisseuille_raw_mean = 1.;
    return;
  }
  double sum = 0.;
  for (int iy = 0; iy < poisseuille_norm_ny; iy++) {
    double yy = -rect_half_W + (iy + 0.5)*rect_W/poisseuille_norm_ny;
    for (int iz = 0; iz < poisseuille_norm_nz; iz++) {
      double zz = -rect_half_H + (iz + 0.5)*rect_H/poisseuille_norm_nz;
      sum += poisseuille_raw_profile(yy, zz);
    }
  }
  poisseuille_raw_mean = sum/(poisseuille_norm_ny*poisseuille_norm_nz);
  if (!(poisseuille_raw_mean > 0.)) {
    fprintf(stderr, "ERROR invalid Poiseuille-series mean %.12g\n", poisseuille_raw_mean);
    exit(2);
  }
}

u.n[left]  = dirichlet(f0[]*bulk_velocity(t)*inlet_profile(y,z));
u.t[left]  = dirichlet(0);
#if dimension > 2
u.r[left]  = dirichlet(0);
#endif
p[left]    = neumann(0);
f[left]    = f0[];

u.n[right] = neumann(0);
p[right]   = dirichlet(0);

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
  char line[4096], last_file[512] = "";
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return 0;
  }
  while (fgets(line, sizeof(line), fp)) {
    char ccase[128], cmode[128], file[512], parent[512];
    int idx = 0, iter_value = 0, level_value = 0;
    double tt = 0.;
    if (sscanf(line, "%127[^,],%127[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
               ccase, cmode, &idx, &tt, &iter_value, &level_value, file, parent) >= 7)
      copy_string(last_file, sizeof(last_file), file);
  }
  fclose(fp);
  if (last_file[0] && file_exists_nonzero(last_file)) {
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
  double found = -1.;
  if (!fgets(line, sizeof(line), fp)) {
    fclose(fp);
    return -1.;
  }
  while (fgets(line, sizeof(line), fp)) {
    char ccase[128], cmode[128], file[512], parent[512];
    int idx = 0, iter_value = 0, level_value = 0;
    double tt = 0.;
    if (sscanf(line, "%127[^,],%127[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
               ccase, cmode, &idx, &tt, &iter_value, &level_value, file, parent) >= 7 &&
        !strcmp(file, checkpoint))
      found = tt;
  }
  fclose(fp);
  return found;
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

static void ensure_output_dirs (void) {
  sanitize_case_id();
  snprintf(frames_dir, sizeof(frames_dir), "%s/native_frames", output_dir);
  snprintf(surfaces_dir, sizeof(surfaces_dir), "%s/vof_surfaces", output_dir);
  snprintf(checkpoints_dir, sizeof(checkpoints_dir), "%s/checkpoints", output_dir);
  ensure_dir_recursive(output_dir);
  ensure_dir_recursive(frames_dir);
  ensure_dir_recursive(surfaces_dir);
  ensure_dir_recursive(checkpoints_dir);
}

static void initialize_output_files (void) {
  char path[1024];
  output_path(path, sizeof(path), "raw_frame_summary.csv");
  write_header_if_missing(path, "case_id,profile_mode,frame_index,t,i,maxlevel,grid_cells,liquid_volume,liquid_volume_error,active_front,active_front_over_L0,interface_proxy,interface_growth,mean_inlet_velocity,expected_mass_flow,tag_count,credible_component_count,detached_proxy_count,largest_component_volume\n");
  output_path(path, sizeof(path), "raw_component_summary.csv");
  write_header_if_missing(path, "case_id,profile_mode,frame_index,t,component_id,volume,cell_count,centroid_x,centroid_y,centroid_z,min_x,max_x,credible,detached_proxy\n");
  output_path(path, sizeof(path), "raw_interface_cells.csv");
  write_header_if_missing(path, "case_id,profile_mode,frame_index,t,x,y,z,f,ux,uy,uz,level,Delta\n");
  output_path(path, sizeof(path), "visual_frame_manifest.csv");
  write_header_if_missing(path, "case_id,profile_mode,frame_index,t,i,filename,format,camera,maxlevel\n");
  output_path(path, sizeof(path), "surface_manifest.csv");
  write_header_if_missing(path, "case_id,profile_mode,surface_index,t,i,filename,facet_cell_count,maxlevel,source_frame_id\n");
  output_path(path, sizeof(path), "checkpoint_index.csv");
  write_header_if_missing(path, "case_id,profile_mode,checkpoint_index,t,i,maxlevel,filename,parent_checkpoint\n");
}

static void write_visual_manifest_json (void) {
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
          "  \"profile_mode\": \"%s\",\n"
          "  \"native_frame_output_ready\": %s,\n"
          "  \"native_frame_method\": \"Basilisk view draw_vof(f)\",\n"
          "  \"frames\": [\n",
          case_id, mode_name(), enable_native_frames ? "true" : "false");
  int count = 0;
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], cmode[128], filename[512], format[32], camera[64];
      int idx = 0, iter_value = 0, level_value = 0;
      double tt = 0.;
      if (sscanf(line, "%127[^,],%127[^,],%d,%lf,%d,%511[^,],%31[^,],%63[^,],%d",
                 ccase, cmode, &idx, &tt, &iter_value, filename, format, camera, &level_value) == 9) {
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"frame_index\": %d, \"time\": %.12g, \"iteration\": %d, \"filename\": \"%s\", \"format\": \"%s\", \"camera\": \"%s\", \"maxlevel\": %d}",
                idx, tt, iter_value, filename, format, camera, level_value);
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"frame_count\": %d\n}\n", count);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void write_surface_manifest_json (void) {
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
          "  \"profile_mode\": \"%s\",\n"
          "  \"surface_export_ready\": %s,\n"
          "  \"surface_export_method\": \"Basilisk output_facets(f)\",\n"
          "  \"topology_cleanup_operations\": \"none\",\n"
          "  \"surfaces\": [\n",
          case_id, mode_name(), enable_facet_export ? "true" : "false");
  int count = 0;
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], cmode[128], filename[512], source_frame[64];
      int idx = 0, iter_value = 0, level_value = 0, facet_cells = 0;
      double tt = 0.;
      if (sscanf(line, "%127[^,],%127[^,],%d,%lf,%d,%511[^,],%d,%d,%63[^\n]",
                 ccase, cmode, &idx, &tt, &iter_value, filename, &facet_cells, &level_value, source_frame) == 9) {
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"surface_index\": %d, \"time\": %.12g, \"iteration\": %d, \"filename\": \"%s\", \"facet_cell_count\": %d, \"maxlevel\": %d, \"source_frame_id\": \"%s\"}",
                idx, tt, iter_value, filename, facet_cells, level_value, source_frame);
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"surface_count\": %d\n}\n", count);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void write_checkpoint_manifest_json (void) {
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
          "  \"profile_mode\": \"%s\",\n"
          "  \"checkpoint_restore_supported\": true,\n"
          "  \"checkpoints\": [\n",
          case_id, mode_name());
  int count = 0;
  char latest[512] = "";
  if (in) {
    char line[4096];
    fgets(line, sizeof(line), in);
    while (fgets(line, sizeof(line), in)) {
      char ccase[128], cmode[128], filename[512], parent[512];
      int idx = 0, iter_value = 0, level_value = 0;
      double tt = 0.;
      if (sscanf(line, "%127[^,],%127[^,],%d,%lf,%d,%d,%511[^,],%511[^\n]",
                 ccase, cmode, &idx, &tt, &iter_value, &level_value, filename, parent) >= 7) {
        copy_string(latest, sizeof(latest), filename);
        if (count)
          fputs(",\n", out);
        fprintf(out,
                "    {\"checkpoint_index\": %d, \"time\": %.12g, \"iteration\": %d, \"maxlevel\": %d, \"filename\": \"%s\", \"parent_checkpoint\": \"%s\", \"verified_nonzero\": %s}",
                idx, tt, iter_value, level_value, filename, parent, file_exists_nonzero(filename) ? "true" : "false");
        count++;
      }
    }
    fclose(in);
  }
  fprintf(out, "\n  ],\n  \"checkpoint_count\": %d,\n  \"latest_checkpoint_file\": \"%s\"\n}\n", count, latest);
  fclose(out);
  atomic_rename(tmp, manifest);
}

static void write_all_manifests (void) {
  write_visual_manifest_json();
  write_surface_manifest_json();
  write_checkpoint_manifest_json();
}

static void write_native_frame (int iter_value) {
  char leaf[256], path[1024], rel[768];
  snprintf(leaf, sizeof(leaf), "native_vof_%04d.ppm", visual_frame_index);
  subdir_path(path, sizeof(path), frames_dir, leaf);
  snprintf(rel, sizeof(rel), "native_frames/%s", leaf);

  clear();
  if (!strcmp(camera_preset, "side"))
    view(width = 1280, height = 720, fov = 14.5, tx = -0.42, ty = 0., bg = {1,1,1});
  else
    view(camera = "iso", fov = 14.5, tx = -0.418, ty = 0.288,
         width = 1280, height = 720, bg = {1,1,1});
  draw_vof("f");
  box();
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
  fprintf(fp, "%s,%s,%d,%.12g,%d,%s,ppm,%s,%d\n",
          case_id, mode_name(), visual_frame_index, t, iter_value, rel, camera_preset, maxlevel);
  fclose(fp);
  write_visual_manifest_json();
  visual_frame_index++;
}

static int interface_facet_cell_count (void) {
  int count = 0;
  foreach(reduction(+:count))
    if (f[] > interface_threshold && f[] < 1. - interface_threshold)
      count++;
  return count;
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
  fprintf(fp, "# case_id=%s\n# profile_mode=%s\n# time=%.12g\n# iteration=%d\n",
          case_id, mode_name(), t, iter_value);
  fprintf(fp, "# coordinate_convention=x_streamwise_y_width_z_height\n");
  fprintf(fp, "# topology_cleanup_operations=none\n# source_frame_id=%s\n", source_frame);
  output_facets(f, fp);
  fclose(fp);

  char manifest_csv[1024];
  output_path(manifest_csv, sizeof(manifest_csv), "surface_manifest.csv");
  FILE *mf = fopen(manifest_csv, "a");
  if (!mf) {
    fprintf(stderr, "ERROR cannot append %s\n", manifest_csv);
    exit(2);
  }
  fprintf(mf, "%s,%s,%d,%.12g,%d,%s,%d,%d,%s\n",
          case_id, mode_name(), surface_frame_index, t, iter_value, rel,
          facet_cells, maxlevel, source_frame);
  fclose(mf);
  write_surface_manifest_json();
  surface_frame_index++;
}

static void write_checkpoint_dump (int iter_value) {
  char leaf[256], path[1024], parent[512] = "fresh";
  if (restored_ok && restored_from[0])
    copy_string(parent, sizeof(parent), restored_from);
  snprintf(leaf, sizeof(leaf), "%s_%s_t%09.6f_i%07d_l%d.dump",
           sanitized_case_id, mode_name(), t, iter_value, maxlevel);
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
          case_id, mode_name(), checkpoint_index, t, iter_value, maxlevel, path, parent);
  fclose(fp);
  write_checkpoint_manifest_json();
  checkpoint_index++;
}

static double liquid_volume_total (void) {
  double vol = 0.;
  foreach(reduction(+:vol))
    vol += f[]*dv()/cube(L0);
  return vol;
}

static double interface_proxy_now (void) {
  double proxy = 0.;
  foreach(reduction(+:proxy))
    if (f[] > 1e-3 && f[] < 1. - 1e-3)
      proxy += sq(Delta)/sq(L0);
  return proxy;
}

static double active_front_now (void) {
  double af = 0.;
  foreach(reduction(max:af))
    if (f[] > tag_threshold)
      af = max(af, x/L0);
  return af;
}

static void write_raw_interface_cells (void) {
  if (!enable_raw_export)
    return;
  char path[1024];
  output_path(path, sizeof(path), "raw_interface_cells.csv");
  FILE *fp = fopen(path, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append %s\n", path);
    exit(2);
  }
  foreach(serial) {
    double uz = 0.;
#if dimension > 2
    uz = u.z[];
#endif
    if (f[] > interface_threshold && f[] < 1. - interface_threshold)
      fprintf(fp, "%s,%s,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%.12g\n",
              case_id, mode_name(), raw_frame_index, t, x, y, z, f[],
              u.x[], u.y[], uz, level, Delta);
  }
  fclose(fp);
}

static void write_component_and_frame_diagnostics (int iter_value) {
  double liquid_volume = liquid_volume_total();
  if (initial_liquid_volume < 0.)
    initial_liquid_volume = liquid_volume;
  final_liquid_volume = liquid_volume;
  final_liquid_volume_error = initial_liquid_volume > 0. ?
    fabs(liquid_volume - initial_liquid_volume)/initial_liquid_volume : 0.;

  double active_front = active_front_now();
  double interface_proxy = interface_proxy_now();
  if (initial_interface_proxy <= 0. && interface_proxy > 0.)
    initial_interface_proxy = interface_proxy;
  double interface_growth = initial_interface_proxy > 0. ? interface_proxy/initial_interface_proxy : 1.;
  max_active_front = max(max_active_front, active_front);
  max_interface_proxy = max(max_interface_proxy, interface_proxy);
  max_interface_growth = max(max_interface_growth, interface_growth);

  scalar m[];
  foreach()
    m[] = f[] > tag_threshold;
  int n = tag(m);
  int credible_count = 0;
  int detached_count = 0;
  double largest = 0.;
  char component_path[1024];
  output_path(component_path, sizeof(component_path), "raw_component_summary.csv");
  FILE *cp = fopen(component_path, "a");
  if (!cp) {
    fprintf(stderr, "ERROR cannot append %s\n", component_path);
    exit(2);
  }
  if (n > 0) {
    double volume[n], bx[n], by[n], bz[n], minx[n], maxx[n];
    int cells[n];
    for (int j = 0; j < n; j++) {
      volume[j] = bx[j] = by[j] = bz[j] = 0.;
      minx[j] = 1e30;
      maxx[j] = -1e30;
      cells[j] = 0;
    }
    foreach(serial) {
      if (m[] > 0) {
        int j = ((int)m[]) - 1;
        double vv = dv()*f[]/cube(L0);
        double xn = x/L0, yn = y/L0, zn = z/L0;
        volume[j] += vv;
        bx[j] += vv*xn;
        by[j] += vv*yn;
#if dimension > 2
        bz[j] += vv*zn;
#endif
        if (xn < minx[j]) minx[j] = xn;
        if (xn > maxx[j]) maxx[j] = xn;
        cells[j]++;
      }
    }
#if _MPI
    MPI_Allreduce(MPI_IN_PLACE, volume, n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, bx, n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, by, n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, bz, n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, minx, n, MPI_DOUBLE, MPI_MIN, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, maxx, n, MPI_DOUBLE, MPI_MAX, MPI_COMM_WORLD);
    MPI_Allreduce(MPI_IN_PLACE, cells, n, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
#endif
    double min_credible_volume = min_component_cell_factor*cube(1./(1 << maxlevel));
    double initial_length_over_L0 = initial_length/L0;
    for (int j = 0; j < n; j++) {
      if (volume[j] > largest)
        largest = volume[j];
      double cx = volume[j] > 0. ? bx[j]/volume[j] : 0.;
      double cy = volume[j] > 0. ? by[j]/volume[j] : 0.;
      double cz = volume[j] > 0. ? bz[j]/volume[j] : 0.;
      int credible = volume[j] >= min_credible_volume && cells[j] > 1;
      int detached = credible && minx[j] > initial_length_over_L0;
      if (credible)
        credible_count++;
      if (detached)
        detached_count++;
      fprintf(cp, "%s,%s,%d,%.12g,%d,%.12g,%d,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d\n",
              case_id, mode_name(), raw_frame_index, t, j, volume[j], cells[j],
              cx, cy, cz, minx[j], maxx[j], credible, detached);
    }
  }
  fclose(cp);

  max_tag_count = max(max_tag_count, n);
  max_credible_component_count = max(max_credible_component_count, credible_count);
  max_detached_proxy_count = max(max_detached_proxy_count, detached_count);

  char frame_path[1024];
  output_path(frame_path, sizeof(frame_path), "raw_frame_summary.csv");
  FILE *fp = fopen(frame_path, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append %s\n", frame_path);
    exit(2);
  }
  double mean_u = bulk_velocity(t);
  double expected_mass_flow = A0*mean_u;
  fprintf(fp, "%s,%s,%d,%.12g,%d,%d,%ld,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d,%d,%d,%.12g\n",
          case_id, mode_name(), raw_frame_index, t, iter_value, maxlevel, grid->tn,
          liquid_volume, final_liquid_volume_error, active_front, active_front,
          interface_proxy, interface_growth, mean_u, expected_mass_flow,
          n, credible_count, detached_count, largest);
  fclose(fp);
}

static void write_final_summary_once (void) {
  if (wrote_final_summary)
    return;
  wrote_final_summary = 1;
  char path[1024];
  output_path(path, sizeof(path), "canonical_pipeline_case_summary.json");
  FILE *fp = fopen(path, "w");
  if (!fp) {
    fprintf(stderr, "ERROR cannot write %s\n", path);
    exit(2);
  }
  fprintf(fp,
          "{\n"
          "  \"case_id\": \"%s\",\n"
          "  \"profile_mode\": \"%s\",\n"
          "  \"rectangular_route_is_inlet_boundary_imposed\": %s,\n"
          "  \"official_control_defaults\": {\"radius\": %.12g, \"initial_length\": %.12g, \"Re\": %.12g, \"sigma\": %.12g, \"density_ratio\": 27.84, \"u0\": %.12g, \"pulse_amplitude\": %.12g, \"pulse_period\": %.12g},\n"
          "  \"geometry\": {\"A0\": %.12g, \"W\": %.12g, \"H\": %.12g, \"half_W\": %.12g, \"half_H\": %.12g, \"Dh\": %.12g},\n"
          "  \"profile\": {\"poisseuille_terms\": %d, \"poisseuille_raw_mean\": %.12g},\n"
          "  \"run\": {\"t\": %.12g, \"i\": %d, \"maxlevel\": %d, \"end_time\": %.12g, \"stable_flag\": %d, \"restored_from\": \"%s\"},\n"
          "  \"outputs\": {\"native_frame_output_ready\": %s, \"surface_export_ready\": %s, \"checkpoint_restore_supported\": true, \"raw_export_enabled\": %s},\n"
          "  \"diagnostics\": {\"liquid_volume\": %.12g, \"liquid_volume_error\": %.12g, \"max_active_front\": %.12g, \"max_interface_proxy\": %.12g, \"max_interface_growth\": %.12g, \"max_tag_count\": %d, \"max_credible_component_count\": %d, \"max_detached_proxy_count\": %d},\n"
          "  \"claim_boundary\": \"internal bounded benchmark source only; not validation, production CFD, stationary spray data, internal-nozzle simulation, public media, or fit-ready calibration\"\n"
          "}\n",
          case_id, mode_name(), mode_is_rectangular() ? "true" : "false",
          radius, initial_length, Re, SIGMA, u0, pulse_amplitude, T0,
          A0, rect_W, rect_H, rect_half_W, rect_half_H, rect_Dh,
          poisseuille_terms, poisseuille_raw_mean, t, last_iter, maxlevel, end_time,
          stable_flag, restored_from[0] ? restored_from : "",
          enable_native_frames ? "true" : "false",
          enable_facet_export ? "true" : "false",
          enable_raw_export ? "true" : "false",
          final_liquid_volume, final_liquid_volume_error, max_active_front,
          max_interface_proxy, max_interface_growth, max_tag_count,
          max_credible_component_count, max_detached_proxy_count);
  fclose(fp);
  write_all_manifests();
}

static const char * require_value (int argc, char **argv, int *i) {
  if (*i + 1 >= argc) {
    fprintf(stderr, "ERROR missing value after %s\n", argv[*i]);
    exit(2);
  }
  (*i)++;
  return argv[*i];
}

static int parse_bool_arg (const char *s) {
  if (!strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "yes") || !strcmp(s, "on"))
    return 1;
  if (!strcmp(s, "0") || !strcmp(s, "false") || !strcmp(s, "no") || !strcmp(s, "off"))
    return 0;
  fprintf(stderr, "ERROR expected boolean 0|1, got %s\n", s);
  exit(2);
}

static void set_mode_from_string (const char *v) {
  if (!strcmp(v, "round_official_top_hat"))
    mode = MODE_ROUND_OFFICIAL_TOP_HAT;
  else if (!strcmp(v, "rect_area_top_hat"))
    mode = MODE_RECT_AREA_TOP_HAT;
  else if (!strcmp(v, "rect_area_separable_parabolic"))
    mode = MODE_RECT_AREA_SEPARABLE_PARABOLIC;
  else if (!strcmp(v, "rect_area_poisseuille_series") ||
           !strcmp(v, "rect_area_poiseuille_series"))
    mode = MODE_RECT_AREA_POISSEUILLE_SERIES;
  else {
    fprintf(stderr, "ERROR unknown profile mode %s\n", v);
    exit(2);
  }
}

static void print_usage (const char *prog) {
  fprintf(stdout,
          "usage: %s [options]\n"
          "\n"
          "Canonical bounded official/rectangular pulsed atomisation-family source.\n"
          "\n"
          "Options:\n"
          "  --case-id STR\n"
          "  --profile-mode round_official_top_hat|rect_area_top_hat|rect_area_separable_parabolic|rect_area_poisseuille_series\n"
          "  --maxlevel INT\n"
          "  --end-time FLOAT\n"
          "  --output-dt FLOAT\n"
          "  --facet-dt FLOAT\n"
          "  --raw-dt FLOAT\n"
          "  --checkpoint-dt FLOAT\n"
          "  --uemax FLOAT\n"
          "  --u0 FLOAT\n"
          "  --pulse-amplitude FLOAT\n"
          "  --pulse-period FLOAT\n"
          "  --output-dir PATH\n"
          "  --restore PATH\n"
          "  --auto-restore 0|1\n"
          "  --max-steps INT\n"
          "  --tag-threshold FLOAT\n"
          "  --interface-threshold FLOAT\n"
          "  --native-frames 0|1\n"
          "  --facet-export 0|1\n"
          "  --raw-export 0|1\n"
          "  --checkpoints 0|1\n"
          "  --poisseuille-terms INT\n"
          "\n",
          prog);
}

static void parse_args (int argc, char **argv) {
  for (int a = 1; a < argc; a++) {
    if (!strcmp(argv[a], "--help") || !strcmp(argv[a], "-h")) {
      print_usage(argv[0]);
      exit(0);
    }
    else if (!strcmp(argv[a], "--case-id"))
      copy_string(case_id, sizeof(case_id), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--profile-mode") || !strcmp(argv[a], "--aperture-profile"))
      set_mode_from_string(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--maxlevel"))
      maxlevel = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--end-time"))
      end_time = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--output-dt"))
      output_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--facet-dt"))
      facet_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--raw-dt"))
      raw_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--checkpoint-dt"))
      checkpoint_dt = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--uemax"))
      uemax = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--u0"))
      u0 = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--pulse-amplitude"))
      pulse_amplitude = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--pulse-period"))
      T0 = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--output-dir"))
      copy_string(output_dir, sizeof(output_dir), require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--restore")) {
      copy_string(restore_path, sizeof(restore_path), require_value(argc, argv, &a));
      restore_requested = 1;
    }
    else if (!strcmp(argv[a], "--auto-restore"))
      auto_restore = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--max-steps"))
      max_steps = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--tag-threshold"))
      tag_threshold = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--interface-threshold"))
      interface_threshold = atof(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--native-frames"))
      enable_native_frames = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--facet-export"))
      enable_facet_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--raw-export"))
      enable_raw_export = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--checkpoints"))
      enable_checkpoints = parse_bool_arg(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--poisseuille-terms") || !strcmp(argv[a], "--poiseuille-terms"))
      poisseuille_terms = atoi(require_value(argc, argv, &a));
    else if (!strcmp(argv[a], "--camera"))
      copy_string(camera_preset, sizeof(camera_preset), require_value(argc, argv, &a));
    else {
      fprintf(stderr, "ERROR unknown option %s\n", argv[a]);
      print_usage(argv[0]);
      exit(2);
    }
  }
}

int main (int argc, char **argv) {
  parse_args(argc, argv);
  compute_geometry_constants();
  if (T0 <= 0. || output_dt <= 0. || raw_dt <= 0. || facet_dt <= 0.) {
    fprintf(stderr, "ERROR cadences and pulse period must be positive\n");
    exit(2);
  }
  if (u0*(1. - fabs(pulse_amplitude)) < 0.) {
    fprintf(stderr, "ERROR pulse settings allow negative inlet velocity\n");
    exit(2);
  }
  if (poisseuille_terms < 3)
    poisseuille_terms = 3;
  compute_poisseuille_normalization();

  init_grid(64);
  origin(0., -1.5, -1.5);
  size(3. [1]);

  rho1 = 1. [0], rho2 = rho1/27.84;
  mu1 = 2.*u0*radius/Re*rho1, mu2 = 2.*u0*radius/Re*rho2;
  f.sigma = SIGMA;
  CFL = 0.35;

  ensure_output_dirs();
  if (auto_restore && !restore_requested && discover_latest_checkpoint(restore_path, sizeof(restore_path)))
    restore_requested = 1;
  initialize_output_files();
  write_all_manifests();

  fprintf(stderr,
          "CASE_CONFIG case_id=%s mode=%s radius=%.12g length=%.12g Re=%.12g sigma=%.12g rho_ratio=27.84 u0=%.12g pulse_amplitude=%.12g T0=%.12g maxlevel=%d end_time=%.12g uemax=%.12g A0=%.12g rect_W=%.12g rect_H=%.12g rect_Dh=%.12g poisseuille_terms=%d poisseuille_raw_mean=%.12g output_dir=%s\n",
          case_id, mode_name(), radius, initial_length, Re, SIGMA, u0,
          pulse_amplitude, T0, maxlevel, end_time, uemax, A0, rect_W, rect_H,
          rect_Dh, poisseuille_terms, poisseuille_raw_mean, output_dir);
  run();
}

event init (t = 0) {
  f.refine = f.prolongation = fraction_refine;
  f0.refine = f0.prolongation = fraction_refine;

  if (restore_requested) {
    if (!restore(file = restore_path)) {
      fprintf(stderr, "ERROR restore failed for %s\n", restore_path);
      exit(2);
    }
    restored_ok = 1;
    copy_string(restored_from, sizeof(restored_from), restore_path);
    fraction(f0, aperture_phi(y,z));
    f0.refine = f0.prolongation = fraction_refine;
    restriction({f0});
    boundary({f0, f, u});
    recover_indices_for_restore();
    double indexed_time = checkpoint_time_from_index(restore_path);
    restore_time = indexed_time >= 0. ? indexed_time : t;
    fprintf(stderr, "RESTORE_OK file=%s restore_time=%.12g next_visual=%d next_surface=%d next_raw=%d next_checkpoint=%d\n",
            restored_from, restore_time, visual_frame_index, surface_frame_index, raw_frame_index, checkpoint_index);
    return 0;
  }

  if (!mode_is_rectangular())
    refine(x < 1.2*initial_length && sq(y) + sq(z) < 2.*sq(radius) && level < maxlevel);
  else
    refine(x < 1.2*initial_length && fabs(y) < rect_W && fabs(z) < rect_H && level < maxlevel);

  fraction(f0, aperture_phi(y,z));
  f0.refine = f0.prolongation = fraction_refine;
  restriction({f0});

  foreach() {
    f[] = f0[]*(x < initial_length);
    u.x[] = u0*f[]*inlet_profile(y,z);
    u.y[] = 0.;
#if dimension > 2
    u.z[] = 0.;
#endif
  }
  boundary({f0, f, u});
}

event logfile (i++) {
  last_iter = i;
  if (i == 0)
    fprintf(stderr, "t dt mgp.i mgpf.i mgu.i cells perf.t perf.speed\n");
  if (i % 20 == 0)
    fprintf(stderr, "%g %g %d %d %d %ld %g %g\n",
            t, dt, mgp.i, mgpf.i, mgu.i, grid->tn, perf.t, perf.speed);
  if (i >= max_steps) {
    stable_flag = 0;
    fprintf(stderr, "MAX_STEPS_REACHED i=%d t=%.12g max_steps=%d\n", i, t, max_steps);
    write_final_summary_once();
    return 1;
  }
}

event diagnostics (t = 0.; t += raw_dt; t <= end_time + 1e-12) {
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  last_iter = i;
  write_component_and_frame_diagnostics(i);
  write_raw_interface_cells();
  raw_frame_index++;
}

event native_frames (t = 0.; t += output_dt; t <= end_time + 1e-12) {
  if (!enable_native_frames)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_native_frame(i);
}

event surface_facets (t = 0.; t += facet_dt; t <= end_time + 1e-12) {
  if (!enable_facet_export)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_surface_facets(i);
}

event checkpoint_dumps (t = checkpoint_dt; t += checkpoint_dt; t <= end_time + 1e-12) {
  if (!enable_checkpoints || checkpoint_dt <= 0.)
    return 0;
  if (restored_ok && t <= restore_time + 1e-12)
    return 0;
  write_checkpoint_dump(i);
}

event adapt (i++) {
  adapt_wavelet({f,u}, {0.01,uemax,uemax,uemax}, maxlevel);
}

event stop (t = end_time) {
  last_iter = i;
  write_final_summary_once();
  fprintf(stderr, "CANONICAL_PIPELINE_DONE case_id=%s mode=%s final_t=%.12g final_i=%d stable=%d\n",
          case_id, mode_name(), t, i, stable_flag);
  return 1;
}
