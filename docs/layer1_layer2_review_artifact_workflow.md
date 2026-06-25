# Layer-1/Layer-2 Review Artifact Workflow

This repository is the working evidence repository for the scientific
visualization stack. It can contain unfinished internal review artifacts when
they are small, bounded, explicitly caveated, and useful for Layer-1 review.
It is not the final public showcase repository.

## Repository Roles

The runbook repository defines what agents should do. It stores prompts,
contracts, schemas, and task instructions. It should not store generated solver
evidence or media.

This working evidence repository stores reusable source, scripts, documentation,
and compact review packets that Layer 1 can inspect through GitHub. Review
packets are allowed here only when they are deliberately small and clearly
marked as private/internal.

Local `/home/franco/stack-validation` roots store full execution evidence:
raw fields, checkpoint dumps, native frame folders, solver logs, large CSVs,
surface/facet folders, Blender work products, and full reports. These outputs
are authoritative for detailed audit but are not committed wholesale.

The public site repository stores final, human-approved public showcase assets
and copy. Internal Basilisk evidence must not be moved there by Layer-2 agents.
Promotion to the site requires a separate human-reviewed publication task.

## What Belongs In `review_artifacts/`

`review_artifacts/` is for compact Layer-1 review packets, using:

`review_artifacts/<domain>/<case>/<YYYYMMDD_label>/`

Allowed packet contents include:

- `README_LAYER1_REVIEW.md`
- `ARTIFACT_MANIFEST.json`
- `metadata/` with ffprobe or schema metadata
- `contact_sheets/` with compact JPG review sheets
- `stills/` with first/middle/last review frames
- `videos_proxy/` with small MP4 proxies
- `metrics/` with compact CSV/JSON summaries
- `evidence/` with selected reports, decisions, manifests, and checklists

Each packet must explain why it exists, what Layer 1 should inspect first, what
is still blocked, and which claims are prohibited.

## What Must Stay Only In Stack Validation

Keep the following outside Git, under `/home/franco/stack-validation`:

- raw solver fields and full-domain dumps
- checkpoint or restart files
- VTK, VTP, VTU, BI4, PPM frame folders, and full native frame folders
- facet/surface folders and full geometry export folders
- Blender `.blend` files and large render work directories
- solver logs, stdout/stderr logs, and broad execution traces
- large CSVs or raw cell exports
- stack-validation task roots copied wholesale

If Layer 1 needs to know these exist, commit only a manifest or short report
that names the local path, size, SHA256 if useful, and reason it remains local.

## What May Later Be Promoted Publicly

Only final, human-approved public assets may move to the Vercel/site repository.
Promotion requires a separate public packaging task and must confirm:

- public copy is caveated and non-misleading
- media quality is sufficient for external viewing
- private run paths and internal route-finding details are removed
- no validation, production, or atomisation claims are implied
- `public_ready=true` is set only by the approved publication task

Review proxies in this repository are not public site assets.

## Claim Boundaries

Internal Basilisk packets must preserve these defaults:

- `fit_ready=false`
- `public_ready=false`
- no validation claim
- no production CFD claim
- no stationary spray claim
- no experimental agreement claim
- no true atomisation or final atomisation prediction claim
- no pressure-atomized-nozzle validation claim
- connected waviness is not breakup
- one-cell debris, pre-exit components, mirrored quadrants, and projection
  artifacts are not detached-liquid evidence

Quarter-symmetry evidence is scout/comparison evidence unless a full-domain
confirmation task explicitly upgrades it.

## Required Layer-2 Sync Step

Every Layer-2 batch that produces useful internal evidence must finish with a
bounded sync decision:

1. keep full outputs under `/home/franco/stack-validation`;
2. create or update a compact `review_artifacts/` packet only when Layer 1 needs
   GitHub-visible evidence;
3. include `README_LAYER1_REVIEW.md` and `ARTIFACT_MANIFEST.json`;
4. include ffprobe metadata and first/middle/last stills for every proxy MP4;
5. update the relevant status Markdown/JSON with the packet path;
6. run JSON validation, media size checks, forbidden-artifact scans, and
   `git diff --check`;
7. commit only source/docs/scripts and the bounded review packet;
8. push only the designated review branch.

Layer-2 must not push `main`, merge, deploy, publish, or mark public readiness.

## Required Layer-1 Inspection Step

Layer 1 should inspect the GitHub-visible packet before directing new work:

1. read the packet README and manifest;
2. inspect proxy videos, stills, contact sheets, and compact metrics;
3. compare the packet against the local stack-validation reports when needed;
4. verify claim boundaries stayed intact;
5. decide whether to request another simulation, a diagnostics pass, visual
   cleanup, documentation work, PR splitting, or human publication review.

Layer 1 should treat a packet as decision evidence, not as publication evidence.
