#ifndef INTERNAL_NOZZLE_NONMUTATION_PROBE_H
#define INTERNAL_NOZZLE_NONMUTATION_PROBE_H

#include <stdint.h>
#include <stdlib.h>

#ifndef INTERNAL_NOZZLE_PROBE_VARIANT
# define INTERNAL_NOZZLE_PROBE_VARIANT "unspecified"
#endif

#define INTERNAL_NOZZLE_PROBE_FNV_OFFSET UINT64_C(14695981039346656037)
#define INTERNAL_NOZZLE_PROBE_FNV_PRIME UINT64_C(1099511628211)

typedef struct {
  int32_t level, i, j, k;
  uint64_t value[9];
} InternalNozzleProbeCell;

typedef struct {
  int32_t axis, level, i, j, k;
  uint64_t value[4];
} InternalNozzleProbeFace;

typedef struct {
  int32_t level, i, j, k;
  uint32_t flags;
  int32_t pid, neighbors;
} InternalNozzleProbeTopology;

typedef struct {
  InternalNozzleProbeCell * cells;
  InternalNozzleProbeFace * faces;
  InternalNozzleProbeTopology * topology;
  uint64_t cell_count, face_count, topology_count;
  uint64_t cell_hash[9], face_hash[4];
  uint64_t cell_key_hash, face_key_hash, topology_hash;
} InternalNozzleProbeSnapshot;

static uint64_t internal_nozzle_probe_bits (double value)
{
  union { double value; uint64_t bits; } bits = {value};
  return bits.bits;
}

static uint64_t internal_nozzle_probe_fnv
  (uint64_t hash, const void * data, size_t length)
{
  const unsigned char * bytes = data;
  for (size_t n = 0; n < length; n++) {
    hash ^= bytes[n];
    hash *= INTERNAL_NOZZLE_PROBE_FNV_PRIME;
  }
  return hash;
}

static int internal_nozzle_probe_cell_compare (const void * a, const void * b)
{
  const InternalNozzleProbeCell * x = a, * y = b;
#define INTERNAL_NOZZLE_PROBE_COMPARE(field) \
  do { if (x->field < y->field) return -1; if (x->field > y->field) return 1; } while (0)
  INTERNAL_NOZZLE_PROBE_COMPARE(level);
  INTERNAL_NOZZLE_PROBE_COMPARE(i);
  INTERNAL_NOZZLE_PROBE_COMPARE(j);
  INTERNAL_NOZZLE_PROBE_COMPARE(k);
#undef INTERNAL_NOZZLE_PROBE_COMPARE
  return 0;
}

static int internal_nozzle_probe_face_compare (const void * a, const void * b)
{
  const InternalNozzleProbeFace * x = a, * y = b;
#define INTERNAL_NOZZLE_PROBE_COMPARE(field) \
  do { if (x->field < y->field) return -1; if (x->field > y->field) return 1; } while (0)
  INTERNAL_NOZZLE_PROBE_COMPARE(axis);
  INTERNAL_NOZZLE_PROBE_COMPARE(level);
  INTERNAL_NOZZLE_PROBE_COMPARE(i);
  INTERNAL_NOZZLE_PROBE_COMPARE(j);
  INTERNAL_NOZZLE_PROBE_COMPARE(k);
#undef INTERNAL_NOZZLE_PROBE_COMPARE
  return 0;
}

static int internal_nozzle_probe_topology_compare
  (const void * a, const void * b)
{
  const InternalNozzleProbeTopology * x = a, * y = b;
#define INTERNAL_NOZZLE_PROBE_COMPARE(field) \
  do { if (x->field < y->field) return -1; if (x->field > y->field) return 1; } while (0)
  INTERNAL_NOZZLE_PROBE_COMPARE(level);
  INTERNAL_NOZZLE_PROBE_COMPARE(i);
  INTERNAL_NOZZLE_PROBE_COMPARE(j);
  INTERNAL_NOZZLE_PROBE_COMPARE(k);
#undef INTERNAL_NOZZLE_PROBE_COMPARE
  return 0;
}

