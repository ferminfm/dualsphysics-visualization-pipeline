# VisualSPHysics Build Decision

This repository uses the direct Blender VTK fallback as the active
visualization path instead of pursuing a full VisualSPHysics build now.

## Decision

- Keep VisualSPHysics parked as a future recovery path.
- Use `scripts/blender_import_legacy_vtk.py` for the active reproducible
  portfolio workflow.
- Do not vendor VisualSPHysics, VTK, Blender, compiled modules, or generated
  simulation outputs in this repository.

## Evidence

The disposable VisualSPHysics UI patch passed as a Blender 4.5 registration
diagnostic. After guarding the top-level `vtkimporter` and `diffuseparticles`
imports in a disposable copy, portable Blender imported, registered, and
unregistered the VisualSPHysics UI classes headlessly with no Blender API
traceback.

That diagnostic only proved that the UI layer can be made to register. It did
not prove the full data-import path, foam features, or compiled module path.

The full VisualSPHysics path remains held because its real data import and foam
features require compiled modules:

- `vtkimporter`
- `diffuseparticles`

Those modules require VTK development headers, VTK CMake metadata, and extension
modules built for Blender's Python ABI.

## Blockers

- Portable Blender 4.5 uses Python `3.11` / `cpython-311-x86_64-linux-gnu`.
- System Python and visible VTK Python bindings use Python `3.12` /
  `cpython-312-x86_64-linux-gnu`.
- Portable Blender does not provide a local `Python.h` include tree.
- `VTKConfig.cmake` and VTK development headers were not visible locally.

A naive build against system Python/VTK would likely produce Python 3.12
extension modules that do not load in Blender 4.5.

## Active Path

The direct Blender fallback imports the small prepared DualSPHysics legacy VTK
subset directly in portable Blender, without VisualSPHysics, VTK Python, or
system package changes.

This is sufficient for the current portfolio goal:

```text
DualSPHysics GPU run -> prepared VTK subset -> portable Blender fallback render
```

Generated VTK files, renders, `.blend` files, MP4 files, raw frames, and logs
remain outside Git unless they are deliberately small portfolio assets.
