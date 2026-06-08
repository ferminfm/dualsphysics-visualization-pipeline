# Next Solver Route Decision for Jet Geometry Data - 2026-06-09

## Purpose

This memo decides the next practical route for generating statistically
stationary fully atomized or spray-like jet geometry data after the
DualSPHysics 3D inlet/open-boundary path remained blocked by missing example
XML cases.

No solver was run for this memo. No package was downloaded. No raw BI4, VTK,
frame, or video output was generated.

## Current DualSPHysics Status

Status: **blocked now; viable only after official examples are recovered.**

Evidence from the previous recovery pass:

- The CUDA 12.8 wrapper is available:
  `/home/franco/bin/dualsphysics5.4-cuda128`.
- The active solver reports `DualSPHysics5 v5.4.355 (08-04-2025)`.
- The active local examples tree contains only `examples/main/01_DamBreak/`.
- The local PDFs mention inlet/open-boundary examples including
  `05_SHAPESINLET3D`, `06_BOX4INLET3D`, and `8_IMPINGINGJET`.
- Those XML case directories are absent locally.
- The local `examples/README.txt` says the GitHub checkout intentionally omits
  most examples and that the full examples are in the full DualSPHysics package.
- No active `bin/linux` multiphase/liquid-gas executable was found.

Implication:

- DualSPHysics remains useful for an SPH-generated jet/spray-geometry proxy once
  the official inlet examples are recovered.
- It should not be used today to fabricate a stationary 3D jet XML from
  templates.
- It should not be presented as fully atomized multiphase pressure-atomization
  validation.

## Route Ranking

| Rank | Route | Current feasibility | Expected evidence value | Time to first data | Overclaiming risk | SprayGeo / Ideal Explorer compatibility |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Basilisk atomization/VOF route | High for a next local solver step. SprayGeo already has a tiny Basilisk VOF adapter proof with `qcc` available, compiled case, successful run, 250 raw rows, and 26 proxy sections. | Best next solver evidence for interface/spray-like geometry because VOF can represent liquid-gas interfaces and breakup-like contours. Still not validation without resolution/threshold studies. | Short for a tiny atomization-derived CSV; medium for a credible post-transient study. | Medium. Must label early runs as VOF/interface geometry tests, not validated atomization. | Strong. Existing `adapters_basilisk.py`, tiny CSV fixture, metrics path, benchmark source comparison, and no-API explanation pipeline already exist. |
| 2 | Recover official DualSPHysics inlet examples | Medium after manual recovery of the full package or verified example subset; blocked without that recovery. | Good for SPH particle geometry and continuity with the visualization repo. Weak for fully atomized physics unless a proper multiphase/liquid-gas path is later validated. | Short after examples are recovered; blocked now. | Medium-high. Easy to overstate a single-phase/free-surface SPH inlet as atomization. | Strong after particle frames are exported: SprayGeo can ingest metrics, and Ideal Explorer already accepts area overlays. |
| 3 | OpenFOAM interFoam/VOF route | Medium. OpenFOAM v2406 and a tiny `interFoam` adapter proof already ran, but the current fixture is a dam-break line-sampling proxy. | Good for VOF field ingestion and future applied spray/VOF setup. Less direct than Basilisk for a tiny atomization-style mechanism study unless a suitable spray/jet case is built. | Short for another VOF proxy; medium-long for a non-dam-break jet case. | Medium. Stock tutorials are not spray validation, and sparse 2D samples are only proxy geometry. | Strong. Existing `adapters_openfoam.py`, curated sample, metrics path, and source-comparison output exist. |
| 4 | Literature / WJTSJ data-first route | Medium for documentation and manual digitization; blocked for fit-grade data because final calibrated WPD CSVs are missing. | Highest eventual physical relevance if calibrated literature/experimental curves are completed, but it is not solver-generated data. | Short after manual WPD exports; blocked today for final CSVs. | High if LOW preliminary data are used as fit-grade evidence. | Good for Ideal Explorer overlays and model comparisons; weaker for SprayGeo contour extraction unless image/contour data are digitized, not only width curves. |

## Recommended Next Route

Recommended route: **Basilisk atomization/VOF route.**

Reasoning:

1. DualSPHysics is blocked until official inlet XML examples are recovered.
2. SprayGeo already has a working Basilisk adapter proof with successful compile,
   run, curated CSV, and geometry metrics.
3. VOF interface data are a better near-term match to atomization-like geometry
   than a missing SPH inlet case or an OpenFOAM dam-break fixture.
4. The next Basilisk step can stay small: export time-indexed VOF/interface data,
   discard early frames, compute per-frame geometry metrics, and report whether a
   post-transient window is even plausible.

Immediate Basilisk next task:

- Start from the existing tiny Basilisk adapter workflow.
- Replace the toy proxy with a documented, bounded atomization/jet VOF case only
  if it is already available locally or can be derived without external
  installation.
- Export small CSV/interface samples outside Git.
- Commit only tiny curated metrics and a report.
- Label the output as a VOF interface geometry workflow, not validated
  atomization.

Expected first SprayGeo handoff fields:

```text
source_id, source_type, time, frame, post_transient, stationarity_window_id,
z, x, y, threshold, contour_id, metadata
```

