#ifndef INTERNAL_NOZZLE_RESTART_LITE_V1_H
#define INTERNAL_NOZZLE_RESTART_LITE_V1_H

#include <string.h>

static const char * restart_lite_checkpoint = "restart-lite.dump";
static int restart_lite_restored;
static int restart_lite_checkpoint_count;
static double restart_lite_next_dt;

static char * restart_lite_state_path (const char * suffix)
{
  char * path = malloc (strlen (restart_lite_checkpoint) + strlen (suffix) + 1);
  if (!path) {
    fputs ("restart-lite sidecar allocation failed\n", stderr);
    exit (2);
  }
  sprintf (path, "%s%s", restart_lite_checkpoint, suffix);
  return path;
}

static void restart_lite_restore_state (void)
{
  char * path = restart_lite_state_path (".state");
  FILE * fp = fopen (path, "r");
  if (!fp) {
    perror (path);
    free (path);
    exit (2);
  }
  int version = 0, state_iter = -1, checkpoint_count = -1;
  double state_t = -1., next_dt = -1.;
  int matched = fscanf (fp,
                        "restart_lite_v2 %d\niter %d\ntime %la\nnext_dt %la\n"
                        "checkpoint_count %d\n",
                        &version, &state_iter, &state_t, &next_dt,
                        &checkpoint_count);
  if (fclose (fp)) {
    perror (path);
    free (path);
    exit (2);
  }
  free (path);
  if (matched != 5 || version != 2 || state_iter != iter || state_t != t ||
      !isfinite (next_dt) || next_dt <= 0. || checkpoint_count < 0) {
    fputs ("restart-lite sidecar does not match the native dump\n", stderr);
    exit (2);
  }
  restart_lite_next_dt = next_dt;
  restart_lite_checkpoint_count = checkpoint_count;
}

static void restart_lite_write_state (scalar * fields)
{
  char * path = restart_lite_state_path (".state");
  char * temporary = restart_lite_state_path (".state~");
  FILE * fp = fopen (temporary, "w");
  if (!fp) {
    perror (temporary);
    free (path);
    free (temporary);
    exit (2);
  }
  fprintf (fp,
           "restart_lite_v2 2\niter %d\ntime %a\nnext_dt %a\n"
           "checkpoint_count %d\n",
           iter, t, dt, restart_lite_checkpoint_count);
  if (fclose (fp)) {
    perror (temporary);
    free (path);
    free (temporary);
    exit (2);
  }
  dump (file = restart_lite_checkpoint, list = fields);
  if (rename (temporary, path)) {
    perror (path);
    free (path);
    free (temporary);
    exit (2);
  }
  free (path);
  free (temporary);
}

static bool restart_lite_restore (void)
{
  restart_lite_restored = restore (file = restart_lite_checkpoint);
  if (restart_lite_restored)
    restart_lite_restore_state();
  return restart_lite_restored;
}

static void restart_lite_dump (void)
{
  restart_lite_write_state (all);
}

static void restart_lite_dump_fields (scalar * fields)
{
  restart_lite_write_state (fields);
}

#endif
