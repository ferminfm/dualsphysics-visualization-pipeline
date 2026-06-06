# DualSPHysics + VisualSPHysics Portfolio Pipeline

Lightweight portfolio scaffold for a reproducible GPU SPH visualization pipeline:
DualSPHysics produces free-surface/multiphase particle data, and VisualSPHysics
is the planned Blender visualization layer for stills and animations.

This repository intentionally does not vendor DualSPHysics, VisualSPHysics,
Blender, VTK, CUDA, or generated simulation outputs.

## Validated Machine Summary

- Host: `frontera`
- OS: Ubuntu 24.04
- CPU: Intel Core Ultra 9 275HX, 24 threads
- RAM: about 30 GiB usable
- GPU: NVIDIA GeForce RTX 5070 Laptop GPU, about 8 GB VRAM
- NVIDIA driver: `595.71.05`
- Active DualSPHysics CUDA toolkit: `/usr/local/cuda-12.8`
- DualSPHysics GPU executable: validated
- VisualSPHysics/Blender status: preflight blocked until Blender and VTK dev
  requirements are available

## DualSPHysics CUDA 12.8 Wrapper

Canonical local wrapper:

```bash
/home/franco/bin/dualsphysics5.4-cuda128
```

Known target executable:

```bash
/home/franco/opt/dualsphysics/DualSPHysics-cuda128-20260606-0340-retry2/bin/linux/DualSPHysics5.4_linux64
```

Safe usage pattern:

```bash
/home/franco/bin/dualsphysics5.4-cuda128 -gpu CASE_INPUT OUTPUT_DIR
```

## VisualSPHysics Role

VisualSPHysics is intended to import DualSPHysics outputs into Blender for
portfolio-grade visualization: water surfaces, particle effects, camera paths,
lighting, and short render clips. It is a visualization layer, not the solver.

Current local status:

- `blender` is not available in `PATH`.
- No VisualSPHysics add-on zip/source artifact is currently present locally.
- VTK development headers/pkg-config metadata were not visible in the latest
  preflight.
- Headless validation should use isolated Blender config directories and
  `blender --background`.

## Reproducible Pipeline

```text
DualSPHysics XML case
        |
        v
GenCase geometry/particle generation
        |
        v
DualSPHysics GPU run via CUDA 12.8 wrapper
        |
        v
Small VTK/output subset export
        |
        v
VisualSPHysics add-on in headless Blender
        |
        v
Portfolio stills / clips / reproducible report
```

## Portfolio Narrative

This project demonstrates a local GPU-backed SPH workflow for free-surface and
multiphase CFD visualization. The research angle is pressure-atomized turbulent
liquid jet work; the portfolio angle is a reproducible path from validated GPU
simulation to Blender-based visual communication.

The intended message is narrow and defensible:

- DualSPHysics validates local CUDA/SPH capability.
- VisualSPHysics/Blender provides presentation-quality visualization.
- Large outputs stay outside Git and are regenerated from documented commands.

## Scripts

- `scripts/run_smoke_case.sh`: run or document a small DualSPHysics smoke case
  through the CUDA 12.8 wrapper.
- `scripts/export_vtk_subset.sh`: copy a bounded number of small VTK files into
  a local output subset for visualization testing.
- `scripts/blender_headless_smoke.py`: minimal Blender Python smoke script for
  isolated add-on install/enable checks.

## Data Policy

Do not commit generated datasets above 20 MB. Large VTK/CSV/log/video/render
artifacts are ignored by `.gitignore` and should remain under
`~/stack-validation/...` or another documented external output directory.

## Current External Reports

Small summaries are kept in `reports/`. Full logs remain outside this repo:

- `/home/franco/stack-validation/20260606-1952-dualsphysics-benchmark-rerun/report.md`
- `/home/franco/stack-validation/20260606-2248-visualsphysics-preflight/report.md`
- `/home/franco/stack-validation/20260606-2252-visualsphysics-headless-smoke/report.md`

