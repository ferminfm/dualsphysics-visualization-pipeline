#ifndef INTERNAL_NOZZLE_CHECKPOINT_V4_H
#define INTERNAL_NOZZLE_CHECKPOINT_V4_H

#include <stdint.h>
#include <stdlib.h>

#define INTERNAL_NOZZLE_CHECKPOINT_VERSION 4u
#define INTERNAL_NOZZLE_ENDIAN_MARKER 0x01020304u
#define INTERNAL_NOZZLE_FNV_OFFSET UINT64_C(14695981039346656037)
#define INTERNAL_NOZZLE_FNV_PRIME UINT64_C(1099511628211)

typedef struct {
  int32_t level, i, j, k;
  uint32_t topology;
  int32_t pid, neighbors;
  double ux, uy, uz;
  double gx, gy, gz;
} InternalNozzleCellRecordV4;

typedef struct {
  int32_t axis, level, i, j, k;
  double uf, fs, acceleration, fm;
} InternalNozzleFaceRecordV4;

typedef struct {
  char magic[40];
  uint32_t version, dimension_value, endian_marker, double_size;
  uint32_t cell_record_size, face_record_size;
  uint64_t cell_count, face_count, payload_bytes;
  uint64_t topology_hash, payload_hash;
  uint64_t active_physical_hash, actual_face_hash;
  double checkpoint_t, checkpoint_dt, checkpoint_dtmax;
  double timestep_previous;
  double domain_x0, domain_y0, domain_z0, domain_l0;
  int32_t checkpoint_iteration, grid_maxdepth;
  char source_sha256[128];
  char schedule_version_value[128];
  char schedule_sha256[128];
} InternalNozzleCheckpointHeaderV4;

typedef struct {
  uint64_t active_physical_hash, actual_face_hash;
  uint64_t active_physical_count, actual_face_count;
} InternalNozzleInvariantSnapshotV4;

static uint64_t internal_nozzle_fnv1a_v4
  (uint64_t hash, const void * data, size_t len)
{
  const unsigned char * p = (const unsigned char *) data;
  for (size_t n = 0; n < len; n++) {
    hash ^= p[n];
    hash *= INTERNAL_NOZZLE_FNV_PRIME;
  }
  return hash;
}

static int internal_nozzle_cell_compare_v4 (const void * a, const void * b)
{
  const InternalNozzleCellRecordV4 * x = a, * y = b;
#define INTERNAL_NOZZLE_COMPARE_FIELD(field) \
  do { if (x->field < y->field) return -1; if (x->field > y->field) return 1; } while (0)
  INTERNAL_NOZZLE_COMPARE_FIELD(level);
  INTERNAL_NOZZLE_COMPARE_FIELD(i);
  INTERNAL_NOZZLE_COMPARE_FIELD(j);
  INTERNAL_NOZZLE_COMPARE_FIELD(k);
#undef INTERNAL_NOZZLE_COMPARE_FIELD
  return 0;
}

static int internal_nozzle_face_compare_v4 (const void * a, const void * b)
{
  const InternalNozzleFaceRecordV4 * x = a, * y = b;
#define INTERNAL_NOZZLE_COMPARE_FIELD(field) \
  do { if (x->field < y->field) return -1; if (x->field > y->field) return 1; } while (0)
  INTERNAL_NOZZLE_COMPARE_FIELD(axis);
  INTERNAL_NOZZLE_COMPARE_FIELD(level);
  INTERNAL_NOZZLE_COMPARE_FIELD(i);
  INTERNAL_NOZZLE_COMPARE_FIELD(j);
  INTERNAL_NOZZLE_COMPARE_FIELD(k);
#undef INTERNAL_NOZZLE_COMPARE_FIELD
  return 0;
}

static int internal_nozzle_same_cell_key_v4
  (const InternalNozzleCellRecordV4 * a,
   const InternalNozzleCellRecordV4 * b)
{
  return a->level == b->level && a->i == b->i && a->j == b->j &&
    a->k == b->k;
}

static int internal_nozzle_same_face_key_v4
  (const InternalNozzleFaceRecordV4 * a,
   const InternalNozzleFaceRecordV4 * b)
{
  return a->axis == b->axis && a->level == b->level && a->i == b->i &&
    a->j == b->j && a->k == b->k;
}

