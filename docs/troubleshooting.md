# Troubleshooting

This note records the failure modes that mattered while turning local
DualSPHysics outputs into public-safe Blender videos.

## Missing Full-Package Examples

Symptom:

```text
examples/inletoutlet/05_ShapesInlet3D not found
examples/inletoutlet/08_ImpingingJet not found
```

Cause:

The source-oriented checkout did not include every official example XML
directory. The official full package had the relevant inlet and impinging-jet
examples.

Fix:

- Inspect local full-package archives before inventing XML.
- Recover official examples from a trusted full package.
- Keep generated runs in `$HOME/stack-validation/...`, not in Git.
- Do not substitute dam-break output for a jet/inlet example when the scientific
  question depends on inlet/open-boundary behavior.

## Permission Denied After ZIP Extraction

Symptom:

```text
../../../bin/linux/GenCase_linux64: Permission denied
```

Cause:

Executable bits were missing after extracting the official package.

Fix:

```bash
chmod +x /path/to/DualSPHysics_v5.4/bin/linux/*
find /path/to/DualSPHysics_v5.4/examples -type f -name 'xCase*_linux64*.sh' -exec chmod +x {} +
```

No `sudo` is needed when the package lives in a user-writable location.

## Final Artifacts Written Only To `/tmp`

Symptom:

The run succeeded, but final MP4/contact-sheet/metrics were hard to recover
after a reboot or cleanup.

Cause:

Using `/tmp` for final deliverables instead of only disposable intermediates.

Fix:

Use a stable output root:

```bash
OUT_ROOT="$HOME/stack-validation/$(date +%Y%m%d)-dualsphysics-showcase"
mkdir -p "$OUT_ROOT"
```

It is acceptable to use `/tmp` for temporary scratch files, but final MP4, PNG,
CSV, JSON, manifest, and report files should go under `$HOME/stack-validation`.

## Static Or Incorrect MP4 Assembly

Symptom:

The contact sheet showed multiple rendered frames, but the MP4 appeared static
or much shorter than expected.

Cause:

The first assembly path effectively consumed too few source frames. This was a
frame-selection/encoding issue, not a solver or Blender rendering issue.

Fix:

- Create a manifest of actual animation frames.
- Copy or symlink them into a canonical directory as `frame_00000.png`,
  `frame_00001.png`, and so on.
- Assemble by deterministic numeric pattern:

```bash
ffmpeg -y -framerate 12 \
  -i "$RENDER_ROOT/frames_canonical/frame_%05d.png" \
  -c:v libx264 -pix_fmt yuv420p \
  "$RENDER_ROOT/showcase_fixed.mp4"
```

Then verify:

```bash
ffprobe "$RENDER_ROOT/showcase_fixed.mp4"
```

## Particle Render Looks Coarse

Symptom:

The video is technically correct but visibly marker-like or polygonal.

Cause:

SPH particle data rendered as visible points can expose particle spacing,
especially in sparse or low-resolution runs.

Fix:

- Use particle rendering when provenance matters.
- Use smoother marker scale/material/lighting for a first improvement.
- Use `IsoSurface_linux64` or another surface reconstruction path when a
  free-surface visual is more appropriate.
- Document that a surface render is post-processing, not physics validation.

## Surface Render Looks Better But Is Not Validation

Symptom:

The reconstructed surface looks more water-like and may be tempting to describe
as physically validated.

Cause:

Visual realism and physical validation are different standards.

Fix:

Keep this caveat near public media:

```text
Visualization and post-processing demonstration; not physical validation.
```

Do not claim production CFD validation, atomization validation, statistically
stationary spray validation, or experimental agreement.
