# Basilisk Rectangular Atomisation Blender Showcase

`scripts/blender_rectangular_atomisation_showcase.py` renders internal-review
Cycles media from Basilisk `output_facets(f)` surface manifests. It is designed
for the 2026-06-25 rectangular Poiseuille atomisation showcase batch and keeps
generated frames, videos, `.blend` files, and manifests outside the repository.

The script preserves topology by importing facet polygons directly. It does not
smooth, remesh, decimate, or fabricate solver states. The official circular
control is the primary media route; the 2:1 rectangular imposed-inlet route is a
caveated comparison only unless later resolution work supersedes that decision.

Supported modes:

- `smoke`: one representative Cycles render and device qualification.
- `sequence`: all primary physical surface frames in chronological order.
- `comparison`: exact-time round-versus-rectangular frame pairs.
- `flythrough`: static final-frame curved external camera path.
- `multiview`: final-frame oblique/profile/top stills.

Keep `fit_ready=false` and `public_ready=false` for this batch. Do not publish
these assets without a separate human review task.