static uint32_t internal_nozzle_probe_topology_flags (Point point)
{
  uint32_t flags = 0;
  if (is_leaf(cell)) flags |= 1u;
  if (is_active(cell)) flags |= 2u;
  if (is_local(cell)) flags |= 4u;
  if (is_boundary(cell)) flags |= 8u;
  return flags;
}

static InternalNozzleProbeSnapshot internal_nozzle_probe_capture (void)
{
  InternalNozzleProbeSnapshot snapshot = {0};
  foreach(serial) snapshot.cell_count++;
  foreach_face(x, serial) snapshot.face_count++;
  foreach_face(y, serial) snapshot.face_count++;
  foreach_face(z, serial) snapshot.face_count++;
  foreach_cell_all() snapshot.topology_count++;
  if (!snapshot.cell_count || !snapshot.face_count || !snapshot.topology_count) {
    fprintf(stderr, "ERROR nonmutation probe observed an empty solver state\n");
    exit(2);
  }
  snapshot.cells = calloc((size_t) snapshot.cell_count, sizeof(*snapshot.cells));
  snapshot.faces = calloc((size_t) snapshot.face_count, sizeof(*snapshot.faces));
  snapshot.topology = calloc
    ((size_t) snapshot.topology_count, sizeof(*snapshot.topology));
  if (!snapshot.cells || !snapshot.faces || !snapshot.topology) {
    fprintf(stderr, "ERROR cannot allocate nonmutation probe snapshot\n");
    exit(2);
  }
  uint64_t n = 0;
  foreach(serial) {
    InternalNozzleProbeCell * record = &snapshot.cells[n++];
    record->level = level; record->i = point.i; record->j = point.j;
    record->k = point.k;
    record->value[0] = internal_nozzle_probe_bits(f[]);
    record->value[1] = internal_nozzle_probe_bits(u.x[]);
    record->value[2] = internal_nozzle_probe_bits(u.y[]);
    record->value[3] = internal_nozzle_probe_bits(u.z[]);
    record->value[4] = internal_nozzle_probe_bits(g.x[]);
    record->value[5] = internal_nozzle_probe_bits(g.y[]);
    record->value[6] = internal_nozzle_probe_bits(g.z[]);
    record->value[7] = internal_nozzle_probe_bits(p[]);
    record->value[8] = internal_nozzle_probe_bits(pf[]);
  }
  n = 0;
#define INTERNAL_NOZZLE_PROBE_FACE(axis_value, component) do { \
    InternalNozzleProbeFace * record = &snapshot.faces[n++]; \
    record->axis = axis_value; record->level = level; \
    record->i = point.i; record->j = point.j; record->k = point.k; \
    record->value[0] = internal_nozzle_probe_bits(uf.component[]); \
    record->value[1] = internal_nozzle_probe_bits(fs.component[]); \
    record->value[2] = internal_nozzle_probe_bits(a.component[]); \
    record->value[3] = internal_nozzle_probe_bits(fm.component[]); \
  } while (0)
  foreach_face(x, serial) INTERNAL_NOZZLE_PROBE_FACE(0, x);
  foreach_face(y, serial) INTERNAL_NOZZLE_PROBE_FACE(1, y);
  foreach_face(z, serial) INTERNAL_NOZZLE_PROBE_FACE(2, z);
