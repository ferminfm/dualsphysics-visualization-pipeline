# Boundary Clearance Audit

Generated: 2026-06-26T05:18:08.799702+00:00

This is a no-solver audit of the existing Basilisk `output_facets(f)` surfaces for the long official circular control and the long 2:1 rectangular top-hat imposed-inlet comparison. It does not modify source physics or solver outputs.

## Domain and Resolution Assumptions

- Domain from `cases/basilisk/official_rectangular_pulsed_atomisation.c`: `origin(0, -1.5, -1.5)` and `size(3)`, so x in `[0, 3]`, y/z in `[-1.5, 1.5]`.
- maxlevel: `8`.
- Finest local Delta estimate: `0.01171875`.
- Boundary proximity thresholds: 2 Delta = `0.0234375`, 4 Delta = `0.046875`, and 0.05 domain length = `0.15`.
- The inlet plane at x=0 is excluded from downstream/lateral contact classification because the initialized/injected liquid intentionally remains attached there.

## Result

| Route | Surface frames | Boundary contact detected | Clean until t | Min downstream clearance | Min lateral clearance | Selected safe hero frame/time |
|---|---:|---:|---:|---:|---:|---|
| `official_round_control` | 101 | false | 2.000 | 1.292730 | 0.965188 | 98 / t=1.960 |
| `rectangular_top_hat` | 101 | false | 2.000 | 1.330840 | 0.935551 | 99 / t=1.980 |


## Hero Frame Gate

A hero frame is eligible only when:

- no meaningful downstream or lateral boundary contact is detected;
- topology diagnostics are present;
- the interface/component complexity is high;
- the facet output is nonzero and parseable.

The selected primary hero is official circular frame `98` at t=`1.960`. It was selected by maximum complexity score among eligible frames, not merely by choosing the last frame. The rectangular comparison remains `C1_rect_area_top_hat` / `rect_area_top_hat`, with a separate safe hero frame recorded in the JSON summary.

## Scientific Boundary

- No CFD solver was run.
- The rectangular long route is a 2:1 area-matched rectangular top-hat imposed-inlet comparison.
- Poiseuille-series profiles were implemented and tested but were not selected by the bounded candidate gate.
- These outputs remain internal review artifacts: `fit_ready=false`, `public_ready=false`.

Detailed per-frame data: `metrics/boundary_clearance_by_frame.csv`.
Summary JSON: `metrics/boundary_clearance_summary.json`.
