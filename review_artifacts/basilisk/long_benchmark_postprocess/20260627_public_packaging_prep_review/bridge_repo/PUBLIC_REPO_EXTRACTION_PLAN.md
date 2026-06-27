# Public Repo Extraction Plan

## Goal

Extract only the reusable Basilisk-to-Blender bridge layer into a future public repository. Do not include solver outputs, stack-validation folders, or benchmark-specific heavy media.

## Candidate source areas

- `scripts/blender_rectangular_atomisation_showcase.py` — mine reusable scene, material, camera, ffprobe/contact-sheet logic; remove benchmark-specific text and route assumptions.
- `scripts/export_basilisk_vof_surface.py` — evaluate generic surface export handling.
- Review packet schemas under `review_artifacts/` — extract manifest patterns only, not private paths/media.
- Documentation claim-boundary patterns from `docs/layer1_layer2_review_artifact_workflow.md` and current Basilisk status docs.

## Extraction phases

1. Create new repo skeleton with examples using tiny synthetic/sample facet files.
2. Move generic Python modules into `basilisk_blender_bridge/`.
3. Add CLI tools:
   - `basilisk-facet-manifest`
   - `basilisk-blender-render-sequence`
   - `bridge-contact-sheet`
   - `bridge-ffprobe-manifest`
4. Add docs and schema examples.
5. Add tests using tiny fixtures only.
6. Add claim-boundary template and metadata manifest template.

## Public boundary

The repo can say it helps convert Basilisk/VOF facet outputs into Blender review media. It must not claim validation, production CFD, true atomisation, pressure-nozzle validation, or predictive modeling.
