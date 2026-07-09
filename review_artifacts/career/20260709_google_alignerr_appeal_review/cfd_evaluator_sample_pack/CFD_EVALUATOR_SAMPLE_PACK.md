# CFD Evaluator Sample Pack

These examples use a consistent rubric:

- Physics correctness
- Boundary and initial conditions
- Nondimensional and scaling logic
- Numerical method and resolution evidence
- Visualization/data support
- Scope and overclaim control
- Actionability

Scores use 1 = weak, 3 = acceptable with caveats, and 5 = strong.

## Sample 1: Connected VOF Waviness Is Not Breakup

### Prompt

An AI answer says: "The VOF jet has atomized because the final rendered image shows a wavy, stretched liquid interface downstream of the inlet."

### Verdict

Fail as written. A connected wavy interface is not sufficient evidence of breakup or atomisation.

### Key Issues

- The claim relies on a rendered image rather than topology/component diagnostics.
- Connected waviness can indicate deformation, ligament stretching, or transient interface growth, but not detached liquid structures by itself.
- One-cell debris, projection artifacts, pre-exit components, or boundary clipping cannot be counted as detached fragments.
- A credible breakup proxy needs persistent post-exit components, detached-liquid counts, component volumes, and visual/topological agreement.

### Rubric Scores

| Dimension | Score | Rationale |
|---|---:|---|
| Physics correctness | 2 | Recognizes free-surface deformation but overstates the morphology. |
| Boundary and initial conditions | 3 | Boundary details are not necessarily wrong, but they are not checked. |
| Nondimensional and scaling logic | 2 | No Re, We, or advective-time context is given. |
| Numerical method and resolution evidence | 2 | No grid sensitivity or debris filtering is discussed. |
| Visualization/data support | 1 | Render alone does not support the claim. |
| Scope and overclaim control | 1 | Uses atomisation language without evidence. |
| Actionability | 3 | Can be repaired with component and topology checks. |

### Safe Corrected Wording

> The frame shows a connected VOF interface with downstream waviness and interface growth. It is an exploratory morphology visualization, not evidence of validated atomisation. A breakup-proxy claim would require topology diagnostics showing persistent, credible post-exit detached liquid components beyond one-cell debris or projection artifacts.

### Evidence Needed For A Stronger Claim

- Component labels over time with volume and cell-count filters.
- Detached-component counts excluding pre-exit and one-cell artifacts.
- Matched visual frames and component diagnostics.
- Resolution/time sensitivity check at the same physical times.
- Boundary-clearance audit showing structures are not clipped by domain boundaries.

## Sample 2: Pressure Heatmaps From Zero-Range Restored Pressure

### Prompt

An AI answer includes pressure heatmaps generated from a restored Basilisk checkpoint where the recovered pressure field has zero range.

### Verdict

Fail. A zero-range restored pressure field is not a valid pressure visualization.

### Key Issues

- If the restored pressure field is constant or zero-range, a heatmap would be visually fabricated or numerically meaningless.
- Pressure may be intentionally omitted from dumps unless explicitly exported during runtime.
- A valid pressure panel must use real nonzero pressure data with provenance and units or normalized scale clearly defined.
- Replacing a missing pressure field with a colored panel creates false evidence.

### Rubric Scores

| Dimension | Score | Rationale |
|---|---:|---|
| Physics correctness | 2 | Pressure is relevant, but unavailable data are treated as available. |
| Boundary and initial conditions | 3 | Not central to this error. |
| Nondimensional and scaling logic | 2 | No pressure scale or normalization is justified. |
| Numerical method and resolution evidence | 2 | Does not explain checkpoint/export limitations. |
| Visualization/data support | 1 | The plotted field does not support a pressure claim. |
| Scope and overclaim control | 1 | Presents missing evidence as real evidence. |
| Actionability | 4 | Clear fix: remove panel or export pressure correctly in a future run. |

### Safe Corrected Wording

> Pressure visualization is blocked for this checkpoint because restored `p` has zero range. The review should show only fields that are actually available, such as phase indicator, velocity magnitude, and diagnostic vorticity magnitude, and should document a future runtime pressure-export branch.

### Evidence Needed For A Stronger Claim

- Source-level confirmation that pressure is dumped or explicitly written after projection.
- Runtime pressure export at selected frames.
- Restored pressure range compared with runtime pressure range.
- Units or nondimensional pressure scaling.
- Gradient-derived diagnostics only after validating the gradient tensor export.

## Sample 3: Pressure-Driven Internal Nozzle Versus Imposed-Inlet Comparison

### Prompt

An AI answer says: "The rectangular top-hat imposed-inlet case validates the pressure-driven internal-nozzle workflow because both show rectangular liquid jets."

### Verdict

Fail. The comparison confuses two different physical setups.

### Key Issues

- A pressure-driven internal-nozzle case includes plenum/contraction/wall development and should not impose a uniform exit velocity at the visual nozzle exit.
- An imposed-inlet rectangular top-hat case can be a controlled benchmark or visualization comparison, but it does not resolve internal nozzle flow.
- Similar downstream visual shape does not prove equivalent boundary conditions, velocity profiles, pressure forcing, or internal-wall development.
- Aperture-mask or imposed-inlet evidence must not be treated as internal-nozzle validation.

### Rubric Scores

