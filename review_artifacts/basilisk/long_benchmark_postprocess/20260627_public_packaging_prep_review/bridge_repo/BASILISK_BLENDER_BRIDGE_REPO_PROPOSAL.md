# Basilisk-to-Blender Bridge Repo Proposal

## Recommended public repo name

`basilisk-blender-bridge`

This name is short, direct, and narrower than a full CFD validation or atomisation claim. It describes the reusable layer that emerged from this benchmark: moving Basilisk VOF/facet evidence into a reviewable Blender/media pipeline.

## Scope

The future public contribution should be a reusable bridge layer, not a solver benchmark claim.

Included:

- Basilisk facet/VOF output manifests;
- checkpoint/frame mapping schemas;
- surface import helpers;
- topology-preserving normal/surface recipes;
- Blender scene automation;
- material presets for VOF surfaces;
- camera/flythrough tools;
- contact sheet and ffprobe metadata generation;
- claim/metadata manifests that preserve scientific boundaries.

Excluded:

- raw solver data;
- checkpoint dumps;
- full frame/surface folders;
- case-specific public claims;
- validation or predictive nozzle modeling claims.

## Relation to prior SPH/Blender pipeline

The earlier DualSPHysics/SPH visualization work focused on particle and reconstructed-surface outputs from SPH workflows. This bridge would target Basilisk/VOF facet output and checkpoint/frame synchronization. It should be positioned as a sibling visualization pipeline for VOF data, not as an extension of SPH physics validation.

## Candidate repo names

1. `basilisk-blender-bridge` — recommended.
2. `basilisk-vof-visualization-pipeline` — precise but longer.
3. `vof-to-blender-visualization` — generic and less discoverable for Basilisk users.
