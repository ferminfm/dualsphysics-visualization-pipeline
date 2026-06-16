# Video Metadata

This file consolidates public-safe metadata for the hosted DualSPHysics videos.
It records links and captions only; MP4 files remain outside Git.

## 3D Inlet-Flow Scientific Demonstration

- YouTube URL: <https://youtu.be/eMUbVgLRkHY>
- Suggested embed URL: `https://www.youtube-nocookie.com/embed/eMUbVgLRkHY`
- Title: `3D Inlet-Flow Scientific Demonstration`
- Short description: Official DualSPHysics v5.4 inlet example rendered through
  a reproducible GPU SPH -> VTK/IsoSurface -> headless Blender -> ffmpeg
  workflow.
- Caption: Visualization and post-processing demonstration; not physical
  validation.
- Recommended use: primary scientific-computing demonstration for the
  simulation-to-visualization pipeline.

Long description:

```text
Official DualSPHysics v5.4 05_ShapesInlet3D example processed through a local
GPU SPH -> VTK/IsoSurface -> headless Blender -> ffmpeg workflow. The video
combines raw SPH particle provenance, reconstructed free-surface visualization,
and velocity-magnitude post-analysis.

This is a visualization and post-processing demonstration, not physical
validation, production CFD validation, atomization validation, or experimental
agreement.
```

## DualSPHysics Dam-Break Visualization

- YouTube URL: <https://youtu.be/EDUGMpGn5MI>
- Suggested embed URL: `https://www.youtube-nocookie.com/embed/EDUGMpGn5MI`
- Title: `DualSPHysics Dam-Break Visualization`
- Short description: GPU SPH to Blender workflow demonstration using a small
  dam-break case, VTK export, headless Blender rendering, and ffmpeg assembly.
- Caption: GPU SPH to Blender workflow demonstration; not production CFD
  validation.
- Recommended use: supporting demonstration of the direct Blender VTK fallback
  and deterministic MP4 assembly path.

Thumbnail-link Markdown:

```markdown
[![Front-view dam-break video thumbnail](assets/dambreak_frontview_video_thumbnail.png)](https://youtu.be/EDUGMpGn5MI)
```

Long description:

```text
Small dam-break visualization-pipeline demo generated from a local DualSPHysics
CUDA run, converted to VTK, rendered through headless Blender, and assembled as
MP4. Frame 0200 was excluded after visual QA; the prepared sequence uses frames
0000-0150.

This is a workflow demonstration, not production CFD validation.
```

## Official DualSPHysics 2D Impinging-Jet Visualization Demo

- YouTube URL: <https://youtu.be/5JkdLRPYWUI>
- Suggested embed URL: `https://www.youtube-nocookie.com/embed/5JkdLRPYWUI`
- Title: `Official DualSPHysics 2D Impinging-Jet Visualization Demo`
- Short description: Official DualSPHysics v5.4 `08_ImpingingJet` example
  rendered as a front-on reconstructed-surface, particle, impact-zoom, and
  scalar-analysis showcase.
- Caption: Visualization demo only: 2D single-phase, not validation.
- Recommended use: supporting scalar-analysis demonstration for the
  SPH-to-Blender post-processing family.

Long description:

```text
Official DualSPHysics v5.4 08_ImpingingJet / CaseJet2D example processed
through IsoSurface, particle VTK, headless Blender, and ffmpeg. The video shows
front-on reconstructed-surface and scalar-analysis views.

This is a 2D single-phase visualization demo. It is not a 3D atomized jet, not
liquid-gas spray breakup, not statistically stationary spray validation, not
production CFD, and not experimental agreement.
```

## Rectangular Jet Geometry Proxy

- YouTube URL: not uploaded yet; use manual hosting or upload before embedding.
- Suggested title: `Rectangular Jet Geometry Proxy | DualSPHysics + Surface Reconstruction`
- Local accepted root:
  `/home/franco/stack-validation/20260612-dualsphysics-rectangular-jet-v41-accepted-v1`
- Accepted classification: `accepted_public_preview_candidate`
- Short description: Render-polished DualSPHysics rectangular inlet jet geometry
  proxy using GPU SPH data, PartVTK/IsoSurface post-processing,
  transparent-water Blender rendering, and ffmpeg assembly.
- Caption: Single-phase geometry-proxy demonstration; not atomization
  validation.
- Recommended use: public-preview demonstration of a reproducible scientific
  visualization and post-processing workflow. Host the MP4 externally before
  embedding it on a website; do not commit video media to Git.

Long description:

```text
This video presents a modified single-phase DualSPHysics rectangular inlet jet
geometry proxy. The workflow starts from accepted v4 simulation data and applies
a v4.1 render-only polish pass: particle provenance, reconstructed IsoSurface
views with clearer transparent-water material, velocity and pressure
post-processing views, proxy-energy/cross-section diagnostics, and true
surface-cut panels.

Pipeline: DualSPHysics v5.4 GPU data -> PartVTK/IsoSurface outputs ->
headless Blender render pass -> ffmpeg assembly.

This is a scientific-computing workflow demonstration. It is not fully atomized
spray, not physical validation, not production CFD, and not experimental
agreement.
```

## Shared Caveat

Use one of these caveats near any public embed:

```text
Visualization and post-processing demonstration; not physical validation.
```

```text
GPU SPH to Blender workflow demonstration; not production CFD validation.
```

```text
Single-phase geometry-proxy demonstration; not atomization validation.
```

Avoid wording that implies:

- physical validation,
- production CFD validation,
- atomization validation,
- statistically stationary spray validation,
- experimental agreement,
- deployed cloud implementation.

For the recommended page structure and demo hierarchy, see
[dualsphysics_demo_family.md](dualsphysics_demo_family.md).
