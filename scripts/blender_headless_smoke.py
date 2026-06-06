"""Headless Blender smoke test for a VisualSPHysics add-on artifact.

Run with an isolated Blender environment, for example:

BLENDER_USER_CONFIG=/tmp/blender-config \
BLENDER_USER_SCRIPTS=/tmp/blender-scripts \
blender -b --python scripts/blender_headless_smoke.py -- /path/to/addon.zip
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def _addon_arg() -> Path:
    if "--" not in sys.argv:
        raise SystemExit("ERROR: pass add-on zip/path after --")
    args = sys.argv[sys.argv.index("--") + 1 :]
    if not args:
        raise SystemExit("ERROR: missing add-on zip/path")
    path = Path(args[0]).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"ERROR: add-on path not found: {path}")
    return path


def main() -> None:
    addon_path = _addon_arg()
    print(f"BLENDER_VERSION={bpy.app.version_string}")
    print(f"ADDON_PATH={addon_path}")

    bpy.ops.preferences.addon_install(filepath=str(addon_path), overwrite=True)

    candidates = [
        addon_path.stem,
        "VisualSPHysics",
        "visualsphysics",
    ]
    enabled = False
    last_error = None
    for module in candidates:
        try:
            bpy.ops.preferences.addon_enable(module=module)
            print(f"ADDON_ENABLE_CANDIDATE={module}")
            enabled = True
            break
        except Exception as exc:  # Blender reports add-on failures this way.
            last_error = exc

    enabled_modules = sorted(bpy.context.preferences.addons.keys())
    visual_modules = [m for m in enabled_modules if "sphysics" in m.lower()]
    print(f"VISUALSPHYSICS_ENABLED={enabled}")
    print(f"VISUALSPHYSICS_MODULES={visual_modules}")

    if not enabled:
        raise SystemExit(f"ERROR: could not enable add-on; last error: {last_error}")


if __name__ == "__main__":
    main()

