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

## Shared Caveat

Use one of these caveats near any public embed:

```text
Visualization and post-processing demonstration; not physical validation.
```

```text
GPU SPH to Blender workflow demonstration; not production CFD validation.
```

Avoid wording that implies:

- physical validation,
- production CFD validation,
- atomization validation,
- statistically stationary spray validation,
- experimental agreement,
- deployed cloud implementation.