static uint32_t internal_nozzle_topology_flags_v4 (Point point)
{
  uint32_t flags = 0;
  if (is_leaf(cell)) flags |= 1u;
  if (is_active(cell)) flags |= 2u;
  if (is_local(cell)) flags |= 4u;
  if (is_boundary(cell)) flags |= 8u;
  return flags;
}

static void internal_nozzle_collect_cells_v4
  (InternalNozzleCellRecordV4 ** records_out, uint64_t * count_out)
{
  uint64_t count = 0;
  foreach_cell_all()
    count++;
  if (!count || count > SIZE_MAX/sizeof(InternalNozzleCellRecordV4)) {
    fprintf(stderr, "ERROR invalid prediction-closure cell count %llu\n",
            (unsigned long long) count);
    exit(2);
  }
  InternalNozzleCellRecordV4 * records = calloc
    ((size_t) count, sizeof(InternalNozzleCellRecordV4));
  if (!records) {
    fprintf(stderr, "ERROR cannot allocate prediction-closure cell records\n");
    exit(2);
  }
  uint64_t n = 0;
  foreach_cell_all() {
    InternalNozzleCellRecordV4 * r = &records[n++];
    r->level = level; r->i = point.i; r->j = point.j; r->k = point.k;
    r->topology = internal_nozzle_topology_flags_v4(point);
    r->pid = cell.pid; r->neighbors = cell.neighbors;
    r->ux = u.x[]; r->uy = u.y[]; r->uz = u.z[];
    r->gx = g.x[]; r->gy = g.y[]; r->gz = g.z[];
  }
  if (n != count) {
    fprintf(stderr, "ERROR prediction-closure cell count changed during collection\n");
    exit(2);
  }
  qsort(records, (size_t) count, sizeof(*records),
        internal_nozzle_cell_compare_v4);
  for (uint64_t k = 1; k < count; k++)
    if (internal_nozzle_same_cell_key_v4(&records[k - 1], &records[k])) {
      fprintf(stderr, "ERROR duplicate prediction-closure cell key\n");
      exit(2);
    }
  *records_out = records;
  *count_out = count;
}

static void internal_nozzle_collect_faces_v4
  (InternalNozzleFaceRecordV4 ** records_out, uint64_t * count_out)
{
  uint64_t count = 0;
  foreach_face(x, serial) count++;
  foreach_face(y, serial) count++;
  foreach_face(z, serial) count++;
  if (!count || count > SIZE_MAX/sizeof(InternalNozzleFaceRecordV4)) {
    fprintf(stderr, "ERROR invalid prediction-closure face count %llu\n",
            (unsigned long long) count);
    exit(2);
  }
  InternalNozzleFaceRecordV4 * records = calloc
    ((size_t) count, sizeof(InternalNozzleFaceRecordV4));
  if (!records) {
    fprintf(stderr, "ERROR cannot allocate prediction-closure face records\n");
    exit(2);
  }
  uint64_t n = 0;
#define INTERNAL_NOZZLE_COLLECT_FACE(axis_value, component) do { \
    InternalNozzleFaceRecordV4 * r = &records[n++]; \
    r->axis = axis_value; r->level = level; r->i = point.i; \
    r->j = point.j; r->k = point.k; \
    r->uf = uf.component[]; r->fs = fs.component[]; \
    r->acceleration = a.component[]; r->fm = fm.component[]; \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_COLLECT_FACE(0, x);
  foreach_face(y, serial) INTERNAL_NOZZLE_COLLECT_FACE(1, y);
  foreach_face(z, serial) INTERNAL_NOZZLE_COLLECT_FACE(2, z);
#undef INTERNAL_NOZZLE_COLLECT_FACE
  if (n != count) {
    fprintf(stderr, "ERROR prediction-closure face count changed during collection\n");
    exit(2);
  }
  qsort(records, (size_t) count, sizeof(*records),
        internal_nozzle_face_compare_v4);
  for (uint64_t k = 1; k < count; k++)
    if (internal_nozzle_same_face_key_v4(&records[k - 1], &records[k])) {
      fprintf(stderr, "ERROR duplicate prediction-closure face key\n");
      exit(2);
    }
  *records_out = records;
  *count_out = count;
}

