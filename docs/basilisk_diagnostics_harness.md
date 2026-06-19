# Basilisk Diagnostics Harness

## Purpose

The Basilisk diagnostics harness consolidates existing VOF route summaries and
metrics into consistent case tables, route comparisons, and conservative
morphology labels. It is a post-processing layer only: it does not rerun
simulations, create public-quality videos, or promote preliminary evidence into
validation claims.

The current consolidated output root is:

```text
/home/franco/stack-validation/20260618-basilisk-diagnostics-harness
```

Generated reports and tables are kept outside Git:

```text
preflight.md
input_inventory.md
input_inventory.json
diagnostics_schema.md
consolidated_basilisk_case_table.csv
consolidated_basilisk_case_table.json
basilisk_route_comparison.md
basilisk_route_comparison.json
classification_audit.md
diagnostics_harness_usage.md
```

## Reusable Scripts

The reusable entry points are:

```text
scripts/basilisk_collect_diagnostics.py
scripts/basilisk_classify_morphology.py
scripts/basilisk_compare_routes.py
```

Typical command:

```bash
python3 scripts/basilisk_collect_diagnostics.py \
  --output-root /home/franco/stack-validation/20260618-basilisk-diagnostics-harness \
  /home/franco/stack-validation/20260618-basilisk-2d-shear-sigma-scout \
  /home/franco/stack-validation/20260618-basilisk-rectangular-slot-gas-weber-scan \
  /home/franco/stack-validation/20260618-basilisk-rect-slot-morphology-escalation \
  /home/franco/stack-validation/20260618-basilisk-3d-micro-translation-we80 \
  /home/franco/stack-validation/20260618-basilisk-3d-adaptive-refinement-map \
  /home/franco/stack-validation/20260618-basilisk-official-atomisation-wrapper \
  /home/franco/stack-validation/20260618-basilisk-atomisation-route
```

The scripts use the Python standard library and read existing summary JSON and
metrics CSV/JSON files. They avoid raw frame/video parsing.

## Classification Policy

Connected waviness is not atomization. A 2D scout candidate is treated as
reduced-model parameter evidence only, not 3D validation. A 3D breakup-proxy
label requires credible post-exit components or detached-volume proxies, not
raw one-cell debris or pre-exit component counts.

The harness keeps these evidence classes separate:

| Evidence class | Interpretation |
| --- | --- |
| Positive 2D scout | Useful reduced-model signal for parameter selection only. |
| Negative 3D rectangular-slot map | Tested settings stayed connected or runtime-limited. |
| Internal official-wrapper evidence | Demonstrates native VOF/tag workflow, not public-ready validation. |
| Missing optional route | Marked missing without failing the whole comparison. |

None of the Basilisk route tables should be described as physical validation,
production CFD, stationary spray evidence, experimental agreement, or final
atomisation prediction.

## Current High-Level Result

The consolidated audit reproduces the expected route distinctions:

- `basilisk_2d_shear_sigma_scout`: positive reduced-model scout candidate.
- `basilisk_rectangular_slot_gas_weber_scan`: negative 3D morphology result.
- `basilisk_rectangular_slot_morphology_escalation`: negative 3D morphology result.
- `basilisk_3d_micro_translation_we80`: negative 3D transfer result.
- `basilisk_3d_adaptive_refinement_map`: negative 3D map with raw debris rejected
  by the credible-component gate.
- `basilisk_official_atomisation_wrapper`: internal/preliminary only.
- `basilisk_atomisation_route`: internal/preliminary proof route.

The next technical step is not video polish. Use the consolidated comparison to
choose a materially different physics or refinement branch before spending more
3D runtime.
