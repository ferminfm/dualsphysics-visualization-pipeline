# Pressure Visualization Blocked

Status: `blocked_pressure_only`

Task 02 restored the pressure symbol, but every selected export has `p` with zero range (`min=0`, `max=0`, `sum=0`). Task 05 therefore did not create pressure heatmaps.

Future export requirement: write pressure or a pressure-like diagnostic at the source postprocess event, verify nonzero range in the exported metadata, and only then generate pressure media.