static uint64_t internal_nozzle_topology_hash_v4
  (const InternalNozzleCellRecordV4 * cells, uint64_t cell_count,
   const InternalNozzleFaceRecordV4 * faces, uint64_t face_count)
{
  uint64_t hash = INTERNAL_NOZZLE_FNV_OFFSET;
  for (uint64_t n = 0; n < cell_count; n++) {
    const InternalNozzleCellRecordV4 * r = &cells[n];
    hash = internal_nozzle_fnv1a_v4(hash, &r->level, sizeof(r->level));
    hash = internal_nozzle_fnv1a_v4(hash, &r->i, sizeof(r->i));
    hash = internal_nozzle_fnv1a_v4(hash, &r->j, sizeof(r->j));
    hash = internal_nozzle_fnv1a_v4(hash, &r->k, sizeof(r->k));
    hash = internal_nozzle_fnv1a_v4(hash, &r->topology, sizeof(r->topology));
    hash = internal_nozzle_fnv1a_v4(hash, &r->pid, sizeof(r->pid));
    hash = internal_nozzle_fnv1a_v4(hash, &r->neighbors, sizeof(r->neighbors));
  }
  for (uint64_t n = 0; n < face_count; n++) {
    const InternalNozzleFaceRecordV4 * r = &faces[n];
    hash = internal_nozzle_fnv1a_v4(hash, &r->axis, sizeof(r->axis));
    hash = internal_nozzle_fnv1a_v4(hash, &r->level, sizeof(r->level));
    hash = internal_nozzle_fnv1a_v4(hash, &r->i, sizeof(r->i));
    hash = internal_nozzle_fnv1a_v4(hash, &r->j, sizeof(r->j));
    hash = internal_nozzle_fnv1a_v4(hash, &r->k, sizeof(r->k));
  }
  return hash;
}

static uint64_t internal_nozzle_payload_hash_v4
  (const InternalNozzleCheckpointHeaderV4 * header,
   const InternalNozzleCellRecordV4 * cells,
   const InternalNozzleFaceRecordV4 * faces)
{
  uint64_t hash = INTERNAL_NOZZLE_FNV_OFFSET;
  hash = internal_nozzle_fnv1a_v4(hash, &header->version,
                                  sizeof(header->version));
  hash = internal_nozzle_fnv1a_v4(hash, &header->cell_count,
                                  sizeof(header->cell_count));
  hash = internal_nozzle_fnv1a_v4(hash, &header->face_count,
                                  sizeof(header->face_count));
  hash = internal_nozzle_fnv1a_v4(hash, &header->topology_hash,
                                  sizeof(header->topology_hash));
  hash = internal_nozzle_fnv1a_v4(hash, &header->checkpoint_t,
                                  sizeof(header->checkpoint_t));
  hash = internal_nozzle_fnv1a_v4(hash, &header->checkpoint_dt,
                                  sizeof(header->checkpoint_dt));
  hash = internal_nozzle_fnv1a_v4(hash, &header->checkpoint_dtmax,
                                  sizeof(header->checkpoint_dtmax));
  hash = internal_nozzle_fnv1a_v4(hash, &header->timestep_previous,
                                  sizeof(header->timestep_previous));
  hash = internal_nozzle_fnv1a_v4(hash, header->source_sha256,
                                  sizeof(header->source_sha256));
  hash = internal_nozzle_fnv1a_v4(hash, header->schedule_version_value,
                                  sizeof(header->schedule_version_value));
  hash = internal_nozzle_fnv1a_v4(hash, header->schedule_sha256,
                                  sizeof(header->schedule_sha256));
  hash = internal_nozzle_fnv1a_v4
    (hash, cells, (size_t) header->cell_count*sizeof(*cells));
  hash = internal_nozzle_fnv1a_v4
    (hash, faces, (size_t) header->face_count*sizeof(*faces));
  return hash;
}

