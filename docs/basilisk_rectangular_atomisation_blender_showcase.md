# Basilisk Rectangular Pulsed-Profile Blender Review Media

`scripts/blender_rectangular_atomisation_showcase.py` renders internal-review
Cycles media from Basilisk `output_facets(f)` surface manifests. It is designed
for the 2026-06-25 rectangular pulsed-profile benchmark batch and keeps
generated frames, videos, `.blend` files, and manifests outside the repository.

The script preserves topology by importing facet polygons directly. It does not
smooth, remesh, decimate, or fabricate solver states. The official circular
control is the primary media route; the 2:1 rectangular top-hat imposed-inlet
route is a caveated comparison only unless later resolution work supersedes that
decision. Poiseuille-series inlet profiles were implemented and tested by the
canonical source, but they were not selected by the bounded candidate gate.

Supported modes:

- `smoke`: one representative Cycles render and device qualification.
- `sequence`: all primary physical surface frames in chronological order.
- `comparison`: legacy exact-time round-versus-rectangular frame pairs. Corrected
  public-review comparisons should be assembled as a split-screen compositor
  from separately rendered route sequences, not as two routes in one shared 3D
  room.
- `flythrough`: static safe-frame curved external camera path, with optional
  low-resolution fluid-mask visibility QA.
- `multiview`: final-frame oblique/profile/top stills.

Keep `fit_ready=false` and `public_ready=false` for this batch. Do not publish
these assets without a separate human review task.
