# Blender Render Recipe

Renderer script committed in repo:

`/home/franco/Documents/GitHub/dualsphysics-visualsphysics-portfolio/scripts/blender_internal_nozzle_surface_sequence.py`

Commit:

`dc9ffff801caeb674df9ac73120ac2c605536279`

Core settings:

- Blender: 4.5.10 LTS
- Renderer: Cycles
- Device: Cycles OPTIX: NVIDIA GeForce RTX 5070 Laptop GPU, NVIDIA GeForce RTX 5070 Laptop GPU
- Samples: 24
- Resolution: 1920x1080
- Denoising: enabled
- Surface import: direct facet mesh import, no smoothing, no remeshing, no decimation

Rendered outputs:

- `showcase/internal_nozzle_full_domain_blender_physics_sequence.mp4`: all 61 Task 03 L7 physical frames at 6 fps
- `showcase/internal_nozzle_final_frame_probe_flythrough.mp4`: 72-frame curved camera flythrough around the final Task 03 L7 frame at 12 fps
- `showcase/internal_nozzle_l7_l8_scientific_comparison.mp4`: 25 matched L7/L8 physical-time frames at 6 fps
- `showcase/internal_nozzle_quarter_symmetry_blender_diagnostic.mp4`: all 61 Task 05 mirrored quarter-domain diagnostic frames at 6 fps

No CFD command was run for Task 07.