static InternalNozzleInvariantSnapshotV4
internal_nozzle_invariant_snapshot_v4 (void)
{
  InternalNozzleInvariantSnapshotV4 snapshot = {
    INTERNAL_NOZZLE_FNV_OFFSET, INTERNAL_NOZZLE_FNV_OFFSET, 0, 0
  };
  foreach(serial) {
    int32_t key[4] = {level, point.i, point.j, point.k};
    snapshot.active_physical_hash = internal_nozzle_fnv1a_v4
      (snapshot.active_physical_hash, key, sizeof(key));
    double values[] = {
      f[], u.x[], u.y[], u.z[], g.x[], g.y[], g.z[], p[], pf[]
    };
    snapshot.active_physical_hash = internal_nozzle_fnv1a_v4
      (snapshot.active_physical_hash, values, sizeof(values));
    snapshot.active_physical_count++;
  }
#define INTERNAL_NOZZLE_HASH_FACE(axis_value, component) do { \
    int32_t key[5] = {axis_value, level, point.i, point.j, point.k}; \
    double values[] = {uf.component[], fs.component[], a.component[], fm.component[]}; \
    snapshot.actual_face_hash = internal_nozzle_fnv1a_v4 \
      (snapshot.actual_face_hash, key, sizeof(key)); \
    snapshot.actual_face_hash = internal_nozzle_fnv1a_v4 \
      (snapshot.actual_face_hash, values, sizeof(values)); \
    snapshot.actual_face_count++; \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_HASH_FACE(0, x);
  foreach_face(y, serial) INTERNAL_NOZZLE_HASH_FACE(1, y);
  foreach_face(z, serial) INTERNAL_NOZZLE_HASH_FACE(2, z);
#undef INTERNAL_NOZZLE_HASH_FACE
  return snapshot;
}

static void internal_nozzle_read_closure_v4
  (const char * path, InternalNozzleCheckpointHeaderV4 * header,
   InternalNozzleCellRecordV4 ** cells_out,
   InternalNozzleFaceRecordV4 ** faces_out)
{
  FILE * fp = fopen(path, "rb");
  if (!fp) {
    fprintf(stderr, "ERROR cannot read prediction-closure checkpoint %s\n", path);
    exit(2);
  }
  memset(header, 0, sizeof(*header));
  if (fread(header, sizeof(*header), 1, fp) != 1 ||
      strcmp(header->magic, "internal_nozzle_prediction_closure_v4") ||
      header->version != INTERNAL_NOZZLE_CHECKPOINT_VERSION ||
      header->dimension_value != dimension ||
      header->endian_marker != INTERNAL_NOZZLE_ENDIAN_MARKER ||
      header->double_size != sizeof(double) ||
      header->cell_record_size != sizeof(InternalNozzleCellRecordV4) ||
      header->face_record_size != sizeof(InternalNozzleFaceRecordV4)) {
    fprintf(stderr, "ERROR incompatible prediction-closure checkpoint %s\n", path);
    exit(2);
  }
  if (!header->cell_count || !header->face_count ||
      header->cell_count > SIZE_MAX/sizeof(InternalNozzleCellRecordV4) ||
      header->face_count > SIZE_MAX/sizeof(InternalNozzleFaceRecordV4) ||
      header->payload_bytes !=
      header->cell_count*sizeof(InternalNozzleCellRecordV4) +
      header->face_count*sizeof(InternalNozzleFaceRecordV4)) {
    fprintf(stderr, "ERROR invalid prediction-closure counts in %s\n", path);
    exit(2);
  }
  if (strcmp(header->source_sha256, source_sha) ||
      strcmp(header->schedule_version_value, schedule_version) ||
      strcmp(header->schedule_sha256, schedule_sha)) {
    fprintf(stderr, "ERROR prediction-closure provenance mismatch in %s\n", path);
    exit(2);
  }
  InternalNozzleCellRecordV4 * cells = calloc
    ((size_t) header->cell_count, sizeof(*cells));
  InternalNozzleFaceRecordV4 * faces = calloc
    ((size_t) header->face_count, sizeof(*faces));
  if (!cells || !faces ||
      fread(cells, sizeof(*cells), (size_t) header->cell_count, fp) !=
      header->cell_count ||
      fread(faces, sizeof(*faces), (size_t) header->face_count, fp) !=
      header->face_count || fgetc(fp) != EOF) {
    fprintf(stderr, "ERROR truncated or trailing prediction-closure payload %s\n", path);
    exit(2);
  }
  fclose(fp);
  for (uint64_t n = 1; n < header->cell_count; n++)
    if (internal_nozzle_cell_compare_v4(&cells[n - 1], &cells[n]) >= 0) {
      fprintf(stderr, "ERROR unordered or duplicate prediction-closure cell key\n");
      exit(2);
    }
  for (uint64_t n = 1; n < header->face_count; n++)
    if (internal_nozzle_face_compare_v4(&faces[n - 1], &faces[n]) >= 0) {
      fprintf(stderr, "ERROR unordered or duplicate prediction-closure face key\n");
      exit(2);
    }
  if (internal_nozzle_topology_hash_v4
      (cells, header->cell_count, faces, header->face_count) !=
      header->topology_hash ||
      internal_nozzle_payload_hash_v4(header, cells, faces) !=
      header->payload_hash) {
    fprintf(stderr, "ERROR prediction-closure topology or payload hash mismatch %s\n",
            path);
    exit(2);
  }
  *cells_out = cells;
  *faces_out = faces;
}

