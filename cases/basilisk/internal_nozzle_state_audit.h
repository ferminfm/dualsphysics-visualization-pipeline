#ifndef INTERNAL_NOZZLE_STATE_AUDIT_H
#define INTERNAL_NOZZLE_STATE_AUDIT_H

/* Observation only: do not call boundary, restriction, properties or projection.
 * Mode 2 replaces large CSV snapshots with keyed complete-state fingerprints.
 * A fingerprint mismatch localizes a stage/field but is not a difference norm. */
static void internal_nozzle_state_audit (const char * phase, int iteration_value)
{
  scalar * fields = (scalar *){f, u, g, p, pf, cs, cm, un, rho};
  const char * labels[] = {"f", "ux", "uy", "uz", "gx", "gy", "gz",
                           "p", "pf", "cs", "cm", "un", "rho"};
  uint64_t hashes[3][13], keys[3], counts[3] = {0};
  for (int j = 0; j < 3; j++) {
    keys[j] = INTERNAL_NOZZLE_FNV_OFFSET;
    for (int k = 0; k < 13; k++) hashes[j][k] = INTERNAL_NOZZLE_FNV_OFFSET;
  }
  foreach_cell_all() {
    int32_t key[] = {level, point.i, point.j, point.k,
                    is_leaf(cell), is_active(cell), is_local(cell), is_boundary(cell)};
    int group = is_leaf(cell) && is_active(cell) && is_local(cell) && !is_boundary(cell) ?
      (x <= exit_x() ? 0 : 1) : 2;
    keys[group] = internal_nozzle_fnv1a_v4(keys[group], key, sizeof(key));
    counts[group]++;
    for (int k = 0; k < 13; k++) {
      double value = is_constant(fields[k]) ? constant(fields[k]) : val(fields[k],0,0,0);
      hashes[group][k] = internal_nozzle_fnv1a_v4(hashes[group][k], &value, sizeof(value));
    }
  }
  uint64_t face_hashes[3][6], face_keys[3], face_counts[3] = {0};
  for (int j = 0; j < 3; j++) {
    face_keys[j] = INTERNAL_NOZZLE_FNV_OFFSET;
    for (int k = 0; k < 6; k++) face_hashes[j][k] = INTERNAL_NOZZLE_FNV_OFFSET;
  }
#define INTERNAL_NOZZLE_AUDIT_FACE(axis_value, component) do { \
    int32_t key[] = {axis_value, level, point.i, point.j, point.k}; \
    scalar * ff = (scalar *){uf.component, fs.component, fm.component, a.component, alpha.component, mu.component}; \
    face_keys[axis_value] = internal_nozzle_fnv1a_v4(face_keys[axis_value], key, sizeof(key)); \
    face_counts[axis_value]++; \
    for (int k = 0; k < 6; k++) { \
      double value = is_constant(ff[k]) ? constant(ff[k]) : val(ff[k],0,0,0); \
      face_hashes[axis_value][k] = internal_nozzle_fnv1a_v4(face_hashes[axis_value][k], &value, sizeof(value)); \
    } \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_AUDIT_FACE(0,x);
  foreach_face(y, serial) INTERNAL_NOZZLE_AUDIT_FACE(1,y);
  foreach_face(z, serial) INTERNAL_NOZZLE_AUDIT_FACE(2,z);
#undef INTERNAL_NOZZLE_AUDIT_FACE
  char path[1024]; output_path(path, sizeof(path), "state_audit.jsonl");
  FILE * fp = fopen(path, "a");
  if (!fp) { fprintf(stderr, "ERROR cannot open compact state audit\n"); exit(2); }
  fprintf(fp, "{\"schema\":\"internal_nozzle_compact_state_v1\",\"phase\":\"%s\",\"t\":%.17g,\"i\":%d,\"iter\":%d,\"dt\":%.17g,\"dtmax\":%.17g,\"previous_dt\":%.17g,\"mg_nrelax\":[%d,%d,%d],\"cell_groups\":[", phase, t, iteration_value, iter, dt, dtmax, internal_nozzle_timestep_previous, mgp.nrelax, mgpf.nrelax, mgu.nrelax);
  for (int j = 0; j < 3; j++) {
    fprintf(fp, "%s{\"group\":%d,\"count\":%llu,\"key_hash\":\"%016llx\",\"fields\":{", j ? "," : "", j, (unsigned long long)counts[j], (unsigned long long)keys[j]);
    for (int k = 0; k < 13; k++)
      fprintf(fp, "%s\"%s\":\"%016llx\"", k ? "," : "", labels[k], (unsigned long long)hashes[j][k]);
    fputs("}}", fp);
  }
  const char * flabels[] = {"uf","fs","fm","a","alpha","mu"};
  fputs("],\"face_axes\":[", fp);
  for (int j = 0; j < 3; j++) {
    fprintf(fp, "%s{\"axis\":%d,\"count\":%llu,\"key_hash\":\"%016llx\",\"fields\":{", j ? "," : "", j, (unsigned long long)face_counts[j], (unsigned long long)face_keys[j]);
    for (int k = 0; k < 6; k++)
      fprintf(fp, "%s\"%s\":\"%016llx\"", k ? "," : "", flabels[k], (unsigned long long)face_hashes[j][k]);
    fputs("}}", fp);
  }
  fputs("]}\n", fp); fclose(fp);
  /* Optional, bounded binary observations for independent keyed field norms.
   * Explicit fwrite arrays avoid C-ABI padding; no solver state is changed. */
  if (forensic_snapshot_end_time < 0. || t > forensic_snapshot_end_time + 1e-14)
    return;
  if (strcmp(phase, "post_checkpoint") && strcmp(phase, "stability_post_sidecar") &&
      strcmp(phase, "before_advection_term") && strcmp(phase, "before_projection") &&
      strcmp(phase, "post_projection") && strcmp(phase, "post_restore_pre_centered") &&
      strcmp(phase, "before_prediction") && strcmp(phase, "after_prediction_pre_projection"))
    return;
  uint32_t endian = 1;
  if (*(unsigned char *)&endian != 1 || sizeof(double) != 8 || sizeof(int32_t) != 4) {
    fprintf(stderr, "ERROR unsupported field observation binary ABI\n"); exit(2);
  }
  char snapshot_leaf[256];
  snprintf(snapshot_leaf, sizeof(snapshot_leaf), "state_%s_t%.17e_i%07d.bin", phase, t, iter);
  subdir_path(path, sizeof(path), forensic_dir, snapshot_leaf);
  fp = fopen(path, "wx");
  if (!fp) { fprintf(stderr, "ERROR duplicate/unwritable field observation\n"); exit(2); }
  fprintf(fp, "{\"schema\":\"internal_nozzle_keyed_state_v1\",\"endian\":\"little\",\"phase\":\"%s\",\"t\":%.17g,\"i\":%d,\"dt\":%.17g,\"exit_x\":%.17g,\"cell_count\":%llu,\"face_count\":%llu,\"cell_bytes\":168,\"face_bytes\":100}\n",
          phase, t, iter, dt, exit_x(),
          (unsigned long long)(counts[0] + counts[1] + counts[2]),
          (unsigned long long)(face_counts[0] + face_counts[1] + face_counts[2]));
  foreach_cell_all() {
    int32_t key[] = {level, point.i, point.j, point.k,
                    is_leaf(cell), is_active(cell), is_local(cell), is_boundary(cell)};
    double values[17] = {x,y,z,Delta};
    for (int k = 0; k < 13; k++)
      values[k+4] = is_constant(fields[k]) ? constant(fields[k]) : val(fields[k],0,0,0);
    if (fwrite(key, sizeof(int32_t), 8, fp) != 8 || fwrite(values, sizeof(double), 17, fp) != 17) {
      fprintf(stderr, "ERROR incomplete cell observation write\n"); exit(2);
    }
  }
#define INTERNAL_NOZZLE_SNAPSHOT_FACE(axis_value, component) do { \
    int32_t key[] = {axis_value, level, point.i, point.j, point.k}; \
    scalar * ff = (scalar *){uf.component, fs.component, fm.component, a.component, alpha.component, mu.component}; \
    double values[10] = {x,y,z,Delta}; \
    for (int k = 0; k < 6; k++) \
      values[k+4] = is_constant(ff[k]) ? constant(ff[k]) : val(ff[k],0,0,0); \
    if (fwrite(key, sizeof(int32_t), 5, fp) != 5 || fwrite(values, sizeof(double), 10, fp) != 10) { \
      fprintf(stderr, "ERROR incomplete face observation write\n"); exit(2); \
    } \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_SNAPSHOT_FACE(0,x);
  foreach_face(y, serial) INTERNAL_NOZZLE_SNAPSHOT_FACE(1,y);
  foreach_face(z, serial) INTERNAL_NOZZLE_SNAPSHOT_FACE(2,z);
#undef INTERNAL_NOZZLE_SNAPSHOT_FACE
  if (fclose(fp)) { fprintf(stderr, "ERROR field observation close failed\n"); exit(2); }
}
#endif
