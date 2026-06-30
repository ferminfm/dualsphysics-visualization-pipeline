# Test and Render Status

Commands run from the VisualBasilisk source branch:

- `python3 -m pytest -q` -> `20 passed`
- `python3 -m visualbasilisk.cli check examples/minimal_vof_smoke/surface_manifest.json` -> `ok: 2 surface frames`
- `python3 -m visualbasilisk.cli render-blender ... --dry-run` -> passed and produced a valid render plan
- Tiny actual Blender render outside Git -> attempted and passed

Actual render output was written under the local gate output root, not committed.
