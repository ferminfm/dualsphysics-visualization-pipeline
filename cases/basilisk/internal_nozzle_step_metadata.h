#ifndef INTERNAL_NOZZLE_STEP_METADATA_H
#define INTERNAL_NOZZLE_STEP_METADATA_H
/* Strict versioned metadata for the pure accepted-step accumulator. These
 * eight fields extend metadata_v8; the base checkpoint remains native dump
 * plus its existing v4 prediction closure. No scientific quantity is reset
 * or reconstructed from sparse output during restore. */
#include "internal_nozzle_step_integral.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define INTERNAL_NOZZLE_STEP_SCHEMA "internal_nozzle_accepted_step_integral_v1"

static inline int internal_nozzle_step_metadata_field
  (const char *line, InternalNozzleStepIntegral *state,
   unsigned *seen, double *scale)
{
  const char *keys[] = {"accepted_step_schema", "accepted_step_count",
    "accepted_step_iteration", "accepted_step_time", "accepted_step_previous_Q",
    "accepted_step_net_volume", "accepted_step_positive_volume",
    "accepted_step_nozzle_scale"};
  if (strncmp(line, "accepted_step_", 14)) return 0;
  const char *sep = strchr(line, '=');
  if (!sep) return -1;
  int index = -1;
  for (int n = 0; n < 8; n++)
    if (strlen(keys[n]) == (size_t)(sep-line) &&
        !strncmp(line, keys[n], (size_t)(sep-line))) index = n;
  if (index < 0 || (*seen & (1u << index))) return -1;
  const char *value = sep+1;
  char *end = NULL;
  if (!*value || *value == ' ' || *value == '\t' || *value == '+') return -1;
  errno = 0;
  if (index == 0) {
    size_t len = strlen(INTERNAL_NOZZLE_STEP_SCHEMA);
    if (strncmp(value, INTERNAL_NOZZLE_STEP_SCHEMA, len) ||
        (value[len] != '\0' && !(value[len] == '\n' && value[len+1] == '\0')))
      return -1;
  }
  else if (index == 1) {
    if (*value < '0' || *value > '9') return -1;
    uintmax_t count = strtoumax(value, &end, 10);
    if (errno || count >= UINT64_MAX) return -1;
    state->accepted_steps = (uint64_t)count;
  }
  else if (index == 2) {
    if ((*value < '0' || *value > '9') && *value != '-') return -1;
    intmax_t iteration = strtoimax(value, &end, 10);
    if (errno || iteration < -1 || iteration >= INT64_MAX) return -1;
    state->last_iteration = (int64_t)iteration;
  }
  else {
    double result = strtod(value, &end);
    if (errno || !isfinite(result)) return -1;
    switch (index) {
    case 3: state->time = result; break;
    case 4: state->previous_flow = result; break;
    case 5: state->net_volume = result; break;
    case 6: state->positive_volume = result; break;
    case 7: *scale = result; break;
    }
  }
  if (index && (end == value ||
      (*end != '\0' && !(*end == '\n' && end[1] == '\0')))) return -1;
  *seen |= 1u << index;
  return 1;
}

static inline int internal_nozzle_step_metadata_complete
  (InternalNozzleStepIntegral *state, unsigned seen, double scale,
   double expected_scale, int64_t checkpoint_iteration, double checkpoint_end)
{
  if (seen != 255u || !isfinite(scale) || !(scale > 0.) ||
      scale != expected_scale || state->last_iteration != checkpoint_iteration ||
      state->time != checkpoint_end) return 0;
  state->initialized = 1;
  return internal_nozzle_step_integral_valid(state);
}

static inline int internal_nozzle_step_metadata_write
  (FILE *stream, const InternalNozzleStepIntegral *state, double scale)
{
  if (!internal_nozzle_step_integral_valid(state) || !isfinite(scale) || !(scale > 0.))
    return 0;
  return fprintf(stream,
    "accepted_step_schema=" INTERNAL_NOZZLE_STEP_SCHEMA "\n"
    "accepted_step_count=%" PRIu64 "\n"
    "accepted_step_iteration=%" PRId64 "\n"
    "accepted_step_time=%.17g\naccepted_step_previous_Q=%.17g\n"
    "accepted_step_net_volume=%.17g\naccepted_step_positive_volume=%.17g\n"
    "accepted_step_nozzle_scale=%.17g\n",
    state->accepted_steps, state->last_iteration, state->time,
    state->previous_flow, state->net_volume, state->positive_volume, scale) > 0;
}
#endif