static void internal_nozzle_validate_current_keys_v4
  (const InternalNozzleCheckpointHeaderV4 * header,
   const InternalNozzleCellRecordV4 * expected_cells,
   const InternalNozzleFaceRecordV4 * expected_faces,
   InternalNozzleCellRecordV4 ** current_cells_out,
   InternalNozzleFaceRecordV4 ** current_faces_out)
{
  uint64_t current_cell_count = 0, current_face_count = 0;
  InternalNozzleCellRecordV4 * current_cells = NULL;
  InternalNozzleFaceRecordV4 * current_faces = NULL;
  InternalNozzleProbeSnapshot probe_before = internal_nozzle_probe_capture();
  internal_nozzle_collect_cells_v4(&current_cells, &current_cell_count);
  InternalNozzleProbeSnapshot probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_validate_enumerate_cells",
     "candidate_added", "internal_nozzle_validate_current_keys_v4:cells");
  probe_before = internal_nozzle_probe_capture();
  internal_nozzle_collect_faces_v4(&current_faces, &current_face_count);
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_validate_enumerate_faces",
     "candidate_added", "internal_nozzle_validate_current_keys_v4:faces");
  if (current_cell_count != header->cell_count ||
      current_face_count != header->face_count) {
    fprintf(stderr, "ERROR prediction-closure current count mismatch\n");
    exit(2);
  }
  for (uint64_t n = 0; n < current_cell_count; n++)
    if (!internal_nozzle_same_cell_key_v4(&expected_cells[n], &current_cells[n]) ||
        expected_cells[n].topology != current_cells[n].topology ||
        expected_cells[n].pid != current_cells[n].pid ||
        expected_cells[n].neighbors != current_cells[n].neighbors) {
      fprintf(stderr, "ERROR prediction-closure unknown, dropped, or changed cell key\n");
      exit(2);
    }
  for (uint64_t n = 0; n < current_face_count; n++)
    if (!internal_nozzle_same_face_key_v4(&expected_faces[n], &current_faces[n])) {
      fprintf(stderr, "ERROR prediction-closure unknown or dropped face key\n");
      exit(2);
    }
  if (internal_nozzle_topology_hash_v4
      (current_cells, current_cell_count, current_faces, current_face_count) !=
      header->topology_hash) {
    fprintf(stderr, "ERROR prediction-closure current topology fingerprint mismatch\n");
    exit(2);
  }
  *current_cells_out = current_cells;
  *current_faces_out = current_faces;
}

static long internal_nozzle_find_cell_v4
  (const InternalNozzleCellRecordV4 * records, uint64_t count,
   int32_t level_value, int32_t i, int32_t j, int32_t k)
{
  InternalNozzleCellRecordV4 key = {0};
  key.level = level_value; key.i = i; key.j = j; key.k = k;
  const InternalNozzleCellRecordV4 * found = bsearch
    (&key, records, (size_t) count, sizeof(*records),
     internal_nozzle_cell_compare_v4);
  return found ? (long)(found - records) : -1;
}

static long internal_nozzle_find_face_v4
  (const InternalNozzleFaceRecordV4 * records, uint64_t count,
   int32_t axis, int32_t level_value, int32_t i, int32_t j, int32_t k)
{
  InternalNozzleFaceRecordV4 key = {0};
  key.axis = axis; key.level = level_value; key.i = i; key.j = j; key.k = k;
  const InternalNozzleFaceRecordV4 * found = bsearch
    (&key, records, (size_t) count, sizeof(*records),
     internal_nozzle_face_compare_v4);
  return found ? (long)(found - records) : -1;
}

