#ifndef INTERNAL_NOZZLE_STENCIL_METADATA_H
#define INTERNAL_NOZZLE_STENCIL_METADATA_H
#include <stdio.h>
#include <string.h>

/* Native boundary-validity bits, not new boundary conditions. Exact order:
 * u.x,u.y,u.z,g.x,g.y,g.z,cs. io/width are loop-local and are not persistent.
 * Captured only with the same keyed field/topology checkpoint. */
typedef struct { unsigned seen; int bc[7]; } InternalNozzleStencilMetadata;

static int internal_nozzle_stencil_metadata_field
  (const char * line, InternalNozzleStencilMetadata * state)
{
  if (!strncmp(line, "stencil_closure_schema=", 23)) {
    if (state->seen & 1u || strcmp(line,
        "stencil_closure_schema=internal_nozzle_stencil_bc_v1\n")) return -1;
    state->seen |= 1u; return 1;
  }
  if (!strncmp(line, "stencil_bc=", 11)) {
    if (state->seen & 2u) return -1;
    const char * p = line + 11;
    for (int k = 0; k < 7; k++) {
      if (*p < '0' || *p > '7') return -1;
      state->bc[k] = *p++ - '0';
      if (k < 6 && *p++ != ',') return -1;
    }
    if (strcmp(p, "\n")) return -1;
    state->seen |= 2u; return 1;
  }
  return !strncmp(line,"stencil_",8) ? -1 : 0;
}

static int internal_nozzle_stencil_metadata_complete
  (const InternalNozzleStencilMetadata * state)
{
  if (state->seen != 3u) return 0;
  for (int k = 0; k < 7; k++) if (state->bc[k] < 0 || state->bc[k] > 7) return 0;
  return 1;
}

static int internal_nozzle_stencil_metadata_write
  (FILE * stream, const InternalNozzleStencilMetadata * state)
{
  if (!internal_nozzle_stencil_metadata_complete(state)) return 0;
  return fprintf(stream,
    "stencil_closure_schema=internal_nozzle_stencil_bc_v1\n"
    "stencil_bc=%d,%d,%d,%d,%d,%d,%d\n",
    state->bc[0],state->bc[1],state->bc[2],state->bc[3],
    state->bc[4],state->bc[5],state->bc[6]) > 0;
}
#endif
