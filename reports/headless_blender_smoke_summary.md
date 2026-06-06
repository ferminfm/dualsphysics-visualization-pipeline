# Headless Blender Smoke Summary

Source report:
`/home/franco/stack-validation/20260606-2252-visualsphysics-headless-smoke/report.md`

Summary:

- Status: FAIL / HOLD
- Blender headless available: no
- VisualSPHysics artifact found: no
- Add-on loaded: no
- Import possible: no
- Normal Blender user settings modified: no

Conclusion: install or unpack a user-space Blender binary first, then rerun the
headless smoke using isolated `BLENDER_USER_CONFIG` and `BLENDER_USER_SCRIPTS`.

