# Review Artifacts

This directory contains compact private/internal review packets for Layer-1
scientific review. These packets are not public showcase assets.

## Directory Convention

Use:

`review_artifacts/<domain>/<case>/<YYYYMMDD_label>/`

Example:

`review_artifacts/basilisk/internal_nozzle/20260622_convergence_visual_review/`

## Required Packet Files

Every packet should include:

- `README_LAYER1_REVIEW.md`
- `ARTIFACT_MANIFEST.json`
- `metadata/`
- `contact_sheets/`
- `stills/`
- `videos_proxy/`
- `metrics/`
- `evidence/`

The README must tell Layer 1 what to inspect first, what result is claimed, what
is not claimed, and what decision is needed next. The manifest must include
source local paths, repo-relative paths, sizes, SHA256 hashes, media metadata
when applicable, proxy/original status, and claim boundaries.

## Size Limits

Default limits:

- MP4 proxy: target `<= 8 MB`
- Hard MP4 limit: `<= 15 MB`
- CSV: `<= 5 MB`
- Individual review image: keep small enough for GitHub review; prefer `<= 2 MB`
- Do not commit full frame folders or raw simulation folders

If an original artifact exceeds the limits, create a proxy or a sampled summary.
Leave the original under `/home/franco/stack-validation`.

## Proxy Rules

For every MP4/proxy:

- include ffprobe JSON under `metadata/`;
- include a contact sheet under `contact_sheets/`;
- include first, middle, and last stills under `stills/`;
- record SHA256 and file size in `ARTIFACT_MANIFEST.json`;
- label whether it is diagnostic, failed/limited, or
  portfolio-candidate-requires-human-review.

## Prohibited Files

Do not commit:

- `.blend` files
- checkpoint or dump files
- VTK, VTP, VTU, or BI4 files
- full frame folders, PPM folders, native frame folders, or raw render folders
- facet/surface folders
- raw solver logs and broad stdout/stderr logs
- large raw CSVs or raw cell exports
- complete stack-validation task directories

## Public/Private Warning

Review packets are private/internal working evidence. They must not be treated
as public media or final scientific claims. Keep:

- `fit_ready=false`
- `public_ready=false`

Do not claim validation, production CFD, stationary spray, experimental
agreement, true atomisation, pressure-atomized-nozzle validation, final
predictive modeling, or public readiness from these packets.