static void internal_nozzle_restore_prediction_closure_v4 (const char * path)
{
  InternalNozzleCheckpointHeaderV4 header;
  InternalNozzleCellRecordV4 * expected_cells = NULL, * current_cells = NULL;
  InternalNozzleFaceRecordV4 * expected_faces = NULL, * current_faces = NULL;
  internal_nozzle_read_closure_v4
    (path, &header, &expected_cells, &expected_faces);
  internal_nozzle_validate_current_keys_v4
    (&header, expected_cells, expected_faces, &current_cells, &current_faces);
  free(current_cells); free(current_faces);

  uint64_t seen_cells = 0, seen_faces = 0;
  foreach_cell_all() {
    long n = internal_nozzle_find_cell_v4
      (expected_cells, header.cell_count, level, point.i, point.j, point.k);
    if (n < 0) {
      fprintf(stderr, "ERROR unknown current prediction-closure cell key\n");
      exit(2);
    }
    const InternalNozzleCellRecordV4 * r = &expected_cells[n];
    u.x[] = r->ux; u.y[] = r->uy; u.z[] = r->uz;
    g.x[] = r->gx; g.y[] = r->gy; g.z[] = r->gz;
    seen_cells++;
  }
#define INTERNAL_NOZZLE_RESTORE_FACE(axis_value, component) do { \
    long n = internal_nozzle_find_face_v4 \
      (expected_faces, header.face_count, axis_value, level, point.i, point.j, point.k); \
    if (n < 0) { \
      fprintf(stderr, "ERROR unknown current prediction-closure face key\n"); \
      exit(2); \
    } \
    const InternalNozzleFaceRecordV4 * r = &expected_faces[n]; \
    uf.component[] = r->uf; fs.component[] = r->fs; \
    a.component[] = r->acceleration; fm.component[] = r->fm; \
    seen_faces++; \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_RESTORE_FACE(0, x);
  foreach_face(y, serial) INTERNAL_NOZZLE_RESTORE_FACE(1, y);
  foreach_face(z, serial) INTERNAL_NOZZLE_RESTORE_FACE(2, z);
#undef INTERNAL_NOZZLE_RESTORE_FACE
  if (seen_cells != header.cell_count || seen_faces != header.face_count) {
    fprintf(stderr, "ERROR prediction-closure restore count mismatch\n");
    exit(2);
  }
  dt = header.checkpoint_dt;
  dtmax = header.checkpoint_dtmax;
  internal_nozzle_timestep_previous = header.timestep_previous;

  internal_nozzle_collect_cells_v4(&current_cells, &seen_cells);
  internal_nozzle_collect_faces_v4(&current_faces, &seen_faces);
  if (memcmp(expected_cells, current_cells,
             (size_t) header.cell_count*sizeof(*expected_cells)) ||
      memcmp(expected_faces, current_faces,
             (size_t) header.face_count*sizeof(*expected_faces))) {
    fprintf(stderr, "ERROR prediction-closure post-restore payload mismatch\n");
    exit(2);
  }
  InternalNozzleInvariantSnapshotV4 after =
    internal_nozzle_invariant_snapshot_v4();
  if (after.active_physical_hash != header.active_physical_hash ||
      after.actual_face_hash != header.actual_face_hash) {
    fprintf(stderr, "ERROR prediction-closure post-restore invariant mismatch\n");
    exit(2);
  }
  fprintf(stderr,
          "prediction-closure-v4 restored cells=%llu faces=%llu topology=%016llx payload=%016llx\n",
          (unsigned long long) header.cell_count,
          (unsigned long long) header.face_count,
          (unsigned long long) header.topology_hash,
          (unsigned long long) header.payload_hash);
  free(expected_cells); free(expected_faces);
  free(current_cells); free(current_faces);
}

