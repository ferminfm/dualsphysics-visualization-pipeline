# basilisk-blender-bridge

Internal draft for a future public repository.

`basilisk-blender-bridge` is a small visualization bridge for converting Basilisk/VOF facet outputs into Blender review media with explicit manifests and scientific claim boundaries.

## Goals

- Track Basilisk facet/frame outputs with reusable manifests.
- Import solver-derived VOF facets into Blender scenes.
- Apply topology-preserving surface-normal recipes for visualization.
- Automate materials, cameras, contact sheets, stills, and ffprobe metadata.
- Keep visual assets traceable to source frames and claim boundaries.

## Non-goals

- Not a CFD solver.
- Not a validation dataset.
- Not a pressure-nozzle model.
- Not a claim of true atomisation, experimental agreement, or production CFD.
- Not a repository for raw simulation dumps or full media archives.

## Example workflow

```bash
basilisk-facet-manifest --surface-dir vof_surfaces --out surface_manifest.json
render-blender-sequence --manifest surface_manifest.json --recipe merged_smooth_normals
bridge-contact-sheet --video output.mp4 --out contact_sheet.jpg
ffprobe-manifest --video output.mp4 --out media_manifest.json
```

## Example claim boundary

This repository demonstrates a visualization workflow for Basilisk VOF outputs. It does not validate the underlying simulation or provide predictive nozzle modeling.
