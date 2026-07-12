# Quarter-domain bounded execution recipe

This recipe compiles one dual-mode Basilisk source and runs a short matched
quarter/full pair. It is Task 02 smoke validation, not the Task 03 benchmark.

## Preconditions and limits

- Branch: `review/basilisk-quarter-domain-20260711`
- Basilisk `qcc`: `/home/franco/opt/basilisk-survey-20260606/basilisk/src/qcc`
- Output stays outside Git under the Task 02 output root.
- Default OpenMP threads: `4`.
- Compile timeout: `180 s`; each solver timeout: `300 s`.
- Default smoke: maxlevel 5, baselevel 4, `t_end = 0.006`, three-millisecond cadence.
- Stop before any long duration, refinement matrix, or production media.
- Keep at least 20 GiB free on the `/home` execution/output volume.

## Bounded smoke pair

From the repository worktree:

```sh
python3 scripts/run_quarter_domain_smoke.py \
  --output-root /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/smoke/attempt-1
```

The runner uses an isolated temporary qcc build directory, captures compile and
solver logs, passes identical arguments to both cases except `--domain`, and
writes `run_manifest.json`. It refuses a nonempty output directory instead of
overwriting prior evidence.

## Render-only reconstruction

```sh
python3 scripts/reconstruct_quarter_domain.py \
  --input /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/smoke/attempt-1/quarter/vof_surfaces/vof_facets_0000.facets \
  --output-dir /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/reconstruction/attempt-1 \
  --manifest /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/reconstruction/attempt-1/reconstruction_manifest.json
```

Additional quarter facet inputs may be repeated with `--input`. The result is
always render-only and must retain the persistent non-full-physics label.

## Quantitative QA

```sh
python3 scripts/validate_quarter_domain.py \
  --smoke-root /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/smoke/attempt-1 \
  --reconstruction-manifest /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/reconstruction/attempt-1/reconstruction_manifest.json \
  --output-json /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/qa/attempt-1/quarter_domain_qa.json \
  --output-report /home/franco/stack-validation/20260711-basilisk-quarter-internal-brand-portfolio/task-02-quarter-domain-design/qa/attempt-1/QUARTER_DOMAIN_SMOKE_QA.md
```

The coarse smoke tolerance is 35% for four-times-quarter versus full integral
metrics. This is a compile/BC/control sanity gate, not an accuracy or
convergence threshold. Task 03 must define stricter benchmark acceptance before
using a speedup result.

## Source and Python gates

```sh
python3 -m py_compile \
  scripts/run_quarter_domain_smoke.py \
  scripts/reconstruct_quarter_domain.py \
  scripts/validate_quarter_domain.py
python3 -m unittest tests.test_quarter_domain_tools
git diff --check
```

The Task 02 result is then validated against
`schemas/task_result.schema.json` from the authoritative runbook branch. Do not
commit solver outputs, facets, binaries, logs, caches, or generated media.

## Task 03 authorization

Proceed only when `quarter_domain_qa.json` contains both:

```json
{
  "passed": true,
  "task03_authorization": "go_bounded_benchmark"
}
```

Even then, Task 03 remains bounded and must preserve `fit_ready=false` and
`public_ready=false`. A failure means repair Task 02 within its remaining retry
budget or stop for human scientific review.
