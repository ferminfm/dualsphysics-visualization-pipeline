# Field Visualization Method Note

Inputs came from Task 02 restore-only CSV exports. No CFD time advancement was performed.

For each selected checkpoint, Task 05 selected the `z ~= 0` center slice using `abs(z) <= 0.51 * Delta`, interpolated scattered samples to a regular plotting grid, and overlaid an `f=0.5` contour as the liquid/interface context where available.

Generated fields: phase indicator `f`, velocity magnitude `speed`, diagnostic `vorticity_magnitude`, and ambient-phase speed/streamline context using `f <= 1e-3`.

Blocked fields: pressure heatmaps are blocked because restored `p` has zero range. Lambda2/Q-like criteria remain blocked because Task 02 did not export a validated adaptive-grid gradient-tensor convention.
