# Overnight Jet Workflow Handoff - 2026-06-09

## Scope

This handoff summarizes the queued jet-workflow work across:

- `dualsphysics-visualsphysics-portfolio`
- `spray-jet-geometry-reduced-model`
- `ideal-momentum-jet-explorer`

No GitHub push, YouTube upload, heavy simulation, rendering run, solver install,
or raw artifact deletion was performed in this final review pass.

## What Succeeded

### Cross-Repo Bridge

The SprayGeo to Ideal Momentum Jet Explorer bridge is now public-safe and
explicitly sample-labeled:

- SprayGeo extracts and exports geometry/model-ready metrics.
- Ideal Momentum Jet Explorer remains the fitting and visualization surface.
- DualSPHysics/source solvers are documented as future data generators.
- The current overlay is labeled as a sample synthetic geometry overlay, not a
  DualSPHysics, stationary, atomization, or validation dataset.

### Stationary Jet Metrics Contract

A canonical stationary jet geometry metrics contract was defined across repos.
The contract covers:

- downstream coordinate: `z` or `zeta`
- time/frame metadata
- post-transient and stationarity window fields
- area proxy or nondimensional area: `Ahat`
- uncertainty: `Ahat_error`
- centroid, aspect ratio, orientation
- particle count and quality flags
- source metadata: `source_type`, `simulation_source`,
  `physical_validation`, `stationarity`

The intended data flow is:

```text
solver or literature data -> SprayGeo extraction/export -> Ideal Momentum Jet Explorer overlay/import
```

This avoids duplicating fitting logic in SprayGeo.

### DualSPHysics Feasibility And Recovery

DualSPHysics remains useful as a visualization-pipeline proof, but the local
installation does not currently provide a safe 3D inlet/open-boundary case for
statistically stationary jet metrics.

The recovery path is documented:

- locate or recover official/near-official 3D inlet examples such as
  `05_SHAPESINLET3D`, `06_BOX4INLET3D`, or `8_IMPINGINGJET`
- avoid inventing XML boundary-condition assumptions
- do not substitute dam-break or splash outputs for stationary jet data

### Next Solver Route

Because DualSPHysics 3D inlet data remain blocked locally, the current next
solver recommendation is:

1. Basilisk VOF route for first post-transient solver-derived geometry data.
2. DualSPHysics official-example recovery as fallback if source-side SPH
   continuity is more important.
3. WJTSJ/literature fit-stage data as a data-first fallback after manual
   digitization is completed.

## What Is Blocked

- No safe local DualSPHysics continuous 3D inlet/open-boundary case was found.
- No statistically stationary DualSPHysics jet/spray dataset was generated.
- No fully atomized or pressure-atomization validation is available.
- The local DualSPHysics route should stay on HOLD until official examples or
  authoritative XML templates are recovered.
- WJTSJ fit-stage data remain a manual-data path until calibrated/raw exports
  are available.

## Commits Created Tonight

### dualsphysics-visualsphysics-portfolio

- `94a493e` - Document source data contract for jet metrics
- `6402095` - Document next solver route for jet geometry data
- `3ff505e` - Document DualSPHysics 3D inlet example recovery path
- `b7f993f` - Document 3D jet workflow feasibility

### spray-jet-geometry-reduced-model

- `d03db07` - Define stationary jet geometry data contract
- `98c768b` - Harden Ideal Explorer bridge metadata
- `42934d7` - Add Ideal Momentum Jet Explorer bridge

### ideal-momentum-jet-explorer

- `16581b1` - Document SprayGeo stationary metrics contract
- `db8bb95` - Harden SprayGeo overlay sample labels
- `a7ad76b` - Add SprayGeo overlay import example

## Artifact Review

No tracked prohibited solver or rendering artifacts were found in the three
reviewed repos:

- no tracked `*.bi4`
- no tracked `*.vtk`, `*.vtp`, or `*.vtu`
- no tracked `*.mp4`, `*.mov`, or `*.avi`
- no tracked `*.blend`
- no tracked raw frame directories
- no tracked log files

Tracked file-size checks found only small curated project assets. The largest
tracked SprayGeo benchmark CSV is below the 5 MB per-file public-release cap.

The Ideal Momentum Jet Explorer working tree contains local `node_modules`
dependency files, including some large packages and dependency logs, but these
are not tracked project artifacts.

## Wording And Caveat Review

Risk terms were searched across the three repos:

- `validated`
- `validation`
- `production`
- `atomization`
- `experimental agreement`
- `fully atomized`

The remaining uses are caveated or contextual. The preserved public position is:

- DualSPHysics output is a visualization-pipeline demo unless a future 3D inlet
  case is recovered and run.
- SprayGeo uses synthetic benchmarks plus tiny solver-adapter proofs; it is not
  physical pressure-atomization validation.
- Ideal Momentum Jet Explorer overlays are exploratory inputs and do not create
  experimental agreement or engineering validation.
- Gemini/Vertex/Cloud AI language remains roadmap or no-API scaffold language,
  not deployed cloud integration.

## Checks Run

- `git status --short --branch` in all three repos
- `git log --oneline --decorate -8` in all three repos
- tracked prohibited-artifact scan in all three repos
- tracked file-size scan in all three repos
- wording-risk scans in all three repos
- `git diff --check` in all three repos before this handoff doc

Earlier bridge hardening checks already run during this queued block included:

- SprayGeo Python compile and focused tests
- SprayGeo export bridge tests
- Ideal Momentum Jet Explorer `npm run test`
- Ideal Momentum Jet Explorer `npm run build`

## Exact Next Human Decision

Choose the next data-source route:

1. Approve the Basilisk VOF route for first post-transient solver-derived jet
   geometry data.
2. Or prioritize recovering official DualSPHysics 3D inlet examples before any
   more solver work.
3. Or complete WJTSJ/literature digitization first and use measured/literature
   geometry data as the first serious model-fit input.

Recommended decision: proceed with the Basilisk VOF route unless maintaining a
DualSPHysics-only story is more important than reaching first stationary
geometry data.

## Recommended Next Codex Prompt

```text
Continue from the active jet-workflow goal.

Objective:
Run a bounded Basilisk VOF post-transient jet-geometry candidate workflow for
SprayGeo and Ideal Momentum Jet Explorer handoff.

Constraints:
- no installs, no sudo, no downloads, no API calls, no push
- no physical validation or fully atomized spray claims
- raw solver outputs outside Git
- commit only small docs/scripts/curated metrics

Tasks:
1. Inspect local Basilisk qcc and available examples.
2. Select the smallest safe VOF jet/atomisation-like case or documented toy case.
3. Run a bounded low-resolution smoke case only if qcc and headers are present.
4. Export small CSV field/geometry data.
5. Convert to the stationary jet geometry metrics contract.
6. Create SprayGeo metrics and Ideal Explorer overlay only if post-transient
   frames are meaningful.
7. Document limitations and stop before any validation claim.
```

Stop if qcc is missing, no safe case exists, the output is not jet/spray-like,
no post-transient window can be identified, outputs grow too large, or any text
would imply physical validation.
