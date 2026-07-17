#ifndef INTERNAL_NOZZLE_PROJECTION_TRACE_H
#define INTERNAL_NOZZLE_PROJECTION_TRACE_H

/*
 * Observation-only hooks used by the Task 01 projection/restart forensics
 * build.  The task-local Basilisk poisson.h calls these hooks only when
 * INTERNAL_NOZZLE_PROJECTION_TRACE is defined.  They do not call boundary(),
 * restriction(), adaptation, or any solver routine.
 */
void internal_nozzle_projection_trace_stage
  (const char * stage, face vector uf_trace, scalar pressure_trace,
   (const) face vector alpha_trace, scalar div_trace,
   double projection_dt, int requested_nrelax);

void internal_nozzle_prediction_trace_stage
  (const char * stage, face vector uf_trace,
   (const) face vector alpha_trace);

void internal_nozzle_poisson_trace_stage
  (const char * stage, scalar pressure_trace, scalar rhs_trace,
   (const) face vector alpha_trace, (const) scalar lambda_trace,
   double tolerance, int nrelax, int minlevel);

void internal_nozzle_mg_trace_stage
  (const char * stage, scalar * solution, scalar * rhs,
   scalar * residual_trace, scalar * correction_trace,
   int cycle, int active_level, int nrelax, double residual_value);

void internal_nozzle_projection_trace_summary
  (scalar pressure_trace, int iterations, double residual_before,
   double residual_after, double rhs_sum, int nrelax, int minlevel);

#endif
