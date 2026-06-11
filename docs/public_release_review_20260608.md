# Public Release Review - 2026-06-08

## Files Inspected

- `README.md`
- `docs/video_publish_notes.md`
- `docs/visualsphysics_decision.md`
- `reports/dualsphysics_benchmark_summary.md`
- `reports/visualsphysics_preflight_summary.md`
- `reports/headless_blender_smoke_summary.md`

## Changes Made

- Replaced workstation-local absolute paths with `$HOME`, environment-variable
  examples, or external generated-artifact report names.
- Clarified that the active path is direct legacy VTK parsing plus headless
  Blender rendering.
- Kept VisualSPHysics documented as investigated but not adopted as the active
  renderer.
- Kept MP4 and raw output guidance outside Git.
- Preserved the caveat that the dam-break video is a visualization-pipeline
  demo, not production CFD validation.

## Overclaiming Risks Checked

- No production CFD validation is claimed.
- No atomization or spray validation is claimed.
- No full VisualSPHysics support is claimed.
- The MP4 is described as local/manual-hosting material, not a committed or
  uploaded artifact.

## Local Path Leakage Status

Reviewed public-facing files no longer expose workstation-local absolute paths.
Local generated-artifact paths are described with `$HOME` examples or neutral
external report names.

## Markdown And HTML Formatting Status

- README command examples remain fenced and replaceable.
- Superseded after manual upload: video publishing notes now record the hosted
  dam-break YouTube URL.
- Image references point to committed thumbnail/preview assets.

## Remaining Manual Checks

- Review the hosted video description and thumbnail after publication.
- Review README rendering on GitHub before public push.

## Verdict

Public candidate after manual MP4 review and explicit push approval.
