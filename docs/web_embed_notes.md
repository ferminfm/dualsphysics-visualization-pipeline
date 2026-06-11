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

## Hosting Placeholder

```text
Video hosting URL: TBD
Preferred first visibility: unlisted/manual review
```

Do not commit the MP4 directly to this repository. Host it manually through an
external video platform or a release/media storage path chosen later, then add
only the final public or unlisted URL to the README or website.

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
