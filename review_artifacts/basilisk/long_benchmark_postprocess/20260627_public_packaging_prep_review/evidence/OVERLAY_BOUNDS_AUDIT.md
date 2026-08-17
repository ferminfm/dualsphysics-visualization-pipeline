# Overlay Bounds Audit

Input packet: `review_artifacts/basilisk/long_benchmark_postprocess/20260626_postprocess_review/`

Assets inspected:

- `contact_sheets/long_primary_route_blender_sequence_v31_contact_sheet.jpg`
- `contact_sheets/round_vs_rectangular_split_screen_v31_contact_sheet.jpg`
- `contact_sheets/task05_field_visualization_reel_v31_no_pressure_contact_sheet.jpg`
- `contact_sheets/final_complex_geometry_flythrough_v3_contact_sheet.jpg`
- first/middle/last stills for the V3.1 proxy videos where available.

## Findings

| Asset | Bounds | Readability | Fluid overlap | Packaging decision |
| --- | --- | --- | --- | --- |
| V3.1 primary circular sequence | Overlay stays inside the black box and within frame. | Text is small for external/public use. | Low; top-left panel does not materially cover the fluid region. | Accept for internal review; not final public text. |
| V3.1 split-screen comparison | Top labels, panel labels, and bottom caveat stay within frame. | Main labels are readable; inherited in-scene black panels are small. | Low; caveat is outside fluid panels. | Accept for internal review; keep as supporting comparison. |
| V3.1 no-pressure field reel | Field labels and method note stay within frame. | Readable enough for diagnostic review. | N/A, plot panels. | Accept for internal technical diagnostic. |
| Retained v3 flythrough | Overlay stays within frame. | Readable as internal review text; still uses explicit internal/public-ready-false wording. | Low-to-moderate depending on camera view; not a public caption style. | Useful inspection clip; not final public packaging without human review. |

## Result

`overlay_bounds_passed=true` for internal review. No urgent overlay-fix proxy was generated.

Public packaging still needs a separate caption/overlay pass because existing overlays are intentionally internal and some text is too small or too process-oriented for a modest public technical sample.