#undef INTERNAL_NOZZLE_PROBE_FACE
  n = 0;
  foreach_cell_all() {
    InternalNozzleProbeTopology * record = &snapshot.topology[n++];
    record->level = level; record->i = point.i; record->j = point.j;
    record->k = point.k;
    record->flags = internal_nozzle_probe_topology_flags(point);
    record->pid = cell.pid; record->neighbors = cell.neighbors;
  }
  qsort(snapshot.cells, (size_t) snapshot.cell_count,
        sizeof(*snapshot.cells), internal_nozzle_probe_cell_compare);
  qsort(snapshot.faces, (size_t) snapshot.face_count,
        sizeof(*snapshot.faces), internal_nozzle_probe_face_compare);
  qsort(snapshot.topology, (size_t) snapshot.topology_count,
        sizeof(*snapshot.topology), internal_nozzle_probe_topology_compare);
  snapshot.cell_key_hash = snapshot.face_key_hash = snapshot.topology_hash =
    INTERNAL_NOZZLE_PROBE_FNV_OFFSET;
  for (int field = 0; field < 9; field++)
    snapshot.cell_hash[field] = INTERNAL_NOZZLE_PROBE_FNV_OFFSET;
  for (int field = 0; field < 4; field++)
    snapshot.face_hash[field] = INTERNAL_NOZZLE_PROBE_FNV_OFFSET;
  for (uint64_t index = 0; index < snapshot.cell_count; index++) {
    InternalNozzleProbeCell * record = &snapshot.cells[index];
    snapshot.cell_key_hash = internal_nozzle_probe_fnv
      (snapshot.cell_key_hash, record, 4*sizeof(int32_t));
    for (int field = 0; field < 9; field++) {
      snapshot.cell_hash[field] = internal_nozzle_probe_fnv
        (snapshot.cell_hash[field], record, 4*sizeof(int32_t));
      snapshot.cell_hash[field] = internal_nozzle_probe_fnv
        (snapshot.cell_hash[field], &record->value[field], sizeof(uint64_t));
    }
  }
  for (uint64_t index = 0; index < snapshot.face_count; index++) {
    InternalNozzleProbeFace * record = &snapshot.faces[index];
    snapshot.face_key_hash = internal_nozzle_probe_fnv
      (snapshot.face_key_hash, record, 5*sizeof(int32_t));
    for (int field = 0; field < 4; field++) {
      snapshot.face_hash[field] = internal_nozzle_probe_fnv
        (snapshot.face_hash[field], record, 5*sizeof(int32_t));
      snapshot.face_hash[field] = internal_nozzle_probe_fnv
        (snapshot.face_hash[field], &record->value[field], sizeof(uint64_t));
    }
  }
  for (uint64_t index = 0; index < snapshot.topology_count; index++) {
    InternalNozzleProbeTopology * record = &snapshot.topology[index];
    snapshot.topology_hash = internal_nozzle_probe_fnv
      (snapshot.topology_hash, record, sizeof(*record));
  }
  return snapshot;
}

static void internal_nozzle_probe_free (InternalNozzleProbeSnapshot * snapshot)
{
  free(snapshot->cells); free(snapshot->faces); free(snapshot->topology);
  memset(snapshot, 0, sizeof(*snapshot));
}

static FILE * internal_nozzle_probe_open (void)
{
  char path[1024];
  snprintf(path, sizeof(path), "%s/nonmutation_probe.jsonl", output_dir);
  FILE * fp = fopen(path, "a");
  if (!fp) {
    fprintf(stderr, "ERROR cannot append nonmutation probe %s\n", path);
    exit(2);
  }
  return fp;
}

static int internal_nozzle_probe_same_cell_key
  (const InternalNozzleProbeCell * a, const InternalNozzleProbeCell * b)
{
  return a->level == b->level && a->i == b->i && a->j == b->j &&
    a->k == b->k;
}

static int internal_nozzle_probe_same_face_key
  (const InternalNozzleProbeFace * a, const InternalNozzleProbeFace * b)
{
  return a->axis == b->axis && a->level == b->level && a->i == b->i &&
    a->j == b->j && a->k == b->k;
}

