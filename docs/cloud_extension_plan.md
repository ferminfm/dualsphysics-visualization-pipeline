# Cloud Extension Plan

This is a future-work plan for turning the local DualSPHysics visualization
workflow into a cloud-backed teaching and reporting pipeline. It is not an
implemented cloud deployment, and it does not call Google Cloud, Gemini, Vertex
AI, or any external API from this repository.

## Current Local Workflow

```text
DualSPHysics GPU run
  -> VTK / IsoSurface post-processing
  -> headless Blender render
  -> ffmpeg assembly
  -> hosted video link
  -> Markdown reports and caveats
```

The current repo demonstrates local, reproducible scientific visualization and
post-processing. Heavy artifacts remain outside Git.

## Future Cloud Storage Layer

Use Cloud Storage as the artifact boundary for generated files:

- solver logs,
- VTK/VTP/BI4-derived exports,
- rendered frame archives,
- MP4 outputs,
- contact sheets,
- manifests and checksums.

Expected behavior:

- Git stores scripts, docs, and small metadata.
- Cloud Storage stores bulky generated artifacts.
- Object names include date, case name, run ID, and media type.

## Future Batch/Post-Processing Layer

Use Cloud Run Jobs or Batch for bounded post-processing jobs:

- convert solver outputs into render-ready VTK or surface data,
- run headless Blender in a container,
- assemble MP4/contact sheets with `ffmpeg`,
- write reports and manifests.

This should be post-processing first. Solver execution should only move to cloud
after licensing, runtime, GPU requirements, and artifact sizes are reviewed.

## Future Container Layer

Use Artifact Registry for versioned containers:

- Blender + Python render container,
- ffmpeg assembly container,
- report-generation container,
- optional solver/postprocessor container if licensing and redistribution allow.

Container images should record tool versions so a public tutorial can explain
what changed between runs.

## Future Gemini / Vertex AI Layer

Use Vertex AI or Gemini only as an explanation and QA assistant over existing
logs, reports, and manifests:

- summarize solver and render logs,
- generate a tutorial checklist from a completed run,
- draft public-safe captions,
- flag risky wording such as validation or experimental agreement claims,
- answer questions about the pipeline steps from curated documentation.

Do not send private data, credentials, unpublished datasets, or large raw
simulation output by default. Gemini/Vertex integration is roadmap-only in this
repo.

## Future Static Documentation Site

Use a static site or Vercel/GitHub Pages page for human-facing documentation:

- hosted video links,
- command walkthroughs,
- troubleshooting notes,
- public-safe caveats,
- small thumbnails or contact sheets,
- links back to source docs.

The site should embed hosted video URLs rather than committing MP4 files.

## Non-Claims

This cloud plan does not claim:

- deployed Google Cloud implementation,
- Gemini-powered production system,
- Vertex AI deployment,
- production CFD validation,
- atomization validation,
- experimental agreement.

It is a future architecture plan for reproducible scientific-computing
communication.
