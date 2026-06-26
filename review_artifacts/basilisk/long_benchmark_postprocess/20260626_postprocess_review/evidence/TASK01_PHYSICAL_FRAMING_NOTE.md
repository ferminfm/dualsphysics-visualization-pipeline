# Physical Framing Note

Task: `01_physical_framing_claim_strategy`

Status: `physical_framing_ready`

This note frames the existing long Basilisk benchmark as internal scientific-computing evidence, not as a validated physical spray prediction or public-ready asset.

## Evidence Read

- Runbook: `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/tasks/01_physical_framing_claim_strategy/CODEX_TASK_INSTRUCTIONS.md`
- Guardrails: `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/COMMON_GUARDRAILS.md`
- Manifest: `/home/franco/Documents/GitHub/ai-agent-runbooks/basilisk/20260626-long-benchmark-postprocess-publicprep-batch/BATCH_MANIFEST.json`
- Review packet: `review_artifacts/basilisk/rectangular_pulsed_profile_atomisation/20260625_long_showcase_review/`
- Canonical source: `cases/basilisk/official_rectangular_pulsed_atomisation.c`
- Source docs: `docs/basilisk_rectangular_pulsed_profile_benchmark.md` and `docs/basilisk_rectangular_pulsed_profile_long_benchmark_status.md`

## Current Nondimensional Setup

The canonical source is a bounded Basilisk two-phase VOF benchmark derived from the local official atomisation-style control and extended with rectangular imposed-inlet profile variants.

Recorded source parameters:

| Quantity | Current value | Evidence |
| --- | ---: | --- |
| Liquid inlet radius | `1/12 = 0.08333333333333333` | canonical source and status doc |
| Initial liquid length | `0.025` | canonical source |
| Reynolds number | `5800` | canonical source and status doc |
| Surface-tension coefficient | `3e-5` | canonical source and status doc |
| Liquid density | `rho1 = 1` | canonical source |
| Ambient/second-phase density | `rho2 = rho1 / 27.84` | canonical source |
| Density ratio | `rho1/rho2 = 27.84` | canonical source and status doc |
| Mean inlet speed scale | `u0 = 1` | canonical source |
| Pulse amplitude | `0.05` | canonical source and status doc |
| Pulse period | `0.1` | canonical source and status doc |
| Inlet velocity | `u0 * (1 + 0.05 * sin(2*pi*t/0.1))` | canonical source |
| Domain | `x in [0,3]`, `y,z in [-1.5,1.5]` | canonical source and boundary audit |
| Long-run final time | `t=2.0` | status docs and review packet |
| Long-run frames | `101` physical frames per long route | status docs and review packet |
| Long-run maxlevel | `8` | review packet manifests |
| Gravity | no body-force/gravity vector assigned in current source/run | runbook, guardrails, source inspection |

The source uses `navier-stokes/centered.h`, `two-phase.h`, and `tension.h`. It represents two incompressible phases through the VOF fraction field `f`, with density and viscosity set by `rho1`, `rho2`, `mu1`, and `mu2`; surface tension is active through `f.sigma = SIGMA`.

## Selected Routes

| Route | Profile | Role | Current classification |
| --- | --- | --- | --- |
| `official_round_control` | `round_official_top_hat` | Primary internal visual/scientific lead | `official_round_benchmark_candidate_supported` |
| `C1_rect_area_top_hat` | `rect_area_top_hat` | Secondary caveated comparison | `rectangular_candidate_resolution_sensitive` |

The rectangular comparison is a 2:1 area-matched rectangular top-hat imposed at the inlet boundary. Its recorded geometry is:

- area: `A0 = 0.02181661564992912`
- width: `W = 0.20888568955258338`
- height: `H = 0.10444284477629169`
- hydraulic diameter: `0.1392571263683889`

The rectangular route is not Poiseuille and not internal-nozzle flow. Poiseuille-series profiles were implemented and tested, but they were not selected by the bounded candidate gate.

## Physical Interpretation

The current evidence is best described as a nondimensional two-phase VOF pulsed-jet benchmark. It is useful for inspecting interface topology, solver-derived media integrity, and postprocessing discipline under a documented parameter set.

It should not be described as ordinary room-condition water injected into air because:

- the density ratio is `27.84`, far denser on the ambient side than ordinary room air relative to water;
- no gravity/body-force term is active in the current benchmark;
- the surface-tension coefficient is a nondimensional Basilisk setting, not a direct room-condition fluid property by itself;
- the rectangular comparison imposes a velocity profile at the inlet plane rather than resolving a plenum, contraction, boundary layer, or nozzle-exit development;
- the rectangular branch is resolution-sensitive and should not support final quantitative breakup claims;
- thresholded component counts are diagnostics, not validated droplet statistics.

## Safe Physical Analogs

The safest analog language is qualified:

- Dense-ambient two-phase pulsed-jet benchmark.
- Process-fluid breakup analogue in a controlled chamber where gravity is secondary or intentionally omitted.
- Solver-derived morphology review for spray, coating, and cleaning workflow concepts.
- Low-gravity or no-gravity two-phase interface-topology benchmark.

These analogs are not validation claims. They should be used only to explain why the benchmark is technically relevant.

## Current Readiness Flags

- `fit_ready=false`
- `public_ready=false`
- `physical_framing_ready=true`
- `publication_blocked_until_human_review=true`
