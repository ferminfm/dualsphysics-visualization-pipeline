# Candidate Public Repo Structure

```text
basilisk-blender-bridge/
  README.md
  LICENSE
  pyproject.toml
  basilisk_blender_bridge/
    __init__.py
    manifests.py
    facet_io.py
    blender_scene.py
    materials.py
    cameras.py
    media.py
    claim_boundary.py
  scripts/
    basilisk_facet_manifest.py
    render_blender_sequence.py
    make_contact_sheet.py
    ffprobe_manifest.py
  schemas/
    surface_manifest.schema.json
    render_asset_manifest.schema.json
    claim_boundary.schema.json
  examples/
    tiny_facets/
    minimal_manifest.json
    blender_recipe_minimal.md
  docs/
    getting_started.md
    topology_preserving_surfaces.md
    scientific_claim_boundaries.md
    basilisk_vof_notes.md
  tests/
    test_manifests.py
    test_facet_parser.py
    test_claim_boundary.py
```

Keep fixtures tiny and synthetic. Do not include benchmark raw fields, checkpoints, full videos, full frame folders, or private stack-validation paths.
```