static void internal_nozzle_probe_emit_cell_field
  (FILE * fp, const InternalNozzleProbeSnapshot * before,
   const InternalNozzleProbeSnapshot * after, const char * operation,
   const char * classification, const char * provenance, int field,
   const char * field_name)
{
  uint64_t changed = 0, first_before = 0, first_after = 0;
  int32_t first_level = 0, first_i = 0, first_j = 0, first_k = 0;
  int found = 0;
  uint64_t common = before->cell_count < after->cell_count ?
    before->cell_count : after->cell_count;
  for (uint64_t index = 0; index < common; index++) {
    const InternalNozzleProbeCell * a = &before->cells[index];
    const InternalNozzleProbeCell * b = &after->cells[index];
    if (!internal_nozzle_probe_same_cell_key(a, b) ||
        a->value[field] != b->value[field]) {
      changed++;
      if (!found) {
        found = 1; first_level = a->level; first_i = a->i;
        first_j = a->j; first_k = a->k;
        first_before = a->value[field]; first_after = b->value[field];
      }
    }
  }
  changed += before->cell_count > common ? before->cell_count - common :
    after->cell_count - common;
  fprintf(fp,
          "{\"variant\":\"%s\",\"operation\":\"%s\",\"classification\":\"%s\",\"provenance\":\"%s\",\"t\":%.17g,\"i\":%d,\"entity\":\"active_physical_cell\",\"field\":\"%s\",\"before_hash\":\"%016llx\",\"after_hash\":\"%016llx\",\"changed_count\":%llu,\"before_count\":%llu,\"after_count\":%llu,\"before_key_hash\":\"%016llx\",\"after_key_hash\":\"%016llx\",",
          INTERNAL_NOZZLE_PROBE_VARIANT, operation, classification, provenance,
          t, iter, field_name,
          (unsigned long long) before->cell_hash[field],
          (unsigned long long) after->cell_hash[field],
          (unsigned long long) changed,
          (unsigned long long) before->cell_count,
          (unsigned long long) after->cell_count,
          (unsigned long long) before->cell_key_hash,
          (unsigned long long) after->cell_key_hash);
  if (found)
    fprintf(fp, "\"first_key\":\"L%d:%d:%d:%d\",\"before_hex\":\"%016llx\",\"after_hex\":\"%016llx\"}\n",
            first_level, first_i, first_j, first_k,
            (unsigned long long) first_before,
            (unsigned long long) first_after);
  else
    fputs("\"first_key\":null,\"before_hex\":null,\"after_hex\":null}\n", fp);
}

static void internal_nozzle_probe_emit_face_field
  (FILE * fp, const InternalNozzleProbeSnapshot * before,
   const InternalNozzleProbeSnapshot * after, const char * operation,
   const char * classification, const char * provenance, int field,
   const char * field_name)
{
  uint64_t changed = 0, first_before = 0, first_after = 0;
  int32_t first_axis = 0, first_level = 0, first_i = 0, first_j = 0, first_k = 0;
  int found = 0;
  uint64_t common = before->face_count < after->face_count ?
    before->face_count : after->face_count;
  for (uint64_t index = 0; index < common; index++) {
    const InternalNozzleProbeFace * a = &before->faces[index];
    const InternalNozzleProbeFace * b = &after->faces[index];
    if (!internal_nozzle_probe_same_face_key(a, b) ||
        a->value[field] != b->value[field]) {
      changed++;
      if (!found) {
        found = 1; first_axis = a->axis; first_level = a->level;
        first_i = a->i; first_j = a->j; first_k = a->k;
        first_before = a->value[field]; first_after = b->value[field];
      }
    }
  }
  changed += before->face_count > common ? before->face_count - common :
    after->face_count - common;
  fprintf(fp,
          "{\"variant\":\"%s\",\"operation\":\"%s\",\"classification\":\"%s\",\"provenance\":\"%s\",\"t\":%.17g,\"i\":%d,\"entity\":\"actual_face\",\"field\":\"%s\",\"before_hash\":\"%016llx\",\"after_hash\":\"%016llx\",\"changed_count\":%llu,\"before_count\":%llu,\"after_count\":%llu,\"before_key_hash\":\"%016llx\",\"after_key_hash\":\"%016llx\",",
          INTERNAL_NOZZLE_PROBE_VARIANT, operation, classification, provenance,
          t, iter, field_name,
          (unsigned long long) before->face_hash[field],
          (unsigned long long) after->face_hash[field],
          (unsigned long long) changed,
          (unsigned long long) before->face_count,
          (unsigned long long) after->face_count,
          (unsigned long long) before->face_key_hash,
          (unsigned long long) after->face_key_hash);
  if (found)
    fprintf(fp, "\"first_key\":\"A%d:L%d:%d:%d:%d\",\"before_hex\":\"%016llx\",\"after_hex\":\"%016llx\"}\n",
            first_axis, first_level, first_i, first_j, first_k,
            (unsigned long long) first_before,
            (unsigned long long) first_after);
  else
    fputs("\"first_key\":null,\"before_hex\":null,\"after_hex\":null}\n", fp);
}

