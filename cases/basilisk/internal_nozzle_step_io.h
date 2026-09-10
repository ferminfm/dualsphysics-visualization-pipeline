#ifndef INTERNAL_NOZZLE_STEP_IO_H
#define INTERNAL_NOZZLE_STEP_IO_H
/* Case-owned I/O for a distinct, versioned same-step coordinate. The legacy
 * output-driven columns are preserved unchanged and remain unqualified. */
static void internal_nozzle_write_step_state (const char *leafname) {
  if (!internal_nozzle_step_integral_valid(&accepted_step_state)) return;
  char path[1024]; output_path(path, sizeof(path), leafname);
  FILE *stream = fopen(path, "w");
  if (!stream) { fprintf(stderr,"ERROR accepted-step state output\n"); exit(2); }
  fprintf(stream,
    "{\"schema\":\"" INTERNAL_NOZZLE_STEP_SCHEMA "\","
    "\"accepted_steps\":%" PRIu64 ",\"last_iteration\":%" PRId64 ","
    "\"time\":%.17g,\"previous_flow\":%.17g,\"net_volume\":%.17g,"
    "\"positive_volume\":%.17g,\"execution_id\":\"%s\",\"case_role\":\"%s\","
    "\"source_commit\":\"%s\",\"solver_sha256\":\"%s\",\"schedule_sha256\":\"%s\","
    "\"nozzle_scale_volume\":%.17g}\n",
    accepted_step_state.accepted_steps, accepted_step_state.last_iteration,
    accepted_step_state.time, accepted_step_state.previous_flow,
    accepted_step_state.net_volume, accepted_step_state.positive_volume,
    execution_id, case_role, scientific_source_commit, solver_sha256,
    schedule_sha, A0*Dhrect);
  if (fclose(stream)) { fprintf(stderr,"ERROR accepted-step state flush\n"); exit(2); }
}

static void internal_nozzle_start_step_integral (void) {
  if (restore_requested) {
    /* metadata_v7 has no same-step record and is diagnostic-only. Never
     * invent its missing prefix or initialize a resumed cumulative zero. */
    internal_nozzle_write_step_state("accepted_step_initial_state.json");
    return;
  }
  double flow, pressure_unused;
  hydraulic_plane_flow_and_pressure(6, &flow, &pressure_unused);
  if (!internal_nozzle_step_integral_init(&accepted_step_state, t, flow)) {
    fprintf(stderr,"ERROR accepted-step fresh initialization\n"); exit(2);
  }
  internal_nozzle_write_step_state("accepted_step_initial_state.json");
}

static void internal_nozzle_capture_accepted_step (int iteration) {
  if (!accepted_step_state.initialized) {
    if (restore_requested && diagnostic_restore_source_commit[0]) return;
    fprintf(stderr,"ERROR missing accepted-step initial state\n"); exit(2);
  }
  /* Native restore advances the scheduler through the checkpoint iteration;
   * any zero-time revisit must not repeat its already-completed interval. */
  if (restored_ok && iteration == recovered_checkpoint_iteration) return;
  double flow, pressure_unused, net_increment, positive_increment;
  hydraulic_plane_flow_and_pressure(6, &flow, &pressure_unused);
  const double left = accepted_step_state.previous_flow;
  const double begin = t, end = t + dt;
  if (!internal_nozzle_step_integral_advance
      (&accepted_step_state, accepted_step_state.accepted_steps+1, iteration,
       begin, end, flow, 1, &net_increment, &positive_increment)) {
    fprintf(stderr,"ERROR noncontiguous accepted-step trace at i=%d t=%.17g dt=%.17g previous_end=%.17g\n",
            iteration,t,dt,accepted_step_state.time); exit(2);
  }
  char path[1024]; output_path(path, sizeof(path), "accepted_step_integral.csv");
  int exists = file_exists_nonzero(path);
  FILE *stream = fopen(path, "a");
  if (!stream) { fprintf(stderr,"ERROR accepted-step trace output\n"); exit(2); }
  if (!exists)
    fputs("schema,step_index,iteration,accepted,begin,end,dt,Q_left,Q_right,net_increment,positive_increment,net_volume,positive_volume,normalized_net_volume,normalized_positive_volume,stage,phase_convention,functional,plane,quadrature,execution_id,case_role,source_commit,solver_sha256,schedule_sha256\n",stream);
  fprintf(stream,
    INTERNAL_NOZZLE_STEP_SCHEMA ",%" PRIu64 ",%d,true,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
    "end_timestep_after_projection_before_adaptation,VOF_at_step_midpoint_velocity_at_step_end,"
    "trapezoid_net_plane_Q_l_and_endpoint_clipped_net_Q_l,exit,exact_rectangular_aperture_leaf_overlap_v1,"
    "%s,%s,%s,%s,%s\n",
    accepted_step_state.accepted_steps,iteration,begin,end,end-begin,left,flow,
    net_increment,positive_increment,accepted_step_state.net_volume,
    accepted_step_state.positive_volume,accepted_step_state.net_volume/(A0*Dhrect),
    accepted_step_state.positive_volume/(A0*Dhrect),execution_id,case_role,
    scientific_source_commit,solver_sha256,schedule_sha);
  if (fclose(stream)) { fprintf(stderr,"ERROR accepted-step trace flush\n"); exit(2); }
}
#endif