| Dimension | Score | Rationale |
|---|---:|---|
| Physics correctness | 2 | Rectangular geometry is relevant, but the physical interpretation is wrong. |
| Boundary and initial conditions | 1 | The main boundary-condition distinction is erased. |
| Nondimensional and scaling logic | 2 | Does not separate area, flux, velocity profile, and forcing differences. |
| Numerical method and resolution evidence | 3 | Could still be numerically useful as a comparison, with caveats. |
| Visualization/data support | 2 | Visual resemblance is overused as physics evidence. |
| Scope and overclaim control | 1 | Treats a benchmark comparison as validation. |
| Actionability | 4 | Can be repaired by relabeling and separating evidence tiers. |

### Safe Corrected Wording

> The rectangular top-hat imposed-inlet case is a benchmark comparison and visualization route. It should be described separately from the pressure-driven internal-nozzle workflow, which requires pressure forcing, internal-wall development, and exit-profile evidence. The imposed-inlet result can support communication of rectangular-jet morphology, not internal-nozzle validation.

### Evidence Needed For A Stronger Claim

- Pressure-driven nozzle source and boundary-condition audit.
- Exit-profile measurements showing natural development rather than imposed uniform velocity.
- No-slip/internal-wall checks.
- Matched downstream geometry metrics from raw fields.
- Resolution and duration sensitivity checks preserving the same forcing.

## Sample 4: Convergence Claim From Misaligned Station/Time Data

### Prompt

An AI answer says: "L7 and L8 station-wise jet metrics converge because both runs produce similar Ahat curves," but the frames and station definitions are not aligned.

### Verdict

Warn or fail depending on severity. Similar curves are not enough when time cadence, station placement, or active-front definitions differ.

### Key Issues

- Station-wise convergence requires matched physical times or justified interpolation.
- Fixed stations and front-relative stations must use the same definitions, half-widths, thresholds, and normalization.
- L7/L8 comparisons are invalid if one level samples near-front stations while the other samples fixed downstream stations.
- A failed conservative gate may indicate true resolution sensitivity, but schedule mismatch must be excluded first.

### Rubric Scores

| Dimension | Score | Rationale |
|---|---:|---|
| Physics correctness | 3 | The intended metric is meaningful. |
| Boundary and initial conditions | 4 | Boundary setup may be unchanged. |
| Nondimensional and scaling logic | 3 | Ahat normalization may be valid, but station coordinates need alignment. |
| Numerical method and resolution evidence | 2 | Grid comparison lacks matched sampling. |
| Visualization/data support | 3 | Curves may be useful qualitatively, not as convergence proof. |
| Scope and overclaim control | 2 | Convergence is overstated. |
| Actionability | 5 | Re-extract with shared times/stations before rerunning. |

### Safe Corrected Wording

> The L7 and L8 curves are overlay-ready for qualitative comparison, but the convergence claim is not established until station definitions, liquid thresholds, and physical times are aligned. A no-solver re-extraction should be attempted first; if common coverage is insufficient, run only the missing aligned export rather than broadening the physics matrix.

### Evidence Needed For A Stronger Claim

- Shared fixed xi and front-relative station definitions.
- Matched physical times or documented interpolation.
- Same liquid threshold and station half-width.
- Median and p90 relative differences for Ahat, width, thickness, aspect ratio, centroid, warp, and interface proxy.
- Unchanged morphology classification.

## Sample 5: 2D Or Single-Phase Visualization Is Not 3D Spray Validation

### Prompt

An AI answer says: "A 2D single-phase impinging-jet visualization validates the 3D liquid-gas spray workflow."

### Verdict

Fail. A lower-dimensional or single-phase visualization can demonstrate post-processing, not validate a 3D multiphase spray workflow.

### Key Issues

- Dimensionality, phase model, turbulence/interface physics, and boundary conditions differ.
- A visualization pipeline can be technically useful while still not validating the physics target.
- Public-facing wording must separate solver demonstration, visualization, benchmark reproduction, and experimental validation.
- A credible 3D liquid-gas claim requires matching physics, grid/time studies, and appropriate diagnostics.

### Rubric Scores

| Dimension | Score | Rationale |
|---|---:|---|
| Physics correctness | 1 | Equates physically different problems. |
| Boundary and initial conditions | 2 | Does not account for different cases. |
| Nondimensional and scaling logic | 2 | Scaling similarity is not established. |
| Numerical method and resolution evidence | 2 | No 3D multiphase convergence evidence. |
| Visualization/data support | 2 | Visualization support is real but scoped too broadly. |
| Scope and overclaim control | 1 | Validation and spray claims are unsupported. |
| Actionability | 4 | Can be reframed as a visualization/post-processing demonstration. |

### Safe Corrected Wording

> The 2D single-phase example demonstrates a visualization and post-processing workflow. It does not validate a 3D liquid-gas spray model or atomisation prediction. A stronger claim would require a dedicated 3D multiphase case with documented boundary conditions, nondimensional scales, resolution checks, and comparison targets.

### Evidence Needed For A Stronger Claim

- 3D two-phase governing setup and boundary-condition documentation.
- Time-step, mesh, and interface-capturing diagnostics.
- Case-specific nondimensional numbers.
- Experimental or benchmark comparison if validation is claimed.
- Public copy that distinguishes demonstration from validation.

## Summary Evaluation Pattern

A strong CFD evaluator answer should:

1. Identify the claim and classify it as supported, caveated, or unsupported.
2. Check whether the solver outputs actually contain the required fields.
3. Separate boundary-condition evidence from visual similarity.
4. Require matched times, stations, and thresholds for convergence claims.
5. Replace overclaims with safe wording and concrete next evidence.
