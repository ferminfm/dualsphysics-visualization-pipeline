#include "internal_nozzle_step_metadata.h"
int initialize(InternalNozzleStepIntegral *s, double t, double q) {
  return internal_nozzle_step_integral_init(s,t,q);
}
int advance(InternalNozzleStepIntegral *s, uint64_t k, int64_t i,
            double a, double b, double q, int accepted) {
  return internal_nozzle_step_integral_advance(s,k,i,a,b,q,accepted,0,0);
}
int valid(InternalNozzleStepIntegral *s) {
  return internal_nozzle_step_integral_valid(s);
}
int metadata_field(const char *line, InternalNozzleStepIntegral *s,
                   unsigned *mask, double *scale) {
  return internal_nozzle_step_metadata_field(line,s,mask,scale);
}
int metadata_complete(InternalNozzleStepIntegral *s, unsigned mask,
                      double scale, double expected_scale,
                      int64_t iteration, double end) {
  return internal_nozzle_step_metadata_complete(s,mask,scale,expected_scale,iteration,end);
}
