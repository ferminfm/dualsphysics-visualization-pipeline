# Web Embed Notes

These notes prepare the accepted DualSPHysics `05_ShapesInlet3D` scientific
demonstration for later website embedding. They do not upload media and do not
put large MP4 files in Git.

## Accepted Local Artifact

- Artifact root:
  `/home/franco/stack-validation/20260611-dualsphysics-shapesinlet3d-accepted-v1`
- Primary video:
  `dualsphysics_shapesinlet3d_final_scientific_demo.mp4`
- Clean companion video:
  `dualsphysics_shapesinlet3d_final_clean.mp4`
- Contact sheet:
  `dualsphysics_shapesinlet3d_final_contact_sheet.png`
- Checksums:
  `SHA256SUMS.txt`

## Hosted Video URLs

- ShapesInlet3D scientific demonstration:
  `https://youtu.be/eMUbVgLRkHY`
- Dam-break visualization demo:
  `https://youtu.be/EDUGMpGn5MI`

## Recommended Title

```text
3D Inlet-Flow Scientific Demonstration
```

## Short Description

```text
Official DualSPHysics v5.4 inlet example rendered through a reproducible GPU SPH -> VTK/IsoSurface -> headless Blender -> ffmpeg workflow.
```

## Long Description

```text
This scientific-computing demonstration uses the official DualSPHysics v5.4
05_ShapesInlet3D example to show a reproducible simulation-to-visualization
workflow. The accepted video combines three views of the same solver-generated
case: raw SPH particle provenance, reconstructed free-surface visualization
from IsoSurface output, and a velocity-magnitude post-analysis view. Rendering
is performed through a headless Blender pipeline and assembled with ffmpeg.

This is a visualization and post-processing demonstration, not physical
validation. It does not claim fully atomized spray validation, statistically
stationary spray validation, production CFD, or experimental agreement.
```

## Contact Sheet Alt Text

```text
Contact sheet for a DualSPHysics 3D inlet-flow demonstration showing intro card, raw SPH particle view, reconstructed free-surface view, velocity-magnitude analysis view, and outro summary.
```

## Suggested Video Caption

```text
Visualization and post-processing demonstration; not physical validation.
```

## Video Hosting

```text
ShapesInlet3D video URL: https://youtu.be/eMUbVgLRkHY
Dam-break video URL: https://youtu.be/EDUGMpGn5MI
```

Do not commit MP4 files directly to this repository. Keep using hosted video
URLs or a separate media storage path, and commit only lightweight Markdown,
metadata, or intentionally small poster images.

## Dam-Break Video Metadata

Recommended title:

```text
DualSPHysics Dam-Break Visualization
```

Short description:

```text
GPU SPH to Blender workflow demonstration using a small dam-break case, VTK
export, headless Blender rendering, and ffmpeg assembly.
```

Suggested caption:

```text
GPU SPH to Blender workflow demonstration; not production CFD validation.
```

Thumbnail Markdown:

```markdown
[![Front-view dam-break video thumbnail](assets/dambreak_frontview_video_thumbnail.png)](https://youtu.be/EDUGMpGn5MI)
```

## Vercel / GitHub Pages Integration Notes

- Embed the hosted video URL, not the local MP4 path.
- Use the contact sheet as a lightweight poster image only if a small,
  web-optimized derivative is created intentionally.
- Keep the title, short description, and caveat near the video embed.
- Avoid autoplay with sound. A muted, click-to-play embed is safer for a
  technical portfolio page.
- If using GitHub Pages, keep the repo media light and avoid committing large
  generated video files.
- If using Vercel, store the video outside the Git repository unless a separate
  media-storage decision is made.

## Public-Safe Caveat

```text
Official DualSPHysics 3D inlet/open-boundary scientific demonstration. This is a visualization and post-processing workflow, not atomization validation, production CFD, or experimental agreement.
```