static void internal_nozzle_write_prediction_closure_v4 (const char * path)
{
  InternalNozzleCellRecordV4 * cells = NULL, * check_cells = NULL;
  InternalNozzleFaceRecordV4 * faces = NULL, * check_faces = NULL;
  uint64_t cell_count = 0, face_count = 0;
  InternalNozzleProbeSnapshot probe_before = internal_nozzle_probe_capture();
  internal_nozzle_collect_cells_v4(&cells, &cell_count);
  InternalNozzleProbeSnapshot probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_writer_enumerate_cells",
     "candidate_added", "internal_nozzle_collect_cells_v4");
  probe_before = internal_nozzle_probe_capture();
  internal_nozzle_collect_faces_v4(&faces, &face_count);
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_writer_enumerate_faces",
     "candidate_added", "internal_nozzle_collect_faces_v4");
  probe_before = internal_nozzle_probe_capture();
  InternalNozzleInvariantSnapshotV4 snapshot =
    internal_nozzle_invariant_snapshot_v4();
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_writer_invariant_snapshot",
     "candidate_added", "internal_nozzle_invariant_snapshot_v4");
  InternalNozzleCheckpointHeaderV4 header = {0};
  snprintf(header.magic, sizeof(header.magic),
           "internal_nozzle_prediction_closure_v4");
  header.version = INTERNAL_NOZZLE_CHECKPOINT_VERSION;
  header.dimension_value = dimension;
  header.endian_marker = INTERNAL_NOZZLE_ENDIAN_MARKER;
  header.double_size = sizeof(double);
  header.cell_record_size = sizeof(InternalNozzleCellRecordV4);
  header.face_record_size = sizeof(InternalNozzleFaceRecordV4);
  header.cell_count = cell_count; header.face_count = face_count;
  header.payload_bytes = cell_count*sizeof(*cells) + face_count*sizeof(*faces);
  header.topology_hash = internal_nozzle_topology_hash_v4
    (cells, cell_count, faces, face_count);
  header.active_physical_hash = snapshot.active_physical_hash;
  header.actual_face_hash = snapshot.actual_face_hash;
  header.checkpoint_t = t; header.checkpoint_dt = dt;
  header.checkpoint_dtmax = dtmax;
  header.timestep_previous = internal_nozzle_timestep_previous;
  header.domain_x0 = X0; header.domain_y0 = Y0; header.domain_z0 = Z0;
  header.domain_l0 = L0; header.checkpoint_iteration = iter;
  header.grid_maxdepth = grid->maxdepth;
  snprintf(header.source_sha256, sizeof(header.source_sha256), "%s", source_sha);
  snprintf(header.schedule_version_value,
           sizeof(header.schedule_version_value), "%s", schedule_version);
  snprintf(header.schedule_sha256, sizeof(header.schedule_sha256), "%s",
           schedule_sha);
  header.payload_hash = internal_nozzle_payload_hash_v4(&header, cells, faces);

  char * temporary = malloc(strlen(path) + 5);
  if (!temporary) {
    fprintf(stderr, "ERROR cannot allocate prediction-closure temporary path\n");
    exit(2);
  }
  sprintf(temporary, "%s.tmp", path);
  probe_before = internal_nozzle_probe_capture();
  FILE * fp = fopen(temporary, "wb");
  if (!fp || fwrite(&header, sizeof(header), 1, fp) != 1 ||
      fwrite(cells, sizeof(*cells), (size_t) cell_count, fp) != cell_count ||
      fwrite(faces, sizeof(*faces), (size_t) face_count, fp) != face_count ||
      fflush(fp) || fclose(fp) || rename(temporary, path)) {
    fprintf(stderr, "ERROR cannot write prediction-closure checkpoint %s\n", path);
    exit(2);
  }
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_container_serialize",
     "candidate_added", "fwrite_fflush_fclose_rename");
  free(temporary);

  InternalNozzleCheckpointHeaderV4 check_header;
  probe_before = internal_nozzle_probe_capture();
  internal_nozzle_read_closure_v4
    (path, &check_header, &check_cells, &check_faces);
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_container_reread",
     "candidate_added", "internal_nozzle_read_closure_v4");
  InternalNozzleCellRecordV4 * current_cells = NULL;
  InternalNozzleFaceRecordV4 * current_faces = NULL;
  probe_before = internal_nozzle_probe_capture();
  internal_nozzle_validate_current_keys_v4
    (&check_header, check_cells, check_faces, &current_cells, &current_faces);
  probe_after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&probe_before, &probe_after, "candidate_container_validate_current_keys",
     "candidate_added", "internal_nozzle_validate_current_keys_v4");
  if (memcmp(check_cells, current_cells,
             (size_t) cell_count*sizeof(*cells)) ||
      memcmp(check_faces, current_faces,
             (size_t) face_count*sizeof(*faces))) {
    fprintf(stderr, "ERROR prediction-closure write verification mismatch\n");
    exit(2);
  }
  fprintf(stderr,
          "prediction-closure-v4 wrote cells=%llu faces=%llu topology=%016llx payload=%016llx\n",
          (unsigned long long) cell_count, (unsigned long long) face_count,
          (unsigned long long) header.topology_hash,
          (unsigned long long) header.payload_hash);
  free(cells); free(faces); free(check_cells); free(check_faces);
  free(current_cells); free(current_faces);
}

#endif