static void internal_nozzle_probe_compare
  (InternalNozzleProbeSnapshot * before, InternalNozzleProbeSnapshot * after,
   const char * operation, const char * classification,
   const char * provenance)
{
  static const char * cell_names[] =
    {"f", "ux", "uy", "uz", "gx", "gy", "gz", "p", "pf"};
  static const char * face_names[] = {"uf", "fs", "a", "fm"};
  FILE * fp = internal_nozzle_probe_open();
  for (int field = 0; field < 9; field++)
    internal_nozzle_probe_emit_cell_field
      (fp, before, after, operation, classification, provenance, field,
       cell_names[field]);
  for (int field = 0; field < 4; field++)
    internal_nozzle_probe_emit_face_field
      (fp, before, after, operation, classification, provenance, field,
       face_names[field]);
  uint64_t changed = 0, common = before->topology_count < after->topology_count ?
    before->topology_count : after->topology_count;
  int found = 0;
  InternalNozzleProbeTopology first_before = {0}, first_after = {0};
  for (uint64_t index = 0; index < common; index++)
    if (memcmp(&before->topology[index], &after->topology[index],
               sizeof(InternalNozzleProbeTopology))) {
      changed++;
      if (!found) {
        found = 1; first_before = before->topology[index];
        first_after = after->topology[index];
      }
    }
  changed += before->topology_count > common ?
    before->topology_count - common : after->topology_count - common;
  fprintf(fp,
          "{\"variant\":\"%s\",\"operation\":\"%s\",\"classification\":\"%s\",\"provenance\":\"%s\",\"t\":%.17g,\"i\":%d,\"entity\":\"topology\",\"field\":\"keys_flags_pid_neighbors\",\"before_hash\":\"%016llx\",\"after_hash\":\"%016llx\",\"changed_count\":%llu,\"before_count\":%llu,\"after_count\":%llu,",
          INTERNAL_NOZZLE_PROBE_VARIANT, operation, classification, provenance,
          t, iter, (unsigned long long) before->topology_hash,
          (unsigned long long) after->topology_hash,
          (unsigned long long) changed,
          (unsigned long long) before->topology_count,
          (unsigned long long) after->topology_count);
  if (found)
    fprintf(fp, "\"first_key\":\"L%d:%d:%d:%d\",\"before_hex\":\"%08x:%08x:%08x\",\"after_hex\":\"%08x:%08x:%08x\"}\n",
            first_before.level, first_before.i, first_before.j, first_before.k,
            first_before.flags, (unsigned) first_before.pid,
            (unsigned) first_before.neighbors, first_after.flags,
            (unsigned) first_after.pid, (unsigned) first_after.neighbors);
  else
    fputs("\"first_key\":null,\"before_hex\":null,\"after_hex\":null}\n", fp);
  fclose(fp);
  internal_nozzle_probe_free(before);
  internal_nozzle_probe_free(after);
}

static void internal_nozzle_probe_mark
  (const char * operation, const char * classification,
   const char * provenance)
{
  InternalNozzleProbeSnapshot before = internal_nozzle_probe_capture();
  InternalNozzleProbeSnapshot after = internal_nozzle_probe_capture();
  internal_nozzle_probe_compare
    (&before, &after, operation, classification, provenance);
}

#endif
