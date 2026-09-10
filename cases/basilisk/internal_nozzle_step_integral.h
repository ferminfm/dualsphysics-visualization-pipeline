#ifndef INTERNAL_NOZZLE_STEP_INTEGRAL_H
#define INTERNAL_NOZZLE_STEP_INTEGRAL_H
/* Pure bookkeeping, not a solver or a replacement for native dump/restore.
 * Temporal functional: endpoint trapezoid of the declared staged plane Q_l.
 * Positive discharge clips the NET plane flow, not the local velocity field.
 * Each call represents exactly one accepted interval. Output events never call
 * this update. The caller owns native event phase and checkpoint provenance.
 */
#include <math.h>
#include <stdint.h>

typedef struct {
  uint64_t accepted_steps;
  int64_t last_iteration;
  double time, previous_flow, net_volume, positive_volume;
  int initialized;
} InternalNozzleStepIntegral;

static int internal_nozzle_step_integral_valid
  (const InternalNozzleStepIntegral *s)
{
  return s && s->initialized == 1 && isfinite(s->time) && s->time >= 0. &&
    isfinite(s->previous_flow) && isfinite(s->net_volume) &&
    isfinite(s->positive_volume) && s->positive_volume >= 0. &&
    s->last_iteration >= -1 && s->last_iteration < INT64_MAX &&
    s->accepted_steps < UINT64_MAX &&
    s->accepted_steps == (uint64_t)(s->last_iteration + 1);
}

static int internal_nozzle_step_integral_init
  (InternalNozzleStepIntegral *s, double time, double flow)
{
  if (!s || !isfinite(time) || time != 0. || !isfinite(flow)) return 0;
  *s = (InternalNozzleStepIntegral){0, -1, time, flow, 0., 0., 1};
  return 1;
}

static int internal_nozzle_step_integral_advance
  (InternalNozzleStepIntegral *s, uint64_t next_step, int64_t iteration,
   double begin, double end, double flow, int accepted,
   double *net_increment, double *positive_increment)
{
  if (!internal_nozzle_step_integral_valid(s) ||
      (accepted != 0 && accepted != 1)) return 0;
  /* A rejected solver attempt is not an accepted time interval. */
  if (!accepted) return 1;
  if (next_step != s->accepted_steps + 1 ||
      iteration != s->last_iteration + 1 ||
      iteration >= INT64_MAX ||
      !isfinite(begin) || !isfinite(end) || !isfinite(flow) ||
      fabs(begin - s->time) > 1e-12 || !(end > begin)) return 0;
  const double interval = end - begin;
  const double net = 0.5*(s->previous_flow + flow)*interval;
  const double pos = 0.5*(fmax(s->previous_flow, 0.) + fmax(flow, 0.))*interval;
  const double net_total = s->net_volume + net;
  const double pos_total = s->positive_volume + pos;
  if (!isfinite(net) || !isfinite(pos) || !isfinite(net_total) ||
      !isfinite(pos_total)) return 0;
  s->accepted_steps = next_step;
  s->last_iteration = iteration;
  s->time = end;
  s->previous_flow = flow;
  s->net_volume = net_total;
  s->positive_volume = pos_total;
  if (net_increment) *net_increment = net;
  if (positive_increment) *positive_increment = pos;
  return 1;
}
#endif