Expected first reduced metrics:

```text
z, time, frame, particle_or_cell_count, area_proxy, centroid_x, centroid_y,
major_extent, minor_extent, aspect_ratio, orientation, quality_flags
```

## Fallback Route

Fallback route: **recover official DualSPHysics inlet examples manually, then run
`05_SHAPESINLET3D` as the first SPH smoke case.**

Reasoning:

- It preserves the SPH/video portfolio path.
- `05_SHAPESINLET3D` directly tests 3D inlet shapes and non-circular inlet
  geometry.
- It is safer than reconstructing an XML case from templates.

Fallback stop condition:

- If the recovered example is only a visualization or inlet-buffer exercise and
  cannot produce interpretable downstream jet/spray-like particle geometry, do
  not force it into the SprayGeo/Ideal Explorer bridge.

## Route Details

### Basilisk Atomization/VOF

Feasibility on this machine:

- Already demonstrated at tiny scale through SprayGeo's Basilisk adapter proof.
- Existing result: compiled and ran a tiny VOF CSV export, producing 250 raw
  rows, 250 curated rows, and 26 proxy sections.
- No install is needed if the previously validated local Basilisk path remains
  available.

Evidence value:

- Strongest next route for liquid-gas interface geometry and breakup-like
  contours.
- Still requires resolution, threshold, and time-window sensitivity before any
  physical interpretation.

Time-to-first-data:

- Short for a tiny CSV/interface proof.
- Medium for a credible post-transient average.

Overclaiming risk:

- Medium. Early runs should be described as VOF interface geometry data, not
  validated atomization, not experimental agreement, and not production CFD.

Compatibility:

- Strong with SprayGeo because `adapters_basilisk.py` already exists.
- Strong with Ideal Explorer after SprayGeo exports `zeta,Ahat,Ahat_error`.

### DualSPHysics Official Inlet Examples

Feasibility on this machine:

- Solver and wrapper are validated.
- Example XMLs are missing locally.
- Manual full-package recovery is required.

Evidence value:

- Good for SPH-generated particle geometry and the visualization portfolio.
- Limited for fully atomized physics unless a multiphase/liquid-gas solver path
  is separately validated.

Time-to-first-data:

- Blocked now.
- Short after official examples are recovered and inspected.

Overclaiming risk:

- Medium-high. A 3D inlet SPH case can be a useful geometry proxy but not a
  fully atomized validation case.

Compatibility:

- Strong after VTK/particle metrics are extracted.
- Existing SprayGeo-to-Ideal Explorer bridge is ready for sample-labeled
  averaged area overlays.

### OpenFOAM interFoam/VOF

Feasibility on this machine:

- OpenFOAM v2406 is available.
- SprayGeo's tiny OpenFOAM adapter proof already ran a shortened serial
  `interFoam` dam-break tutorial, sampled lines, and produced 4 proxy sections.

Evidence value:

- Good for VOF ingestion architecture.
- Moderate for the jet/spray target until a real jet or VOF/LPT spray case is
  configured.

Time-to-first-data:

- Short for another proxy.
- Medium-long for a documented non-dam-break jet case.

Overclaiming risk:

- Medium. Dam-break and sparse line samples must remain labeled as proxy data.

Compatibility:

- Strong with SprayGeo because `adapters_openfoam.py` already exists.
- Good with Ideal Explorer if the output is reduced to area history and
  uncertainty.

### Literature / WJTSJ Data-First

Feasibility on this machine:

- Fit-stage tooling and figures exist.
- Required project Python venv is documented.
- Final calibrated WPD CSVs are currently missing.
- LOW preliminary data are quarantined and must not be used as fit-grade data.

Evidence value:

- Highest eventual physical relevance after calibrated digitization.
- Not solver-generated data and not a stationarity simulation route.

Time-to-first-data:

- Blocked until manual WebPlotDigitizer exports are produced.
- Short after final CSVs exist and manifest rows are enabled.

Overclaiming risk:

- High if preliminary data are used or if digitized width/pressure curves are
  presented as independent validation without uncertainty.

Compatibility:

- Good with Ideal Explorer for overlays and model comparison.
- Partial with SprayGeo unless the data include contours/images rather than only
  width or decay curves.

## Decision

Use **Basilisk atomization/VOF** as the next solver route.

Use **official DualSPHysics inlet-example recovery** as the fallback if the
priority is SPH-specific particle visualization and continuity with the existing
DualSPHysics portfolio.

Keep **OpenFOAM VOF** as the applied-CFD backup once a non-dam-break jet case is
identified.

Keep **WJTSJ/literature data** as an evidence/comparison track, not as the next
solver route, until calibrated final CSVs exist.

## Guardrails For The Next Execution Prompt

- Do not use dam-break output as a jet/spray substitute.
- Do not call tiny 2D proxy adapter data physical validation.
- Do not claim statistically stationary behavior until a post-transient window
  is defined and tested.
- Do not claim fully atomized physics without appropriate solver, interface or
  droplet evidence, and resolution/threshold sensitivity.
- Keep raw solver outputs outside Git.
- Commit only scripts, docs, tiny fixtures, metrics summaries, and small plots.
