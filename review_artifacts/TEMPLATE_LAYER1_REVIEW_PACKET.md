# Layer-1 Review Packet Template

Use this checklist when creating a new packet under:

`review_artifacts/<domain>/<case>/<YYYYMMDD_label>/`

## Packet Identity

- [ ] Domain:
- [ ] Case:
- [ ] Date/label:
- [ ] Source local stack-validation root:
- [ ] Review branch:
- [ ] PR URL:
- [ ] `fit_ready=false`
- [ ] `public_ready=false`

## Required Files

- [ ] `README_LAYER1_REVIEW.md`
- [ ] `ARTIFACT_MANIFEST.json`
- [ ] `metadata/`
- [ ] `contact_sheets/`
- [ ] `stills/`
- [ ] `videos_proxy/`
- [ ] `metrics/`
- [ ] `evidence/`

## Media Proxy Checklist

For every MP4 proxy:

- [ ] file size is `<= 15 MB`
- [ ] ffprobe JSON exists
- [ ] contact sheet exists
- [ ] first still exists
- [ ] middle still exists
- [ ] last still exists
- [ ] SHA256 is recorded
- [ ] source local path is recorded
- [ ] claim boundary is recorded

## Metrics And Evidence Checklist

- [ ] compact metrics copied or sampled
- [ ] CSV files are `<= 5 MB`
- [ ] large raw metrics remain local only
- [ ] decision reports are copied or summarized
- [ ] local full-output paths are named when useful
- [ ] Layer-1 next decision is explicit

## Forbidden Artifact Scan

Confirm no staged files include:

- [ ] `.blend`
- [ ] checkpoint or dump files
- [ ] VTK, VTP, VTU, or BI4 files
- [ ] full frame folders or PPM folders
- [ ] facet/surface folders
- [ ] raw solver logs
- [ ] large CSVs or raw cell exports
- [ ] complete stack-validation task directories

## Claim Boundary

Confirm the packet does not claim:

- [ ] validation
- [ ] production CFD
- [ ] stationary spray
- [ ] experimental agreement
- [ ] true atomisation
- [ ] pressure-atomized-nozzle validation
- [ ] final predictive modeling
- [ ] fit readiness
- [ ] public readiness

## QA

- [ ] JSON files parse
- [ ] ffprobe passes for committed MP4 proxies
- [ ] `git diff --check` passes
- [ ] status Markdown/JSON points to the packet
- [ ] only the review branch is pushed
